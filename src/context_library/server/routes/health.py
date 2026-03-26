"""Health and status endpoint."""

import asyncio
import logging

from fastapi import APIRouter, Request

from context_library.server.helper_health import HelperHealthSnapshot
from context_library.server.schemas import CollectorDeliveryStatus, EndpointDeliveryStatus, CollectorStatus, HelperHealth, HealthResponse

logger = logging.getLogger(__name__)

router = APIRouter()


def _snapshot_to_schema(snapshot: HelperHealthSnapshot) -> HelperHealth:
    return HelperHealth(
        reachable=snapshot.reachable,
        probed_at=snapshot.probed_at,
        watermark=snapshot.watermark,
        collectors=[
            CollectorStatus(
                name=c.name,
                adapter_type=c.adapter_type,
                enabled=c.enabled,
                healthy=c.healthy,
                error=c.error,
                delivery=CollectorDeliveryStatus(
                    cursor=c.cursor,
                    has_more=c.has_more,
                    has_pending=c.has_pending,
                    endpoints={
                        name: EndpointDeliveryStatus(cursor=ep.cursor, has_more=ep.has_more)
                        for name, ep in c.endpoints.items()
                    } if c.endpoints else None,
                ) if c.delivery_available else None,
            )
            for c in snapshot.collectors
        ],
        error=snapshot.error,
    )


@router.get("/health", response_model=HealthResponse)
async def health(request: Request) -> HealthResponse:
    vector_store = request.app.state.vector_store
    embedder = request.app.state.embedder
    document_store = request.app.state.document_store

    status = "healthy"
    sqlite_ok = True
    chromadb_ok = True

    try:
        vector_count = await asyncio.to_thread(vector_store.count)
    except Exception as e:
        logger.warning("Health check: vector store unreachable: %s", e)
        vector_count = 0
        chromadb_ok = False
        status = "degraded"

    try:
        await asyncio.to_thread(lambda: document_store.conn.execute("SELECT 1"))
    except Exception as e:
        logger.warning("Health check: document store unreachable: %s", e)
        sqlite_ok = False
        status = "degraded"

    # Probe the helper service (uses in-memory cache with 30s TTL)
    helper_health: HelperHealth | None = None
    cache = getattr(request.app.state, "helper_health_cache", None)
    if cache is not None:
        try:
            snapshot = await asyncio.to_thread(cache.get_or_probe)
            helper_health = _snapshot_to_schema(snapshot)
        except Exception as e:
            logger.warning("Failed to get helper health snapshot: %s", e)

    return HealthResponse(
        status=status,
        vector_count=vector_count,
        embedding_model=embedder.model_id,
        embedding_dimension=embedder.dimension,
        sqlite_ok=sqlite_ok,
        chromadb_ok=chromadb_ok,
        helper=helper_health,
    )
