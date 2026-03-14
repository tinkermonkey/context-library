"""Webhook ingestion endpoint."""

import asyncio
import logging
import secrets

from fastapi import APIRouter, HTTPException, Request

from context_library.core.exceptions import AllSourcesFailedError
from context_library.domains.registry import get_domain_chunker
from context_library.server.schemas import IngestError, WebhookIngestRequest, WebhookIngestResponse
from context_library.server.webhook_adapter import WebhookAdapter
from context_library.storage.models import NormalizedContent

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

    return WebhookIngestResponse(
        status="ok" if result["sources_failed"] == 0 else "partial",
        sources_processed=result["sources_processed"],
        sources_failed=result["sources_failed"],
        chunks_added=result["chunks_added"],
        chunks_removed=result["chunks_removed"],
        chunks_unchanged=result["chunks_unchanged"],
        errors=[IngestError(**e) for e in result["errors"]],
    )
