"""Push/webhook-based ingestion trigger for real-time adapter events."""

import logging
import threading
from typing import NamedTuple
from context_library.core.pipeline import IngestionPipeline
from context_library.adapters.base import BaseAdapter
from context_library.adapters._watching import FileSystemWatcher
from context_library.domains.base import BaseDomain
from context_library.storage.models import PollStrategy

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

    def __init__(self, pipeline: IngestionPipeline, max_retries: int = 3, drain_interval_sec: float = 5.0) -> None:
        """Initialize the Watcher.

        Args:
            pipeline: IngestionPipeline instance for processing filesystem events
            max_retries: Maximum number of retries for failed push events (default: 3)
            drain_interval_sec: Interval in seconds for periodic retry queue draining (default: 5.0)
        """
        self._pipeline = pipeline
        self._registrations: list[tuple[BaseAdapter, BaseDomain, FileSystemWatcher]] = []
        self._retry_queue: list[FailedPushEvent] = []
        self._retry_queue_lock = threading.Lock()
        self._max_retries = max_retries
        self._drain_interval_sec = drain_interval_sec
        self._drain_thread: threading.Thread | None = None
        self._stop_draining = threading.Event()

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

        Raises:
            ValueError: If the adapter's poll_strategy is not PUSH
        """
        # Validate that adapter is configured for push-based ingestion
        poll_strategy = getattr(adapter, '_poll_strategy', None)
        if poll_strategy is not None and poll_strategy != PollStrategy.PUSH:
            raise ValueError(
                f"Cannot register adapter {adapter.adapter_id} with Watcher: "
                f"poll_strategy is {poll_strategy}, but Watcher only supports PollStrategy.PUSH. "
                f"Use Poller for pull-based sources."
            )

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
                    # Do not continue to handle_webhook if adapter callback fails
                    # The failure may leave adapter state inconsistent (e.g., stale vault cache)
                    return
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
            self._pipeline.ingest(adapter, domain_chunker, source_ref=source_ref)
            return True
        except Exception:
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

    def _drain_loop(self) -> None:
        """Periodically drain the retry queue in a background thread.

        Runs until stop() is called. Flushes the retry queue at regular intervals
        to prevent event loss even if no new events arrive.
        """
        while not self._stop_draining.wait(timeout=self._drain_interval_sec):
            if self.get_retry_queue_size() > 0:
                logger.debug(f"Periodic retry queue drain: {self.get_retry_queue_size()} events in queue")
                self.flush_retry_queue()

    def start(self) -> None:
        """Start all registered FileSystemWatcher instances and periodic retry draining.

        Calls start() on each registered file_watcher to begin monitoring for changes.
        Also starts a background thread that periodically drains the retry queue to
        ensure failed events are not lost if no new events arrive.
        """
        # Start file watchers
        for _, _, file_watcher in self._registrations:
            file_watcher.start()

        # Start periodic drain thread if not already running
        if self._drain_thread is None or not self._drain_thread.is_alive():
            self._stop_draining.clear()
            self._drain_thread = threading.Thread(
                target=self._drain_loop,
                daemon=True,
                name="WatcherDrainThread",
            )
            self._drain_thread.start()
            logger.debug("Started periodic retry queue drain thread")

    def stop(self) -> None:
        """Stop all registered FileSystemWatcher instances and periodic draining.

        Calls stop() on each registered file_watcher to halt monitoring.
        Stops the periodic drain thread and flushes the retry queue before returning
        to ensure no events are lost.
        Safe to call before start() or multiple times (no error).
        """
        # Signal drain thread to stop
        self._stop_draining.set()

        # Wait for drain thread to finish (with timeout as safety measure)
        if self._drain_thread is not None and self._drain_thread.is_alive():
            self._drain_thread.join(timeout=2)
            logger.debug("Stopped periodic retry queue drain thread")

        # Process any remaining queued retry events
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
