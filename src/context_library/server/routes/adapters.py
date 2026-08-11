"""Adapter inspection and management endpoints."""

import asyncio
import logging
import sqlite3

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse

from context_library.scheduler.exceptions import (
    AdapterNotRegisteredError,
    IngestAlreadyInProgressError,
    NoSourcesError,
    PollerNotRunningError,
)
from context_library.server.schemas import (
    AdapterListResponse,
    AdapterResetResponse,
    AdapterResponse,
    HelperResetInfo,
    LibraryResetInfo,
)
from context_library.telemetry.tracer import get_status_code, get_tracer

try:
    import httpx
except ImportError:
    httpx = None  # type: ignore[assignment]

logger = logging.getLogger(__name__)
tracer = get_tracer(__name__)
StatusCode = get_status_code()

router = APIRouter(prefix="/adapters", tags=["adapters"])


@router.get("", response_model=AdapterListResponse)
async def list_adapters(request: Request) -> AdapterListResponse:
    ds = request.app.state.document_store
    configs = await asyncio.to_thread(ds.list_adapters)
    adapters = [
        AdapterResponse(
            adapter_id=c.adapter_id,
            adapter_type=c.adapter_type,
            domain=c.domain.value,
            normalizer_version=c.normalizer_version,
            config=c.config,
            _links={
                    "self": f"/adapters/{c.adapter_id}",
                    "sources": f"/sources?adapter_id={c.adapter_id}",
                },
        )
        for c in configs
    ]
    return AdapterListResponse(adapters=adapters, total=len(adapters))


@router.get("/{adapter_id}", response_model=AdapterResponse)
async def get_adapter(adapter_id: str, request: Request) -> AdapterResponse:
    ds = request.app.state.document_store
    config = await asyncio.to_thread(ds.get_adapter, adapter_id)
    if config is None:
        raise HTTPException(status_code=404, detail=f"Adapter '{adapter_id}' not found")
    return AdapterResponse(
        adapter_id=config.adapter_id,
        adapter_type=config.adapter_type,
        domain=config.domain.value,
        normalizer_version=config.normalizer_version,
        config=config.config,
        _links={
                "self": f"/adapters/{config.adapter_id}",
                "sources": f"/sources?adapter_id={config.adapter_id}",
            },
    )


@router.post("/{adapter_id}/reset", response_model=AdapterResetResponse)
async def reset_adapter(adapter_id: str, request: Request):
    """Reset an adapter: reset helper state, retire library data, and trigger re-ingest.

    Orchestrates a coordinated reset across six steps in strict abort-on-failure order:
    1. Validate adapter exists (404 if not found)
    2. Reset adapter state in helper service (502 if fails — do NOT proceed to step 3)
    3. Retire all chunks and reset fetch state in library (500 if fails)
    4. Trigger immediate re-ingestion (may fail if poller unavailable — non-fatal)
    5. Determine if re-ingestion is needed by checking source poll strategies
    6. Return response (200 on success, 207 if library reset succeeded but re-ingestion failed)

    Critical ordering: Steps 1-3 use abort-on-failure semantics (earlier failures prevent
    later steps). Step 4 failures are non-fatal after Step 3 succeeds — library data is
    retired but re-ingestion may be deferred or require manual trigger if poller is unavailable.
    """
    ds = request.app.state.document_store
    poller = request.app.state.poller
    helper_adapters = request.app.state.helper_adapters

    with tracer.start_as_current_span("adapter.reset") as span:
        span.set_attribute("adapter.id", adapter_id)

        try:
            # Step 1: Validate adapter exists
            span.add_event("step.validate_adapter")
            adapter_config = await asyncio.to_thread(ds.get_adapter, adapter_id)
            if adapter_config is None:
                raise HTTPException(status_code=404, detail=f"Adapter '{adapter_id}' not found")

            # Step 2: Call adapter.reset() via the adapter registry
            # Find the adapter instance from helper_adapters
            adapter = None
            for a in helper_adapters:
                if a.adapter_id == adapter_id:
                    adapter = a
                    break

            errors: list[str] = []
            helper_reset_ok: bool | None = None  # True=success, False=failure, None=not applicable
            cleared: list[str] = []

            span.add_event("step.reset_helper_cursor")
            if adapter is not None:
                try:
                    reset_result = await asyncio.to_thread(adapter.reset)
                    if reset_result.ok:
                        helper_reset_ok = True
                        cleared = reset_result.cleared
                    else:
                        # Helper reset failed
                        error_detail = "; ".join(reset_result.errors) if reset_result.errors else "Reset failed"
                        raise HTTPException(
                            status_code=502,
                            detail=f"Helper reset failed: {error_detail}"
                        )
                except HTTPException:
                    # Re-raise HTTPException (our 502 error)
                    raise
                except Exception as e:  # noqa: BLE001
                    # Distinguish between legitimate network errors (502) and internal bugs (500)
                    is_network_error = False
                    if httpx is not None:
                        is_network_error = isinstance(e, (httpx.HTTPStatusError, httpx.RequestError))

                    status_code = 502 if is_network_error else 500
                    raise HTTPException(
                        status_code=status_code,
                        detail=f"Helper reset error: {type(e).__name__}: {e}"
                    )
            else:
                # Adapter not in helper_adapters (may be webhook or other non-helper adapter)
                # For non-helper adapters, reset is not applicable; ok=None explicitly indicates this
                logger.info("Adapter %s not in helper adapters, skipping helper reset", adapter_id)
                helper_reset_ok = None

            # Step 3: Call document_store.reset_adapter()
            span.add_event("step.clear_library_state")
            library_reset = False
            sources_reset = None
            chunks_retired = None
            try:
                library_result = await asyncio.to_thread(ds.reset_adapter, adapter_id)
                library_reset = True
                sources_reset = library_result["sources_reset"]
                chunks_retired = library_result["chunks_retired"]
                logger.info(
                    "Reset adapter %s: %d sources, %d chunks retired",
                    adapter_id,
                    sources_reset,
                    chunks_retired,
                )
            except Exception as e:
                error_msg = f"Library reset error: {type(e).__name__}: {e}"
                if helper_reset_ok is True:
                    error_msg += " (Note: helper was already reset)"
                logger.exception("Reset adapter %s failed at step 3", adapter_id)
                raise HTTPException(status_code=500, detail=error_msg)

            # Step 4: Trigger immediate re-ingestion
            span.add_event("step.reingest_start")
            reingestion_triggered = False
            try:
                reingestion_triggered = poller.trigger_immediate_ingest(adapter_id)
            except PollerNotRunningError:
                errors.append("Poller is not running; re-ingestion will not occur immediately")
                logger.warning("Reset adapter %s: re-ingestion trigger failed (poller not running)", adapter_id)
            except AdapterNotRegisteredError:
                errors.append("Adapter is not registered with poller; re-ingestion will not occur immediately")
                logger.warning("Reset adapter %s: re-ingestion trigger failed (adapter not registered)", adapter_id)
            except NoSourcesError:
                errors.append("No sources found for adapter; re-ingestion will not occur immediately")
                logger.warning("Reset adapter %s: re-ingestion trigger failed (no sources)", adapter_id)
            except IngestAlreadyInProgressError:
                errors.append("Ingest is already in progress for adapter; re-ingestion will not occur immediately")
                logger.warning("Reset adapter %s: re-ingestion trigger failed (ingest already in progress)", adapter_id)
            except sqlite3.OperationalError as e:
                error_msg = f"Database error while triggering re-ingestion: {e}"
                errors.append(error_msg)
                logger.warning("Reset adapter %s: re-ingestion trigger failed (DB error): %s", adapter_id, e)
            except Exception as e:  # noqa: BLE001
                error_msg = f"Unexpected error while triggering re-ingestion: {type(e).__name__}: {e}"
                errors.append(error_msg)
                logger.warning("Reset adapter %s: re-ingestion trigger failed (unexpected error): %s", adapter_id, e)

            # Step 5: Determine if re-ingestion is needed
            needs_poller_reingestion = False
            if library_reset:
                needs_poller_reingestion = await asyncio.to_thread(ds.has_non_push_sources, adapter_id)

            span.set_attribute("adapter.reset.sources_reset", sources_reset or 0)
            span.set_attribute("adapter.reset.chunks_retired", chunks_retired or 0)
            span.set_attribute("adapter.reset.reingestion_triggered", reingestion_triggered)

            # Step 6: Return response
            response = AdapterResetResponse(
                adapter_id=adapter_id,
                helper_reset=HelperResetInfo(ok=helper_reset_ok, cleared=cleared),
                library_reset=LibraryResetInfo(sources_reset=sources_reset, chunks_retired=chunks_retired),
                reingestion_triggered=reingestion_triggered,
                errors=errors,
            )

            if not reingestion_triggered and library_reset and needs_poller_reingestion:
                return JSONResponse(
                    status_code=207,
                    content=response.model_dump(),
                )

            return response

        except HTTPException:
            span.set_status(StatusCode.ERROR)
            raise
        except Exception as e:
            span.record_exception(e)
            span.set_status(StatusCode.ERROR)
            raise
