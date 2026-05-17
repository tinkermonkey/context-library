"""Semantic search endpoint."""

import asyncio
from typing import Any

from fastapi import APIRouter, Request

from context_library.telemetry.tracer import get_tracer, get_status_code
from context_library.retrieval.query import retrieve
from context_library.server.schemas import QueryRequest, QueryResponse, QueryResultItem

# Import OTel context for cross-thread propagation
try:
    from opentelemetry import context as otel_context
    _otel_available = True
except ImportError:
    _otel_available = False

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

            # Capture OTel context before spawning worker thread to propagate span context
            ctx = otel_context.get_current() if _otel_available else None

            def retrieve_with_context() -> Any:
                if _otel_available and ctx is not None:
                    token = otel_context.attach(ctx)
                    try:
                        return retrieve(
                            query=payload.query,
                            embedder=embedder,
                            document_store=document_store,
                            vector_store=vector_store,
                            top_k=payload.top_k,
                            domain_filter=payload.domain_filter,
                            source_filter=payload.source_filter,
                        )
                    finally:
                        otel_context.detach(token)
                else:
                    return retrieve(
                        query=payload.query,
                        embedder=embedder,
                        document_store=document_store,
                        vector_store=vector_store,
                        top_k=payload.top_k,
                        domain_filter=payload.domain_filter,
                        source_filter=payload.source_filter,
                    )

            results = await asyncio.to_thread(retrieve_with_context)

            if payload.rerank and reranker is not None and results:
                def rerank_with_context() -> Any:
                    if _otel_available and ctx is not None:
                        token = otel_context.attach(ctx)
                        try:
                            return reranker.rerank(
                                query=payload.query,
                                candidates=results,
                                top_k=payload.rerank_top_k,
                            )
                        finally:
                            otel_context.detach(token)
                    else:
                        return reranker.rerank(
                            query=payload.query,
                            candidates=results,
                            top_k=payload.rerank_top_k,
                        )

                results = await asyncio.to_thread(rerank_with_context)

            items = [QueryResultItem.model_validate(r.to_dict()) for r in results]
            query_span.set_attribute("result_count", len(items))
            return QueryResponse(results=items, total=len(items))
        except Exception as e:
            query_span.set_status(StatusCode.ERROR)
            query_span.record_exception(e)
            raise
