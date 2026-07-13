"""Dead-letter inspection endpoints.

Per-source ingest failures are skipped so the rest of their page can commit,
and the page is then acked — the helper's cursor advances past the failed
items. The dead_letters table is the durable record of those drops; these
endpoints expose it for monitoring and post-fix cleanup.
"""

import asyncio
import logging

from fastapi import APIRouter, Query, Request
from pydantic import BaseModel

logger = logging.getLogger(__name__)

router = APIRouter(tags=["dead-letters"])


class DeadLetter(BaseModel):
    id: int
    adapter_id: str
    source_id: str
    error_type: str
    message: str
    first_seen: str
    last_seen: str
    retry_count: int


class DeadLetterListResponse(BaseModel):
    total: int
    dead_letters: list[DeadLetter]


class DeadLetterClearResponse(BaseModel):
    deleted: int


@router.get("/dead-letters", response_model=DeadLetterListResponse)
async def list_dead_letters(
    request: Request,
    adapter_id: str | None = Query(default=None, description="Filter by adapter_id"),
    limit: int = Query(default=100, ge=1, le=1000),
) -> DeadLetterListResponse:
    """List sources that failed ingest and were skipped by a committed page."""
    ds = request.app.state.document_store
    rows = await asyncio.to_thread(ds.list_dead_letters, adapter_id, limit)
    total = await asyncio.to_thread(ds.count_dead_letters, adapter_id)
    return DeadLetterListResponse(
        total=total,
        dead_letters=[DeadLetter(**row) for row in rows],
    )


@router.post("/dead-letters/clear", response_model=DeadLetterClearResponse)
async def clear_dead_letters(
    request: Request,
    adapter_id: str | None = Query(default=None, description="Only clear rows for this adapter"),
    source_id: str | None = Query(default=None, description="Only clear rows for this source"),
) -> DeadLetterClearResponse:
    """Delete dead-letter rows after manual review or a successful re-ingest."""
    ds = request.app.state.document_store
    deleted = await asyncio.to_thread(ds.clear_dead_letters, adapter_id, source_id)
    logger.info(
        "Cleared %d dead-letter row(s) (adapter_id=%s, source_id=%s)",
        deleted, adapter_id, source_id,
    )
    return DeadLetterClearResponse(deleted=deleted)
