"""Source inspection endpoints."""

import asyncio

from fastapi import APIRouter, HTTPException, Query, Request

from context_library.retrieval.provenance import get_version_diff
from context_library.storage.models import Domain
from context_library.server.schemas import (
    ChunkListResponse,
    ChunkResponse,
    ChunkVersionChainItem,
    LineageResponse,
    SourceDetailResponse,
    SourceListResponse,
    SourceSummary,
    VersionDetailResponse,
    VersionDiffResponse,
    VersionHistoryResponse,
    VersionSummary,
)

router = APIRouter(prefix="/sources", tags=["sources"])


def _chunk_response(chunk, lineage, source_id: str) -> ChunkResponse:
    lin = LineageResponse(
        chunk_hash=lineage.chunk_hash,
        source_id=lineage.source_id,
        source_version_id=lineage.source_version_id,
        adapter_id=lineage.adapter_id,
        domain=lineage.domain.value,
        normalizer_version=lineage.normalizer_version,
        embedding_model_id=lineage.embedding_model_id,
    )
    return ChunkResponse(
        chunk_hash=chunk.chunk_hash,
        content=chunk.content,
        context_header=chunk.context_header,
        chunk_index=chunk.chunk_index,
        chunk_type=chunk.chunk_type.value,
        domain_metadata=chunk.domain_metadata,
        cross_refs=list(chunk.cross_refs),
        lineage=lin,
        **{
            "_links": {
                "self": f"/chunks/{chunk.chunk_hash}?source_id={source_id}",
                "source": f"/sources/{source_id}",
                "source_version": f"/sources/{source_id}/versions/{lineage.source_version_id}",
                "provenance": f"/chunks/{chunk.chunk_hash}/provenance?source_id={source_id}",
                "version_chain": f"/chunks/{chunk.chunk_hash}/version-chain?source_id={source_id}",
                "adapter": f"/adapters/{lineage.adapter_id}",
            }
        },
    )


@router.get("", response_model=SourceListResponse)
async def list_sources(
    request: Request,
    domain: Domain | None = Query(default=None),
    adapter_id: str | None = Query(default=None),
    source_id_prefix: str | None = Query(default=None),
    limit: int = Query(default=50, gt=0, le=5000),
    offset: int = Query(default=0, ge=0),
    sort_by: str = Query(default="created_at", pattern="^(created_at|updated_at|chunk_count)$"),
    order: str = Query(default="asc", pattern="^(asc|desc)$"),
) -> SourceListResponse:
    ds = request.app.state.document_store
    domain_value = domain.value if domain is not None else None
    rows, total = await asyncio.to_thread(
        ds.list_sources, domain_value, adapter_id, source_id_prefix, limit, offset, sort_by, order
    )
    sources = [
        SourceSummary(
            source_id=r["source_id"],
            adapter_id=r["adapter_id"],
            adapter_type=r["adapter_type"],
            domain=r["domain"],
            origin_ref=r["origin_ref"],
            display_name=r["display_name"],
            current_version=r["current_version"],
            last_fetched_at=r["last_fetched_at"],
            poll_strategy=r["poll_strategy"],
            chunk_count=r["chunk_count"],
            created_at=r["created_at"],
            updated_at=r["updated_at"],
            **{
                "_links": {
                    "self": f"/sources/{r['source_id']}",
                    "versions": f"/sources/{r['source_id']}/versions",
                    "chunks": f"/sources/{r['source_id']}/chunks",
                    "adapter": f"/adapters/{r['adapter_id']}",
                }
            },
        )
        for r in rows
    ]
    return SourceListResponse(sources=sources, total=total, limit=limit, offset=offset)


@router.get("/{source_id:path}/versions", response_model=VersionHistoryResponse)
async def get_version_history(source_id: str, request: Request) -> VersionHistoryResponse:
    ds = request.app.state.document_store
    versions = await asyncio.to_thread(ds.get_version_history, source_id)
    if not versions:
        raise HTTPException(
            status_code=404,
            detail=f"Source '{source_id}' not found or has no versions",
        )
    version_summaries = []
    for idx, v in enumerate(versions):
        links: dict[str, str] = {
            "self": f"/sources/{source_id}/versions/{v.version}",
            "chunks": f"/sources/{source_id}/chunks?version={v.version}",
            "source": f"/sources/{source_id}",
        }

        # Calculate diff counts from in-memory hash sets
        # (no additional DB queries — using chunk_hashes already fetched)
        if v.version == 1:
            added_count = len(v.chunk_hashes)
            removed_count = 0
            unchanged_count = 0
        else:
            links["diff_from_prev"] = (
                f"/sources/{source_id}/diff?from_version={v.version - 1}&to_version={v.version}"
            )
            # Compute set differences from previous version's hashes
            current_hashes = set(v.chunk_hashes)
            prev_hashes = set(versions[idx - 1].chunk_hashes)
            added_count = len(current_hashes - prev_hashes)
            removed_count = len(prev_hashes - current_hashes)
            unchanged_count = len(current_hashes & prev_hashes)

        version_summaries.append(
            VersionSummary(
                source_id=v.source_id,
                version=v.version,
                chunk_hash_count=len(v.chunk_hashes),
                added_chunks=added_count,
                removed_chunks=removed_count,
                unchanged_chunks=unchanged_count,
                adapter_id=v.adapter_id,
                normalizer_version=v.normalizer_version,
                fetch_timestamp=v.fetch_timestamp,
                **{"_links": links},
            )
        )
    return VersionHistoryResponse(source_id=source_id, versions=version_summaries)


@router.get("/{source_id:path}/versions/{version}", response_model=VersionDetailResponse)
async def get_source_version(
    source_id: str, version: int, request: Request
) -> VersionDetailResponse:
    ds = request.app.state.document_store
    sv = await asyncio.to_thread(ds.get_source_version, source_id, version)
    if sv is None:
        raise HTTPException(
            status_code=404,
            detail=f"Version {version} of source '{source_id}' not found",
        )
    return VersionDetailResponse(
        source_id=sv.source_id,
        version=sv.version,
        markdown=sv.markdown,
        chunk_hashes=list(sv.chunk_hashes),
        adapter_id=sv.adapter_id,
        normalizer_version=sv.normalizer_version,
        fetch_timestamp=sv.fetch_timestamp,
        **{
            "_links": {
                "self": f"/sources/{source_id}/versions/{version}",
                "chunks": f"/sources/{source_id}/chunks?version={version}",
                "source": f"/sources/{source_id}",
            }
        },
    )


@router.get("/{source_id:path}/chunks", response_model=ChunkListResponse)
async def get_source_chunks(
    source_id: str,
    request: Request,
    version: int | None = Query(default=None),
    limit: int | None = Query(default=None, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
) -> ChunkListResponse:
    ds = request.app.state.document_store
    # Resolve the actual version from source metadata before fetching chunks
    if version is None:
        source_row = await asyncio.to_thread(ds.get_source_detail, source_id)
        actual_version = source_row["current_version"] if source_row else None
    else:
        actual_version = version
    chunks, total = await asyncio.to_thread(ds.get_chunks_by_source, source_id, version, limit, offset)
    chunk_responses = []
    for chunk in chunks:
        lineage = await asyncio.to_thread(ds.get_lineage, chunk.chunk_hash, source_id)
        if lineage is None:
            continue
        chunk_responses.append(_chunk_response(chunk, lineage, source_id))
    return ChunkListResponse(source_id=source_id, version=actual_version, chunks=chunk_responses, total=total, limit=limit, offset=offset)


@router.get("/{source_id:path}/diff", response_model=VersionDiffResponse)
async def get_version_diff_endpoint(
    source_id: str,
    request: Request,
    from_version: int = Query(...),
    to_version: int = Query(...),
) -> VersionDiffResponse:
    if from_version == to_version:
        raise HTTPException(status_code=400, detail="from_version and to_version must differ")
    ds = request.app.state.document_store
    try:
        diff = await asyncio.to_thread(get_version_diff, ds, source_id, from_version, to_version)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    def _to_item(chunk) -> ChunkVersionChainItem:
        return ChunkVersionChainItem(
            chunk_hash=chunk.chunk_hash,
            content=chunk.content,
            context_header=chunk.context_header,
            chunk_index=chunk.chunk_index,
            chunk_type=chunk.chunk_type.value,
        )

    return VersionDiffResponse(
        source_id=diff.source_id,
        from_version=diff.from_version,
        to_version=diff.to_version,
        added_hashes=sorted(diff.added_hashes),
        removed_hashes=sorted(diff.removed_hashes),
        unchanged_hashes=sorted(diff.unchanged_hashes),
        added_chunks=[_to_item(c) for c in diff.added_chunks],
        removed_chunks=[_to_item(c) for c in diff.removed_chunks],
    )


# Registered last so the greedy {source_id:path} catch-all does not shadow
# the more specific sub-routes above (versions, chunks, diff).
@router.get("/{source_id:path}", response_model=SourceDetailResponse)
async def get_source(source_id: str, request: Request) -> SourceDetailResponse:
    ds = request.app.state.document_store
    row = await asyncio.to_thread(ds.get_source_detail, source_id)
    if row is None:
        raise HTTPException(status_code=404, detail=f"Source '{source_id}' not found")
    return SourceDetailResponse(
        source_id=row["source_id"],
        adapter_id=row["adapter_id"],
        adapter_type=row["adapter_type"],
        domain=row["domain"],
        origin_ref=row["origin_ref"],
        display_name=row["display_name"],
        current_version=row["current_version"],
        last_fetched_at=row["last_fetched_at"],
        poll_strategy=row["poll_strategy"],
        poll_interval_sec=row["poll_interval_sec"],
        normalizer_version=row["normalizer_version"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
        chunk_count=row["chunk_count"],
        **{
            "_links": {
                "self": f"/sources/{source_id}",
                "versions": f"/sources/{source_id}/versions",
                "chunks": f"/sources/{source_id}/chunks",
                "adapter": f"/adapters/{row['adapter_id']}",
            }
        },
    )
