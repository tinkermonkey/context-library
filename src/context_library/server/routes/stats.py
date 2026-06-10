"""Dataset statistics endpoint."""

import asyncio
import logging

from fastapi import APIRouter, HTTPException, Query, Request

from context_library.server.schemas import (
    ActivityEvent,
    ActivityFeedResponse,
    AdapterStats,
    AdapterStatsResponse,
    DatasetStatsResponse,
    DomainStats,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["stats"])


@router.get("/stats", response_model=DatasetStatsResponse)
async def get_stats(request: Request) -> DatasetStatsResponse:
    ds = request.app.state.document_store
    raw = await asyncio.to_thread(ds.get_dataset_stats)
    return DatasetStatsResponse(
        total_sources=raw["total_sources"],
        total_active_chunks=raw["total_active_chunks"],
        retired_chunk_count=raw["retired_chunk_count"],
        sync_queue_pending_insert=raw["sync_queue_pending_insert"],
        sync_queue_pending_delete=raw["sync_queue_pending_delete"],
        by_domain=[
            DomainStats(
                domain=d["domain"],
                source_count=d["source_count"],
                active_chunk_count=d["active_chunk_count"],
            )
            for d in raw["by_domain"]
        ],
    )


@router.get("/stats/activity", response_model=ActivityFeedResponse)
async def get_activity_feed(
    request: Request,
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
) -> ActivityFeedResponse:
    """Return recent ingestion activity events derived from source_versions.

    Each event represents a completed ingestion pass for a source. Events are
    ordered newest-first and include the event type, entity name, source identifier,
    timestamp, and domain/adapter tags.
    """
    ds = request.app.state.document_store
    try:
        raw_events, total = await asyncio.to_thread(ds.get_activity_feed, limit, offset)
    except Exception as exc:
        logger.error("Activity feed query failed: %s", exc)
        raise HTTPException(status_code=500, detail="Failed to retrieve activity feed") from exc
    return ActivityFeedResponse(
        events=[
            ActivityEvent(
                event_type=e["event_type"],
                entity_name=e["entity_name"],
                identifier=e["identifier"],
                timestamp=e["timestamp"],
                domain=e["domain"],
                adapter_type=e["adapter_type"],
            )
            for e in raw_events
        ],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/stats/adapters", response_model=AdapterStatsResponse)
async def get_adapter_stats(request: Request) -> AdapterStatsResponse:
    """Get per-adapter source and active chunk counts.

    Returns one entry per adapter with source_count (total sources for that adapter)
    and active_chunk_count (total non-retired chunks in those sources).
    """
    ds = request.app.state.document_store
    raw = await asyncio.to_thread(ds.get_adapter_stats)
    return AdapterStatsResponse(
        adapters=[
            AdapterStats(
                adapter_id=row["adapter_id"],
                adapter_type=row["adapter_type"],
                domain=row["domain"],
                source_count=row["source_count"],
                active_chunk_count=row["active_chunk_count"],
            )
            for row in raw
        ],
    )
