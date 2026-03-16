"""Chunk inspection endpoints."""

import asyncio
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
from context_library.storage.models import Chunk, ChunkType, Domain, LineageRecord

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


def _to_chain_item(chunk) -> ChunkVersionChainItem:
    return ChunkVersionChainItem(
        chunk_hash=chunk.chunk_hash,
        content=chunk.content,
        context_header=chunk.context_header,
        chunk_index=chunk.chunk_index,
        chunk_type=chunk.chunk_type.value,
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
    source versions.
    """
    ds = request.app.state.document_store
    rows, total = await asyncio.to_thread(
        ds.list_chunks,
        domain.value if domain else None,
        adapter_id,
        source_id,
        limit,
        offset,
    )

    chunk_responses = []
    for row in rows:
        chunk_hash = row["chunk_hash"]
        src_id = row["source_id"]
        # Construct chunk and lineage objects directly from the query result
        # without additional DB calls (query already returns all needed fields)
        chunk = Chunk(
            chunk_hash=chunk_hash,
            content=row["content"],
            context_header=row["context_header"],
            chunk_index=row["chunk_index"],
            chunk_type=ChunkType(row["chunk_type"]),
            domain_metadata=row["domain_metadata"],
            cross_refs=[],  # cross_refs not included in list_chunks query
            created_at=row["created_at"],
            retired_at=None,
        )
        lineage = LineageRecord(
            chunk_hash=chunk_hash,
            source_id=src_id,
            source_version_id=row["source_version_id"],
            adapter_id=row["adapter_id"],
            domain=Domain(row["domain"]),
            normalizer_version=row["normalizer_version"],
            embedding_model_id=row["embedding_model_id"],
        )
        chunk_responses.append(_chunk_response(chunk, lineage, src_id))

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
    chain_chunks = await asyncio.to_thread(ds.get_chunk_version_chain, chunk_hash, source_id)
    if not chain_chunks:
        raise HTTPException(
            status_code=404,
            detail=f"Chunk '{chunk_hash}' not found in source '{source_id}'",
        )
    return ChunkVersionChainResponse(
        chunk_hash=chunk_hash,
        source_id=source_id,
        chain=[_to_chain_item(c) for c in chain_chunks],
    )
