"""FastAPI application factory with lifespan management."""

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI

from context_library.core.differ import Differ
from context_library.core.embedder import Embedder
from context_library.core.pipeline import IngestionPipeline
from context_library.server.config import ServerConfig
from context_library.server.routes import health, ingest, retrieve
from context_library.storage.chromadb_store import ChromaDBVectorStore
from context_library.storage.document_store import DocumentStore

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    config = ServerConfig()

    # Ensure parent directory exists for SQLite DB
    db_path = Path(config.sqlite_db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)

    # Initialize components in dependency order
    document_store = DocumentStore(config.sqlite_db_path, check_same_thread=False)
    embedder = Embedder(config.embedding_model)
    differ = Differ()
    vector_store = ChromaDBVectorStore(config.chromadb_path)
    pipeline = IngestionPipeline(document_store, embedder, differ, vector_store)

    reranker = None
    if config.enable_reranker:
        from context_library.retrieval.reranker import Reranker

        reranker = Reranker(config.reranker_model)

    # Store on app.state for route access
    app.state.config = config
    app.state.document_store = document_store
    app.state.embedder = embedder
    app.state.vector_store = vector_store
    app.state.pipeline = pipeline
    app.state.reranker = reranker

    logger.info(
        "Server started (model=%s, dim=%d, vectors=%d)",
        embedder.model_id,
        embedder.dimension,
        vector_store.count(),
    )

    yield

    document_store.conn.close()
    logger.info("Server stopped")


def create_app() -> FastAPI:
    app = FastAPI(title="context-library", lifespan=lifespan)
    app.include_router(health.router)
    app.include_router(ingest.router)
    app.include_router(retrieve.router)
    return app


app = create_app()
