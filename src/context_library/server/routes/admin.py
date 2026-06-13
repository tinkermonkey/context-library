"""Admin endpoints for adapter management, system config, and sync log."""

import asyncio
import logging
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Query, Request

from context_library.server.auth import require_auth
from context_library.server.schemas import (
    AdminAdapterListResponse,
    AdminAdapterStatus,
    AdminConfigResponse,
    PipelineListResponse,
    PipelineRun,
    SyncLogEntry,
    SyncLogResponse,
    TriggerSyncResponse,
)
from context_library.scheduler.exceptions import (
    AdapterNotRegisteredError,
    IngestAlreadyInProgressError,
    NoSourcesError,
    PollerNotRunningError,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin", tags=["admin"])


@router.get("/adapters", response_model=AdminAdapterListResponse)
async def list_admin_adapters(request: Request) -> AdminAdapterListResponse:
    """Per-adapter status: last run, item counts, domain."""
    require_auth(request)
    ds = request.app.state.document_store
    rows = await asyncio.to_thread(ds.get_admin_adapter_status)
    return AdminAdapterListResponse(
        adapters=[
            AdminAdapterStatus(
                adapter_id=row["adapter_id"],
                adapter_type=row["adapter_type"],
                domain=row["domain"],
                last_run=row["last_run"],
                source_count=row["source_count"],
                active_chunk_count=row["active_chunk_count"],
            )
            for row in rows
        ]
    )


@router.get("/pipelines", response_model=PipelineListResponse)
async def list_active_pipelines(request: Request) -> PipelineListResponse:
    """Return currently active pipeline ingestion runs.

    Each entry represents an in-flight call to IngestionPipeline.ingest(). Returns
    an empty list when no ingestion is in progress. Duration is computed from the
    run's start time to now.
    """
    require_auth(request)
    pipeline = request.app.state.pipeline
    active_runs = pipeline.get_active_runs()
    now = datetime.now(timezone.utc)
    runs = [
        PipelineRun(
            run_id=r.run_id,
            adapter_id=r.adapter_id,
            current_step=r.current_step,
            started_at=r.started_at.isoformat(),
            duration_sec=(now - r.started_at).total_seconds(),
            ingested=r.sources_ingested,
            created=r.chunks_created,
            unchanged=r.chunks_unchanged,
            errors=r.errors,
        )
        for r in active_runs
    ]
    return PipelineListResponse(runs=runs, total=len(runs))


@router.post("/adapters/{adapter_id}/sync", response_model=TriggerSyncResponse)
async def trigger_adapter_sync(adapter_id: str, request: Request) -> TriggerSyncResponse:
    """Trigger an immediate re-sync for the given adapter without resetting data.

    Returns a TriggerSyncResponse in all non-error cases — even when the adapter
    is push-only or the poller is unavailable — so callers get a structured message
    rather than a 4xx/5xx. A 404 is returned only when the adapter does not exist.
    """
    require_auth(request)
    ds = request.app.state.document_store
    poller = request.app.state.poller

    adapter_config = await asyncio.to_thread(ds.get_adapter, adapter_id)
    if adapter_config is None:
        raise HTTPException(status_code=404, detail=f"Adapter '{adapter_id}' not found")

    try:
        triggered = poller.trigger_immediate_ingest(adapter_id)
        if triggered:
            return TriggerSyncResponse(
                adapter_id=adapter_id,
                triggered=True,
                message="Re-sync triggered successfully",
            )
        return TriggerSyncResponse(
            adapter_id=adapter_id,
            triggered=False,
            message="Adapter has no pull sources; push-only adapters sync via webhook",
        )
    except PollerNotRunningError:
        return TriggerSyncResponse(
            adapter_id=adapter_id,
            triggered=False,
            message="Poller is not running; re-sync cannot be triggered",
        )
    except AdapterNotRegisteredError:
        return TriggerSyncResponse(
            adapter_id=adapter_id,
            triggered=False,
            message="Adapter is not registered with poller; may be push-only",
        )
    except NoSourcesError:
        return TriggerSyncResponse(
            adapter_id=adapter_id,
            triggered=False,
            message="No sources found for this adapter",
        )
    except IngestAlreadyInProgressError:
        return TriggerSyncResponse(
            adapter_id=adapter_id,
            triggered=False,
            message="Ingest already in progress for this adapter",
        )
    except Exception as e:
        logger.error("Sync trigger failed for %s: %s", adapter_id, e, exc_info=True)
        raise HTTPException(status_code=500, detail=f"Sync trigger error: {e}")


@router.get("/config", response_model=AdminConfigResponse)
async def get_admin_config(request: Request) -> AdminConfigResponse:
    """Return non-sensitive server configuration values.

    Sensitive values (webhook_secret, helper_api_key) are never returned in responses.
    The presence of a webhook secret is indicated by the webhook_secret_set boolean.
    """
    require_auth(request)
    config = request.app.state.config
    ds = request.app.state.document_store
    db_size = await asyncio.to_thread(ds.get_db_size_bytes)
    return AdminConfigResponse(
        embedding_model=config.embedding_model,
        reranker_model=config.reranker_model,
        enable_reranker=config.enable_reranker,
        sqlite_db_path=config.sqlite_db_path,
        chromadb_path=config.chromadb_path,
        webhook_secret_set=bool(config.webhook_secret),
        helper_url_set=bool(config.helper_url),
        helper_oura_enabled=config.helper_oura_enabled,
        helper_filesystem_enabled=config.helper_filesystem_enabled,
        youtube_enabled=config.youtube_enabled,
        db_size_bytes=db_size,
    )


@router.get("/logs", response_model=SyncLogResponse)
async def get_sync_logs(
    request: Request,
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
) -> SyncLogResponse:
    """Return paginated entries from the lancedb_sync_log table, newest first."""
    require_auth(request)
    ds = request.app.state.document_store
    entries, total = await asyncio.to_thread(ds.get_sync_log, limit, offset)
    return SyncLogResponse(
        entries=[
            SyncLogEntry(
                id=e["id"],
                chunk_hash=e["chunk_hash"],
                operation=e["operation"],
                synced_at=e["synced_at"],
            )
            for e in entries
        ],
        total=total,
        limit=limit,
        offset=offset,
    )
