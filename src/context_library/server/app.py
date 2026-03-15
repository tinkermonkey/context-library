"""FastAPI application factory with lifespan management."""

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI

from context_library.core.differ import Differ
from context_library.core.embedder import Embedder
from context_library.core.pipeline import IngestionPipeline
from context_library.server.config import ServerConfig
from context_library.server.routes import adapters, chunks, health, ingest, retrieve, sources, stats
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

    # Build helper adapters if the helper is configured
    helper_adapters = []
    if config.helper_url and config.helper_api_key:
        try:
            from context_library.adapters.apple_reminders import AppleRemindersAdapter
            from context_library.adapters.apple_health import AppleHealthAdapter
            from context_library.adapters.apple_imessage import AppleiMessageAdapter
            from context_library.adapters.apple_notes import AppleNotesAdapter
            from context_library.adapters.apple_music import AppleMusicAdapter

            helper_adapters = [
                AppleRemindersAdapter(api_url=config.helper_url, api_key=config.helper_api_key),
                AppleHealthAdapter(api_url=config.helper_url, api_key=config.helper_api_key),
                AppleiMessageAdapter(api_url=config.helper_url, api_key=config.helper_api_key),
                AppleNotesAdapter(api_url=config.helper_url, api_key=config.helper_api_key),
                AppleMusicAdapter(api_url=config.helper_url, api_key=config.helper_api_key),
            ]
        except ImportError as e:
            logger.warning("Apple helper adapters not available (missing dependency): %s", e)

        if config.helper_filesystem_enabled:
            try:
                from context_library.adapters.filesystem_helper import FilesystemHelperAdapter
                helper_adapters.append(FilesystemHelperAdapter(api_url=config.helper_url, api_key=config.helper_api_key))
            except ImportError as e:
                logger.warning("FilesystemHelperAdapter not available (missing dependency): %s", e)

        if config.helper_obsidian_enabled:
            try:
                from context_library.adapters.obsidian_helper import ObsidianHelperAdapter
                helper_adapters.append(ObsidianHelperAdapter(api_url=config.helper_url, api_key=config.helper_api_key))
            except ImportError as e:
                logger.warning("ObsidianHelperAdapter not available (missing dependency): %s", e)

        if config.helper_oura_enabled:
            try:
                from context_library.adapters.oura import OuraAdapter
                helper_adapters.append(OuraAdapter(api_url=config.helper_url, api_key=config.helper_api_key))
            except ImportError as e:
                logger.warning("OuraAdapter not available (missing dependency): %s", e)
            except ValueError as e:
                logger.warning(
                    "OuraAdapter not available (invalid configuration): %s. "
                    "Ensure CTX_HELPER_API_KEY is set when CTX_HELPER_OURA_ENABLED=true",
                    e
                )

        if helper_adapters:
            logger.info("Helper adapters configured (%d adapters, url=%s)", len(helper_adapters), config.helper_url)

    # Store on app.state for route access
    app.state.config = config
    app.state.document_store = document_store
    app.state.embedder = embedder
    app.state.vector_store = vector_store
    app.state.pipeline = pipeline
    app.state.reranker = reranker
    app.state.helper_adapters = helper_adapters

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
    app.include_router(adapters.router)
    app.include_router(sources.router)
    app.include_router(chunks.router)
    app.include_router(stats.router)
    return app


app = create_app()
