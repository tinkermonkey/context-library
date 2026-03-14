"""Adapter inspection endpoints."""

import asyncio

from fastapi import APIRouter, HTTPException, Request

from context_library.server.schemas import AdapterListResponse, AdapterResponse

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
            **{
                "_links": {
                    "self": f"/adapters/{c.adapter_id}",
                    "sources": f"/sources?adapter_id={c.adapter_id}",
                }
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
        **{
            "_links": {
                "self": f"/adapters/{config.adapter_id}",
                "sources": f"/sources?adapter_id={config.adapter_id}",
            }
        },
    )
