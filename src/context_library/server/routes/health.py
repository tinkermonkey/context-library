"""Health and status endpoint."""

import logging

from fastapi import APIRouter, Request

from context_library.server.schemas import HealthResponse

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/health", response_model=HealthResponse)
async def health(request: Request) -> HealthResponse:
    vector_store = request.app.state.vector_store
    embedder = request.app.state.embedder
    document_store = request.app.state.document_store

    status = "healthy"

    try:
        vector_count = vector_store.count()
    except Exception as e:
        logger.warning("Health check: vector store unreachable: %s", e)
        vector_count = 0
        status = "degraded"

    try:
        document_store.conn.execute("SELECT 1")
    except Exception as e:
        logger.warning("Health check: document store unreachable: %s", e)
        status = "degraded"

    return HealthResponse(
        status=status,
        vector_count=vector_count,
        embedding_model=embedder.model_id,
        embedding_dimension=embedder.dimension,
    )
