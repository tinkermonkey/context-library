"""Contact-scoped context retrieval via entity_links traversal."""

import asyncio
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Query, Request

from context_library.server.schemas import (
    LineageResponse,
    PersonContextItem,
    PersonContextResponse,
)
from context_library.storage.models import Domain

router = APIRouter(prefix="/people", tags=["people"])


def _to_utc_iso(value: datetime) -> str:
    """Normalize a query-param datetime to a UTC ISO 8601 string.

    fetch_timestamp is always stored as datetime.now(timezone.utc).isoformat(), so
    comparisons must be normalized to the same UTC representation to be meaningful
    as plain string comparisons.
    """
    if value.tzinfo is not None:
        value = value.astimezone(timezone.utc)
    return value.isoformat()


@router.get("/{contact_id}/context", response_model=PersonContextResponse)
async def get_person_context(
    contact_id: str,
    request: Request,
    domains: str | None = Query(
        default=None,
        description="Comma-separated domain filter, e.g. messages,events,notes,tasks",
    ),
    since: datetime | None = Query(default=None, description="Inclusive lower bound on fetch_timestamp"),
    before: datetime | None = Query(default=None, description="Inclusive upper bound on fetch_timestamp"),
    limit: int = Query(default=50, gt=0, le=500),
    offset: int = Query(default=0, ge=0),
) -> PersonContextResponse:
    """Return all chunks linked to a contact via entity_links, ordered by recency.

    Resolves contact_id to its active PEOPLE chunk(s) via domain_metadata.contact_id,
    then traverses entity_links to find every chunk (message, event, note, task, ...)
    that was matched to that contact by the entity linker.
    """
    ds = request.app.state.document_store

    domain_list: list[str] | None = None
    if domains:
        try:
            domain_list = [Domain(d.strip()).value for d in domains.split(",") if d.strip()]
        except ValueError as e:
            raise HTTPException(status_code=400, detail=f"Invalid domain in filter: {e}") from e

    person_hashes = await asyncio.to_thread(ds.get_person_chunk_hashes_by_contact_id, contact_id)
    if not person_hashes:
        raise HTTPException(status_code=404, detail=f"Contact '{contact_id}' not found")

    chunk_tuples, total = await asyncio.to_thread(
        ds.get_entity_linked_chunks,
        person_hashes,
        domain_list,
        _to_utc_iso(since) if since is not None else None,
        _to_utc_iso(before) if before is not None else None,
        limit,
        offset,
    )

    items = [
        PersonContextItem(
            chunk_hash=chunk_ctx.chunk.chunk_hash,
            content=chunk_ctx.chunk.content,
            context_header=chunk_ctx.chunk.context_header,
            chunk_index=chunk_ctx.chunk.chunk_index,
            chunk_type=chunk_ctx.chunk.chunk_type.value,
            domain=chunk_ctx.domain,
            domain_metadata=chunk_ctx.chunk.domain_metadata,
            lineage=LineageResponse(
                chunk_hash=chunk_ctx.chunk.chunk_hash,
                source_id=chunk_ctx.source_id,
                source_version_id=chunk_ctx.source_version_id,
                adapter_id=chunk_ctx.adapter_id,
                domain=chunk_ctx.domain,
                normalizer_version=chunk_ctx.normalizer_version,
                embedding_model_id=chunk_ctx.embedding_model_id,
            ),
            _links={
                    "chunk": f"/chunks/{chunk_ctx.chunk.chunk_hash}?source_id={chunk_ctx.source_id}",
                    "source": f"/sources/{chunk_ctx.source_id}",
                },
        )
        for chunk_ctx in chunk_tuples
    ]

    return PersonContextResponse(
        contact_id=contact_id,
        items=items,
        total=total,
        limit=limit,
        offset=offset,
    )
