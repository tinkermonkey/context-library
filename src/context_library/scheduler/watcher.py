"""Push/webhook-based ingestion trigger for real-time adapter events."""

import logging
import threading
from typing import NamedTuple
from context_library.core.pipeline import IngestionPipeline
from context_library.adapters.base import BaseAdapter
from context_library.adapters._watching import FileSystemWatcher
from context_library.domains.base import BaseDomain

logger = logging.getLogger(__name__)


class FailedPushEvent(NamedTuple):
    """Record of a failed push event for retry."""
    source_ref: str
    adapter: BaseAdapter
    domain_chunker: BaseDomain
    retry_count: int = 0


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

    def __init__(self, pipeline: IngestionPipeline, max_retries: int = 3) -> None:
        """Initialize the Watcher.

        Args:
            pipeline: IngestionPipeline instance for processing filesystem events
            max_retries: Maximum number of retries for failed push events (default: 3)
        """
        self._pipeline = pipeline
        self._registrations: list[tuple[BaseAdapter, BaseDomain, FileSystemWatcher]] = []
        self._retry_queue: list[FailedPushEvent] = []
        self._retry_queue_lock = threading.Lock()
        self._max_retries = max_retries

    def register(
        self,
        adapter: BaseAdapter,
        domain_chunker: BaseDomain,
        file_watcher: FileSystemWatcher,
    ) -> None:
        """Register a FileSystemWatcher with an adapter and domain chunker.

        Creates a callback closure that maps FileSystemWatcher events to handle_webhook()
        calls, establishing the connection between filesystem events and the ingestion pipeline.
        Preserves any existing adapter-internal callback by chaining it before the webhook handler.

        Args:
            adapter: BaseAdapter instance providing content
            domain_chunker: BaseDomain instance for chunking
            file_watcher: FileSystemWatcher instance for monitoring filesystem changes
        """
        # Preserve any existing callback (e.g., ObsidianAdapter._on_file_changed for cache invalidation)
        original_callback = getattr(file_watcher, '_callback', None)

        # Create closure that chains original callback + handle_webhook
        def _on_event(event):
            # Call adapter's own callback first (e.g., vault cache invalidation)
            if original_callback is not None:
                try:
                    original_callback(event)
                except Exception as e:
                    logger.error(
                        f"Error in adapter's internal callback for {event.path}: {e}",
                        exc_info=True,
                    )
            # Then route through ingestion pipeline
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
        retry_count: int = 0,
    ) -> bool:
        """Handle a webhook event from a filesystem watcher.

        Entry point for push events that routes them through the ingestion pipeline.
        Per-event failures are queued for retry. Returns True if successful, False otherwise.

        Args:
            source_ref: Reference to the changed source (typically file path)
            adapter: BaseAdapter instance providing content
            domain_chunker: BaseDomain instance for chunking
            retry_count: Internal counter for retry attempts (not meant to be set by callers).
                         This is an implementation detail and should not be set by external callers.

        Returns:
            True if ingestion succeeded, False if failed and queued for retry
        """
        try:
            self._pipeline.ingest(adapter, domain_chunker)
            return True
        except Exception as e:
            logger.exception(
                "Watcher: failed to handle webhook for source_ref %s (retry %d/%d)",
                source_ref,
                retry_count,
                self._max_retries,
            )
            # Queue for retry if we haven't exceeded max retries
            if retry_count < self._max_retries:
                with self._retry_queue_lock:
                    self._retry_queue.append(
                        FailedPushEvent(
                            source_ref=source_ref,
                            adapter=adapter,
                            domain_chunker=domain_chunker,
                            retry_count=retry_count + 1,
                        )
                    )
                logger.debug(
                    f"Queued {source_ref} for retry (attempt {retry_count + 1}/{self._max_retries})"
                )
            else:
                logger.error(
                    f"Watcher: permanently dropped event for {source_ref} after {self._max_retries} retries"
                )
            return False

    def flush_retry_queue(self) -> None:
        """Process all queued retry events.

        Attempts to re-ingest any events that previously failed. Can be called
        periodically or as part of stop() to ensure events aren't permanently lost.

        NOTE: Retries are executed immediately with no delay or backoff. If the underlying
        failure is transient (e.g., network timeout, temporary resource exhaustion), immediate
        retry may not succeed. For persistent failures, events will be discarded after
        max_retries is exceeded. This is a best-effort mechanism suitable for handling
        application-level failures in the ingestion pipeline rather than transient I/O errors.
        """
        with self._retry_queue_lock:
            if not self._retry_queue:
                return
            original_queue = self._retry_queue
            self._retry_queue = []

        for failed_event in original_queue:
            success = self.handle_webhook(
                source_ref=failed_event.source_ref,
                adapter=failed_event.adapter,
                domain_chunker=failed_event.domain_chunker,
                retry_count=failed_event.retry_count,
            )
            if not success:
                # Event was re-queued for another retry
                pass

        with self._retry_queue_lock:
            if self._retry_queue:
                logger.debug(
                    f"Retry queue still has {len(self._retry_queue)} events after flush"
                )

    def get_retry_queue_size(self) -> int:
        """Return the current number of events in the retry queue."""
        with self._retry_queue_lock:
            return len(self._retry_queue)

    def start(self) -> None:
        """Start all registered FileSystemWatcher instances.

        Calls start() on each registered file_watcher to begin monitoring for changes.
        """
        for _, _, file_watcher in self._registrations:
            file_watcher.start()

    def stop(self) -> None:
        """Stop all registered FileSystemWatcher instances.

        Calls stop() on each registered file_watcher to halt monitoring.
        Flushes the retry queue before returning to ensure no events are lost.
        Safe to call before start() or multiple times (no error).
        """
        # First, try to process any queued retry events
        self.flush_retry_queue()

        # Then stop all file watchers
        for _, _, file_watcher in self._registrations:
            file_watcher.stop()

        # Final flush in case any retried events were added to queue
        if self._retry_queue:
            logger.warning(
                f"Watcher.stop(): {len(self._retry_queue)} events still in retry queue "
                f"(max retries exceeded)"
            )
