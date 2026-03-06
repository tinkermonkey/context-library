"""Polling-based ingestion trigger; manages per-source poll intervals."""

import logging
import threading
from context_library.core.pipeline import IngestionPipeline
from context_library.storage.document_store import DocumentStore
from context_library.adapters.base import BaseAdapter
from context_library.domains.base import BaseDomain

logger = logging.getLogger(__name__)


class Poller:
    """Background scheduler that periodically polls pull-based sources for updates.

    Manages a background thread that checks for sources due for re-ingestion based on
    their configured poll intervals. Provides clean lifecycle management via start/stop.

    Key features:
    - Reads poll_interval_sec and last_fetched_at from DocumentStore to identify due sources
    - Delegates to IngestionPipeline which invokes adapter.fetch() for each due source
    - Updates last_fetched_at after successful ingestion
    - Isolates per-source failures — one failing source doesn't prevent others from being polled
    - Only processes sources with poll_strategy = 'pull'
    - Uses a single background threading.Thread with tick-based loop
    - Clean shutdown via threading.Event
    """

    def __init__(
        self,
        pipeline: IngestionPipeline,
        document_store: DocumentStore,
        tick_interval: float = 60.0,
    ) -> None:
        """Initialize the Poller.

        Args:
            pipeline: IngestionPipeline instance for processing fetched content
            document_store: DocumentStore instance for querying poll metadata
            tick_interval: Time in seconds between poll cycles (default 60.0)
        """
        self._pipeline = pipeline
        self._document_store = document_store
        self._tick_interval = tick_interval
        self._registered: list[tuple[BaseAdapter, BaseDomain]] = []
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None

    def register(self, adapter: BaseAdapter, domain_chunker: BaseDomain) -> None:
        """Register an adapter and domain chunker for polling.

        Adds the adapter/chunker pair to the internal registry. When start() is called,
        the poller will invoke ingest(adapter, chunker) for sources managed by this adapter.

        Args:
            adapter: BaseAdapter instance providing content
            domain_chunker: BaseDomain instance for chunking
        """
        self._registered.append((adapter, domain_chunker))

    def start(self) -> None:
        """Start the polling background thread.

        Spawns a daemon thread that runs the tick loop. The thread will periodically
        query the document store for sources due for polling and ingest them.

        Safe to call multiple times (subsequent calls are no-ops if thread is already running).
        """
        if self._thread is not None and self._thread.is_alive():
            return

        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        """Stop the polling background thread.

        Sets the stop event and waits for the thread to exit via join().
        Safe to call before start() or multiple times (no error).
        """
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join()
            self._thread = None

    def _run(self) -> None:
        """Main background loop (internal)."""
        while not self._stop_event.wait(timeout=self._tick_interval):
            self._tick()

    def _tick(self) -> None:
        """Single polling cycle (internal).

        Queries the document store for sources due for polling and attempts to ingest each one.
        Per-source errors are caught, logged, and do not prevent other sources from being polled.
        """
        due_sources = self._document_store.get_sources_due_for_poll()
        for source in due_sources:
            adapter, chunker = self._find_adapter(source["adapter_id"])
            if adapter is None:
                logger.warning(
                    "Poller: no registered adapter found for adapter_id=%s",
                    source["adapter_id"],
                )
                continue

            try:
                self._pipeline.ingest(adapter, chunker)
                self._document_store.update_last_fetched_at(source["source_id"])
            except Exception:
                logger.exception(
                    "Poller: failed to ingest source %s", source["source_id"]
                )

    def _find_adapter(
        self, adapter_id: str
    ) -> tuple[BaseAdapter | None, BaseDomain | None]:
        """Find a registered adapter by adapter_id (internal).

        Args:
            adapter_id: The adapter ID to look up

        Returns:
            Tuple of (adapter, chunker) if found, otherwise (None, None)
        """
        for adapter, chunker in self._registered:
            if adapter.adapter_id == adapter_id:
                return adapter, chunker
        return None, None
