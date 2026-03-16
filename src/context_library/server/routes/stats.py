"""Dataset statistics endpoint."""

import asyncio

from fastapi import APIRouter, Request

from context_library.server.schemas import (
    AdapterStats,
    AdapterStatsResponse,
    DatasetStatsResponse,
    DomainStats,
)

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
