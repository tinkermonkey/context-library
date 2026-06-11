"""Chunk inspection endpoints."""

import asyncio
import math
from typing import Annotated

from fastapi import APIRouter, HTTPException, Path, Query, Request

from context_library.retrieval.provenance import trace_chunk_provenance
from context_library.server.schemas import (
    ChunkProvenanceResponse,
    ChunkResponse,
    ChunkVersionChainItem,
    ChunkVersionChainResponse,
    LineageResponse,
    TopLevelChunkListResponse,
)
from context_library.storage.models import Chunk, Domain, LineageRecord

router = APIRouter(prefix="/chunks", tags=["chunks"])

HashPath = Annotated[str, Path(pattern=r"^[0-9a-f]{64}$")]


def _lineage_response(lineage) -> LineageResponse:
    return LineageResponse(
        chunk_hash=lineage.chunk_hash,
        source_id=lineage.source_id,
        source_version_id=lineage.source_version_id,
        adapter_id=lineage.adapter_id,
        domain=lineage.domain.value,
        normalizer_version=lineage.normalizer_version,
        embedding_model_id=lineage.embedding_model_id,
    )


def _chunk_response(chunk, lineage, source_id: str) -> ChunkResponse:
    return ChunkResponse(
        chunk_hash=chunk.chunk_hash,
        content=chunk.content,
        context_header=chunk.context_header,
        chunk_index=chunk.chunk_index,
        chunk_type=chunk.chunk_type.value,
        domain_metadata=chunk.domain_metadata,
        cross_refs=list(chunk.cross_refs),
        lineage=_lineage_response(lineage),
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


def _cosine_similarity(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(x * x for x in b))
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return max(0.0, min(1.0, dot / (norm_a * norm_b)))


def _to_chain_item(
    chunk: Chunk,
    fetch_timestamp: str | None = None,
    similarity_to_head: float | None = None,
) -> ChunkVersionChainItem:
    return ChunkVersionChainItem(
        chunk_hash=chunk.chunk_hash,
        content=chunk.content,
        context_header=chunk.context_header,
        chunk_index=chunk.chunk_index,
        chunk_type=chunk.chunk_type.value,
        fetch_timestamp=fetch_timestamp,
        similarity_to_head=similarity_to_head,
    )


@router.get("", response_model=TopLevelChunkListResponse)
async def list_chunks(
    request: Request,
    domain: Domain | None = Query(default=None),
    adapter_id: str | None = Query(default=None),
    source_id: str | None = Query(default=None),
    limit: int = Query(default=50, gt=0, le=1000),
    offset: int = Query(default=0, ge=0),
) -> TopLevelChunkListResponse:
    """List active chunks with optional domain, adapter, and source filtering.

    Returns paginated chunks across all sources (or filtered by source_id),
    ordered by created_at DESC. Only returns non-retired chunks from current
    source versions. Corrupt chunks are skipped with warnings, ensuring partial
    data availability.

    Query parameters for metadata filtering can be passed as repeating parameters
    in the form `?metadata_filter=key:value&metadata_filter=key2:value2`.
    For example: `GET /chunks?domain=health&metadata_filter=health_type:workout_session`
    """
    ds = request.app.state.document_store

    # Parse optional metadata filters from query string
    # Format: ?metadata_filter=key:value&metadata_filter=key2:value2
    metadata_filter: dict[str, str] | None = None
    filter_params = request.query_params.getlist("metadata_filter") if hasattr(request.query_params, "getlist") else request.query_params.get("metadata_filter", [])
    if isinstance(filter_params, str):
        filter_params = [filter_params]
    if filter_params:
        metadata_filter = {}
        for param in filter_params:
            if ":" in param:
                key, value = param.split(":", 1)
                metadata_filter[key] = value

    chunk_tuples, total = await asyncio.to_thread(
        ds.list_chunks,
        domain.value if domain else None,
        adapter_id,
        source_id,
        limit,
        offset,
        metadata_filter,
    )

    chunk_responses = []
    for chunk_ctx in chunk_tuples:
        lineage = LineageRecord(
            chunk_hash=chunk_ctx.chunk.chunk_hash,
            source_id=chunk_ctx.source_id,
            source_version_id=chunk_ctx.source_version_id,
            adapter_id=chunk_ctx.adapter_id,
            domain=Domain(chunk_ctx.domain),
            normalizer_version=chunk_ctx.normalizer_version,
            embedding_model_id=chunk_ctx.embedding_model_id,
        )
        chunk_responses.append(_chunk_response(chunk_ctx.chunk, lineage, chunk_ctx.source_id))

    return TopLevelChunkListResponse(
        chunks=chunk_responses,
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/{chunk_hash}", response_model=ChunkResponse)
async def get_chunk(
    chunk_hash: HashPath,
    request: Request,
    source_id: str | None = Query(default=None),
) -> ChunkResponse:
    ds = request.app.state.document_store
    chunk = await asyncio.to_thread(ds.get_chunk_by_hash, chunk_hash, source_id)
    if chunk is None:
        raise HTTPException(status_code=404, detail=f"Chunk '{chunk_hash}' not found")
    lineage = await asyncio.to_thread(ds.get_lineage, chunk_hash, source_id)
    if lineage is None:
        raise HTTPException(status_code=404, detail=f"Lineage for chunk '{chunk_hash}' not found")
    effective_source = source_id or lineage.source_id
    return _chunk_response(chunk, lineage, effective_source)


@router.get("/{chunk_hash}/provenance", response_model=ChunkProvenanceResponse)
async def get_chunk_provenance(
    chunk_hash: HashPath,
    request: Request,
    source_id: str | None = Query(default=None),
) -> ChunkProvenanceResponse:
    ds = request.app.state.document_store
    try:
        prov = await asyncio.to_thread(trace_chunk_provenance, ds, chunk_hash, source_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    effective_source = source_id or prov.lineage.source_id
    chunk_resp = _chunk_response(prov.chunk, prov.lineage, effective_source)
    lineage_resp = _lineage_response(prov.lineage)
    chain = [_to_chain_item(c) for c in prov.version_chain]
    return ChunkProvenanceResponse(
        chunk=chunk_resp,
        lineage=lineage_resp,
        source_origin_ref=prov.source_origin_ref,
        adapter_type=prov.adapter_type,
        version_chain=chain,
        **{
            "_links": {
                "chunk": f"/chunks/{chunk_hash}?source_id={effective_source}",
                "source": f"/sources/{effective_source}",
                "adapter": f"/adapters/{prov.lineage.adapter_id}",
            }
        },
    )


@router.get("/{chunk_hash}/version-chain", response_model=ChunkVersionChainResponse)
async def get_chunk_version_chain(
    chunk_hash: HashPath,
    request: Request,
    source_id: str = Query(...),
) -> ChunkVersionChainResponse:
    ds = request.app.state.document_store
    embedder = request.app.state.embedder

    chain_with_ts = await asyncio.to_thread(
        ds.get_chunk_version_chain_with_timestamps, chunk_hash, source_id
    )
    if not chain_with_ts:
        raise HTTPException(
            status_code=404,
            detail=f"Chunk '{chunk_hash}' not found in source '{source_id}'",
        )

    # Compute similarity scores for each chain item relative to HEAD
    contents = [chunk.content for chunk, _ in chain_with_ts]
    embeddings: list[list[float]] = await asyncio.to_thread(embedder.embed, contents)

    # HEAD is the item matching chunk_hash; fall back to last item if not found
    head_idx = next(
        (i for i, (c, _) in enumerate(chain_with_ts) if c.chunk_hash == chunk_hash),
        len(chain_with_ts) - 1,
    )
    head_embedding = embeddings[head_idx]

    chain_items = []
    for i, (chunk, ts) in enumerate(chain_with_ts):
        similarity = _cosine_similarity(head_embedding, embeddings[i])
        chain_items.append(_to_chain_item(chunk, fetch_timestamp=ts, similarity_to_head=similarity))

    return ChunkVersionChainResponse(
        chunk_hash=chunk_hash,
        source_id=source_id,
        chain=chain_items,
    )
