"""Semantic search endpoint."""

import asyncio

from fastapi import APIRouter, Request

from context_library.telemetry.tracer import get_tracer, get_status_code
from context_library.retrieval.query import retrieve
from context_library.server.schemas import QueryRequest, QueryResponse, QueryResultItem

tracer = get_tracer(__name__)
StatusCode = get_status_code()

router = APIRouter()


@router.post("/query", response_model=QueryResponse)
async def query(payload: QueryRequest, request: Request) -> QueryResponse:
    embedder = request.app.state.embedder
    document_store = request.app.state.document_store
    vector_store = request.app.state.vector_store
    reranker = request.app.state.reranker

    with tracer.start_as_current_span("query.endpoint") as query_span:
        try:
            query_span.set_attribute("query_length", len(payload.query))
            query_span.set_attribute("top_k", payload.top_k)
            query_span.set_attribute("rerank_enabled", payload.rerank)
            if payload.domain_filter is not None:
                query_span.set_attribute("domain_filter", payload.domain_filter.value)
            if payload.source_filter is not None:
                query_span.set_attribute("source_filter", payload.source_filter)

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
            query_span.set_attribute("result_count", len(items))
            return QueryResponse(results=items, total=len(items))
        except Exception as e:
            query_span.set_status(StatusCode.ERROR)
            query_span.record_exception(e)
            raise
