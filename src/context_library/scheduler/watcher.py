"""Push/webhook-based ingestion trigger for real-time adapter events."""

import logging
from context_library.core.pipeline import IngestionPipeline
from context_library.adapters.base import BaseAdapter
from context_library.adapters._watching import FileSystemWatcher
from context_library.domains.base import BaseDomain

logger = logging.getLogger(__name__)


class Watcher:
    """Background scheduler that routes filesystem push events through the ingestion pipeline.

    Manages FileSystemWatcher instances for each registered adapter and routes filesystem
    events through handle_webhook() to trigger ingestion. Provides clean lifecycle
    management via start/stop.

    Key features:
    - Routes filesystem events from FileSystemWatcher through the ingestion pipeline
    - Isolates per-event failures — one failed event doesn't prevent others from processing
    - Each event is routed independently via handle_webhook()
    - Clean start/stop lifecycle for managing watchers
    """

    def __init__(self, pipeline: IngestionPipeline) -> None:
        """Initialize the Watcher.

        Args:
            pipeline: IngestionPipeline instance for processing filesystem events
        """
        self._pipeline = pipeline
        self._registrations: list[tuple[BaseAdapter, BaseDomain, FileSystemWatcher]] = []

    def register(
        self,
        adapter: BaseAdapter,
        domain_chunker: BaseDomain,
        file_watcher: FileSystemWatcher,
    ) -> None:
        """Register a FileSystemWatcher with an adapter and domain chunker.

        Creates a callback closure that maps FileSystemWatcher events to handle_webhook()
        calls, establishing the connection between filesystem events and the ingestion pipeline.

        Args:
            adapter: BaseAdapter instance providing content
            domain_chunker: BaseDomain instance for chunking
            file_watcher: FileSystemWatcher instance for monitoring filesystem changes
        """
        # Create closure that maps FileEvent to handle_webhook call
        def _on_event(event):
            self.handle_webhook(
                source_ref=str(event.path),
                adapter=adapter,
                domain_chunker=domain_chunker,
            )

        file_watcher._callback = _on_event
        self._registrations.append((adapter, domain_chunker, file_watcher))

    def handle_webhook(
        self,
        source_ref: str,
        adapter: BaseAdapter,
        domain_chunker: BaseDomain,
    ) -> None:
        """Handle a webhook event from a filesystem watcher.

        Entry point for push events that routes them through the ingestion pipeline.
        Per-event failures are caught and logged without propagating.

        Args:
            source_ref: Reference to the changed source (typically file path)
            adapter: BaseAdapter instance providing content
            domain_chunker: BaseDomain instance for chunking
        """
        try:
            self._pipeline.ingest(adapter, domain_chunker)
        except Exception:
            logger.exception(
                "Watcher: failed to handle webhook for source_ref %s", source_ref
            )

    def start(self) -> None:
        """Start all registered FileSystemWatcher instances.

        Calls start() on each registered file_watcher to begin monitoring for changes.
        """
        for _, _, file_watcher in self._registrations:
            file_watcher.start()

    def stop(self) -> None:
        """Stop all registered FileSystemWatcher instances.

        Calls stop() on each registered file_watcher to halt monitoring.
        Safe to call before start() or multiple times (no error).
        """
        for _, _, file_watcher in self._registrations:
            file_watcher.stop()
