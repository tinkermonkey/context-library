"""Webhook ingestion endpoint."""

import asyncio
import logging
import secrets

from fastapi import APIRouter, HTTPException, Query, Request

from context_library.core.entity_linker import EntityLinker
from context_library.core.exceptions import AllSourcesFailedError
from context_library.domains.registry import get_domain_chunker
from context_library.server.schemas import (
    AppleAdapterResult,
    AppleIngestResponse,
    IngestError,
    WebhookIngestRequest,
    WebhookIngestResponse,
)
from context_library.server.webhook_adapter import WebhookAdapter
from context_library.storage.models import Domain, NormalizedContent

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post("/webhooks/ingest", response_model=WebhookIngestResponse)
async def webhook_ingest(
    payload: WebhookIngestRequest, request: Request
) -> WebhookIngestResponse:
    pipeline = request.app.state.pipeline
    config = request.app.state.config

    # Verify webhook secret if configured (constant-time comparison)
    if config.webhook_secret:
        auth = request.headers.get("Authorization", "")
        expected = f"Bearer {config.webhook_secret}"
        if not secrets.compare_digest(auth, expected):
            raise HTTPException(status_code=401, detail="Invalid webhook secret")

    # Build NormalizedContent items from the payload
    items = [
        NormalizedContent(
            markdown=item.markdown,
            source_id=item.source_id,
            structural_hints=item.structural_hints,
            normalizer_version=payload.normalizer_version,
        )
        for item in payload.items
    ]

    # Create passthrough adapter
    adapter = WebhookAdapter(
        adapter_id=payload.adapter_id,
        domain=payload.domain,
        normalizer_version=payload.normalizer_version,
        items=items,
    )

    domain_chunker = get_domain_chunker(payload.domain)

    try:
        result = await asyncio.to_thread(pipeline.ingest, adapter, domain_chunker)
    except AllSourcesFailedError as e:
        raise HTTPException(status_code=500, detail=str(e))
    except Exception as e:
        logger.error("Unexpected error during webhook ingestion: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=f"Ingestion failed: {type(e).__name__}: {e}")

    # Run entity linking pass if People domain ingestion completed successfully
    if payload.domain == Domain.PEOPLE and result["sources_failed"] == 0:
        try:
            linker = EntityLinker(document_store=request.app.state.document_store)
            new_links = await asyncio.to_thread(linker.run)
            logger.info("Entity linking pass created %d new links", new_links)
        except Exception as e:
            logger.error("Entity linking pass failed: %s", e, exc_info=True)
            # Entity linking is not critical to ingestion success, so we log but don't fail

    return WebhookIngestResponse(
        status="ok" if result["sources_failed"] == 0 else "partial",
        sources_processed=result["sources_processed"],
        sources_failed=result["sources_failed"],
        chunks_added=result["chunks_added"],
        chunks_removed=result["chunks_removed"],
        chunks_unchanged=result["chunks_unchanged"],
        errors=[IngestError(**e) for e in result["errors"]],
    )


@router.post("/ingest/helpers", response_model=AppleIngestResponse)
async def helper_ingest(
    request: Request,
    since: str | None = Query(default=None, description="ISO 8601 cursor; only return items modified after this time"),
    full: bool = Query(default=False, description="Force a full pull, ignoring the since cursor"),
    adapter_id: str | None = Query(default=None, description="Run only this adapter (matches adapter_id prefix)"),
) -> AppleIngestResponse:
    """Pull and ingest content from all configured helper adapters."""
    pipeline = request.app.state.pipeline
    config = request.app.state.config
    helper_adapters = request.app.state.helper_adapters

    if config.webhook_secret:
        auth = request.headers.get("Authorization", "")
        expected = f"Bearer {config.webhook_secret}"
        if not secrets.compare_digest(auth, expected):
            raise HTTPException(status_code=401, detail="Invalid webhook secret")

    if not helper_adapters:
        raise HTTPException(status_code=503, detail="No helper adapters configured (set CTX_HELPER_URL and CTX_HELPER_API_KEY)")

    if adapter_id:
        helper_adapters = [a for a in helper_adapters if a.adapter_id == adapter_id]
        if not helper_adapters:
            raise HTTPException(status_code=404, detail=f"No configured adapter with adapter_id={adapter_id!r}")

    if since and not full:
        try:
            from datetime import datetime
            datetime.fromisoformat(since)
        except ValueError:
            raise HTTPException(status_code=422, detail=f"Invalid 'since' value: {since!r} — expected ISO 8601 timestamp")

    source_ref = "" if full else (since or "")

    results = []
    for adapter in helper_adapters:
        domain_chunker = get_domain_chunker(adapter.domain)
        try:
            result = await asyncio.to_thread(pipeline.ingest, adapter, domain_chunker, source_ref)
            results.append(AppleAdapterResult(
                adapter_id=adapter.adapter_id,
                status="ok" if result["sources_failed"] == 0 else "partial",
                sources_processed=result["sources_processed"],
                sources_failed=result["sources_failed"],
                chunks_added=result["chunks_added"],
                chunks_removed=result["chunks_removed"],
                chunks_unchanged=result["chunks_unchanged"],
                errors=[IngestError(**e) for e in result["errors"]],
            ))

            # Run entity linking pass if People domain ingestion completed successfully
            if adapter.domain == Domain.PEOPLE and result["sources_failed"] == 0:
                try:
                    linker = EntityLinker(document_store=request.app.state.document_store)
                    new_links = await asyncio.to_thread(linker.run)
                    logger.info("Entity linking pass for %s created %d new links", adapter.adapter_id, new_links)
                except Exception as e:
                    logger.error("Entity linking pass for %s failed: %s", adapter.adapter_id, e, exc_info=True)
                    # Entity linking is not critical to ingestion success, so we log but don't fail
        except Exception as e:
            logger.error("Apple adapter %s failed: %s", adapter.adapter_id, e, exc_info=True)
            results.append(AppleAdapterResult(
                adapter_id=adapter.adapter_id,
                status="error",
                sources_processed=0,
                sources_failed=1,
                chunks_added=0,
                chunks_removed=0,
                chunks_unchanged=0,
                errors=[IngestError(source_id="", error_type=type(e).__name__, message=str(e))],
            ))

    return AppleIngestResponse(adapters_run=len(results), results=results)
