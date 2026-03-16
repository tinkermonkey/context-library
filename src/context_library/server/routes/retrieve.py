"""Semantic search endpoint."""

import asyncio

from fastapi import APIRouter, Request

from context_library.retrieval.query import retrieve
from context_library.server.schemas import QueryRequest, QueryResponse, QueryResultItem

router = APIRouter()


@router.post("/query", response_model=QueryResponse)
async def query(payload: QueryRequest, request: Request) -> QueryResponse:
    embedder = request.app.state.embedder
    document_store = request.app.state.document_store
    vector_store = request.app.state.vector_store
    reranker = request.app.state.reranker

    results = await asyncio.to_thread(
        retrieve,
        query=payload.query,
        embedder=embedder,
        document_store=document_store,
        vector_store=vector_store,
        top_k=payload.top_k,
        domain_filter=payload.domain_filter,
        source_filter=payload.source_filter,
    )

    if payload.rerank and reranker is not None and results:
        results = await asyncio.to_thread(
            reranker.rerank,
            query=payload.query,
            candidates=results,
            top_k=payload.rerank_top_k,
        )

    items = [QueryResultItem.model_validate(r.to_dict()) for r in results]
    return QueryResponse(results=items, total=len(items))
