"""Passthrough adapter for webhook-delivered content.

Wraps pre-normalized content received via webhook POST and presents it
as a standard BaseAdapter to the IngestionPipeline. The pipeline sees it
as just another adapter — no special-casing required.
"""

from typing import Iterator

from context_library.adapters.base import BaseAdapter
from context_library.storage.models import Domain, NormalizedContent, PollStrategy


class WebhookAdapter(BaseAdapter):
    """Adapter that yields pre-constructed NormalizedContent from a webhook payload.

    Unlike pull-based adapters that call external APIs in fetch(), this adapter
    simply yields the content it was constructed with. One instance per webhook
    request — instantiate, pass to pipeline.ingest(), discard.
    """

    def __init__(
        self,
        adapter_id: str,
        domain: Domain,
        normalizer_version: str,
        items: list[NormalizedContent],
    ) -> None:
        self._adapter_id = adapter_id
        self._domain = domain
        self._normalizer_version = normalizer_version
        self._items = items
        self._poll_strategy = PollStrategy.WEBHOOK

    def fetch(self, source_ref: str) -> Iterator[NormalizedContent]:
        yield from self._items

    @property
    def adapter_id(self) -> str:
        return self._adapter_id

    @property
    def domain(self) -> Domain:
        return self._domain

    @property
    def normalizer_version(self) -> str:
        return self._normalizer_version

    @property
    def poll_strategy(self) -> PollStrategy:
        return self._poll_strategy
