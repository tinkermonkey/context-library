"""Polling-based ingestion trigger; manages per-source poll intervals."""

import logging
import threading
from context_library.core.pipeline import IngestionPipeline
from context_library.storage.document_store import DocumentStore
from context_library.adapters.base import BaseAdapter
from context_library.domains.base import BaseDomain

logger = logging.getLogger(__name__)


class SourceErrorTracker:
    """Tracks error state for a single source with escalation levels.

    Implements escalating visibility for consecutive failures:
    - 1-2 failures: Logged at INFO level (transient issues expected)
    - 3-5 failures: Logged at WARNING level (persistent issue, requires investigation)
    - 6+ failures: Logged at ERROR level (critical, source may be permanently broken)
    """

    def __init__(self) -> None:
        """Initialize error tracking."""
        self._consecutive_failures = 0

    def record_failure(self) -> None:
        """Record a failure and increment the consecutive failure count."""
        self._consecutive_failures += 1

    def clear(self) -> None:
        """Clear error tracking on successful ingestion."""
        self._consecutive_failures = 0

    @property
    def consecutive_failures(self) -> int:
        """The number of consecutive failures for this source (read-only)."""
        return self._consecutive_failures

    def should_log_at_error_level(self) -> bool:
        """Return True if failures have escalated to ERROR level (6+ failures)."""
        return self._consecutive_failures >= 6

    def should_log_at_warning_level(self) -> bool:
        """Return True if failures are at WARNING level (3-5 failures)."""
        return 3 <= self._consecutive_failures < 6


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

        Raises:
            ValueError: If tick_interval is not a positive number
        """
        if tick_interval <= 0:
            raise ValueError(
                f"tick_interval must be a positive number, got {tick_interval}"
            )
        self._pipeline = pipeline
        self._document_store = document_store
        self._tick_interval = tick_interval
        self._registered: list[tuple[BaseAdapter, BaseDomain]] = []
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        # Track per-source error state for escalation
        self._error_tracker: dict[str, SourceErrorTracker] = {}
        # Prevent concurrent ingest of the same adapter
        self._ingest_in_progress: dict[str, bool] = {}
        # Track background ingest threads for graceful shutdown
        self._background_threads: set[threading.Thread] = set()
        # Lock for thread-safe management of background threads
        self._threads_lock = threading.Lock()

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
        """Stop the polling background thread and wait for background ingest threads to complete.

        Sets the stop event and waits for the main poller thread to exit via join() with a timeout.
        Also waits for all background ingest threads to complete.
        If threads do not exit within the timeout, logs an error and continues.
        Safe to call before start() or multiple times (no error).
        """
        self._stop_event.set()

        # Stop the main poller thread
        if self._thread is not None:
            self._thread.join(timeout=5.0)
            if self._thread.is_alive():
                logger.error(
                    "Poller: thread did not exit within timeout (5.0s). "
                    "It may still be running a network call. "
                    "Graceful shutdown failed; thread remains alive."
                )
            else:
                # Only clear the reference if the thread actually exited
                self._thread = None

        # Wait for background ingest threads to complete
        with self._threads_lock:
            threads_to_wait = list(self._background_threads)

        for thread in threads_to_wait:
            thread.join(timeout=5.0)
            if thread.is_alive():
                logger.error(
                    "Poller: background ingest thread did not exit within timeout (5.0s). "
                    "It may still be running a network call or database operation."
                )
            else:
                with self._threads_lock:
                    self._background_threads.discard(thread)

    def _run(self) -> None:
        """Main background loop (internal).

        Executes the first tick immediately unless stop_event is already set, then waits
        tick_interval between subsequent ticks. This ensures the poller begins processing
        sources promptly after start() while respecting a concurrent stop() call.
        """
        # Execute first tick immediately unless already stopping
        if not self._stop_event.is_set():
            self._tick()

        # Then loop with tick_interval delay between subsequent ticks
        while not self._stop_event.wait(timeout=self._tick_interval):
            self._tick()

    def _tick(self) -> None:
        """Single polling cycle (internal).

        Queries the document store for sources due for polling and attempts to ingest each one.
        Per-source errors are caught, logged, and do not prevent other sources from being polled.

        Error escalation:
        - Tracks consecutive failures per source
        - 1-2 failures: INFO level (transient issues expected)
        - 3-5 failures: WARNING level (persistent issue)
        - 6+ failures: ERROR level (critical, may be permanently broken)

        Memory management:
        - Prunes error tracker entries for sources no longer due for polling
        - Prevents unbounded growth of _error_tracker dict over time

        CRITICAL: update_last_fetched_at is only called if ingest succeeds. If ingest succeeds
        but update_last_fetched_at fails, the source will be re-polled on the next tick (acceptable).
        If ingest fails, update_last_fetched_at is NOT called, so the source remains due for re-polling
        on the next tick (allowing retry without preventing the scheduler from progressing).
        """
        due_sources = self._document_store.get_sources_due_for_poll()
        due_source_ids = {source["source_id"] for source in due_sources}

        # Clean up error tracker entries for sources no longer due for polling.
        # Note: A source that just succeeded and updated last_fetched_at won't appear in
        # due_sources until its poll interval elapses again, so its error tracker entry will
        # be pruned here. This is the desired behavior since clear() already resets state on success.
        # Entries for removed/deleted sources are also pruned here, allowing failure history
        # to be implicitly forgotten when sources are no longer in the system.
        # (prevents unbounded growth of _error_tracker dict)
        sources_to_remove = set(self._error_tracker.keys()) - due_source_ids
        for source_id in sources_to_remove:
            del self._error_tracker[source_id]

        for source in due_sources:
            source_id = source["source_id"]
            adapter_id = source["adapter_id"]

            # Skip if a background ingest is already in progress for this adapter
            if self._ingest_in_progress.get(adapter_id, False):
                logger.debug(
                    "Poller: skipping source %s; background ingest in progress for adapter %s",
                    source_id,
                    adapter_id,
                )
                continue

            adapter, chunker = self._find_adapter(adapter_id)
            if adapter is None or chunker is None:
                logger.warning(
                    "Poller: no registered adapter found for adapter_id=%s",
                    adapter_id,
                )
                continue

            # Initialize error tracker for this source if needed
            if source_id not in self._error_tracker:
                self._error_tracker[source_id] = SourceErrorTracker()

            try:
                self._pipeline.ingest(adapter, chunker, source_ref=source["origin_ref"])
                # Clear error tracking on successful ingestion
                self._error_tracker[source_id].clear()
            except MemoryError:
                # System-level memory exhaustion is fatal; propagate immediately
                raise
            except Exception as e:
                error_tracker = self._error_tracker[source_id]
                error_msg = f"ingest failed: {e}"
                error_tracker.record_failure()

                # Log at escalated level based on failure count
                if error_tracker.should_log_at_error_level():
                    logger.error(
                        "Poller: source %s has failed %d times (ERROR level): %s",
                        source_id,
                        error_tracker.consecutive_failures,
                        error_msg,
                    )
                elif error_tracker.should_log_at_warning_level():
                    logger.warning(
                        "Poller: source %s has failed %d times (WARNING level): %s",
                        source_id,
                        error_tracker.consecutive_failures,
                        error_msg,
                    )
                else:
                    logger.info(
                        "Poller: source %s ingestion attempt failed (transient): %s",
                        source_id,
                        error_msg,
                    )
                continue

            # Only update last_fetched_at if ingest succeeded
            try:
                self._document_store.update_last_fetched_at(source_id)
            except Exception as e:
                logger.exception(
                    "Poller: failed to update last_fetched_at for source %s: %s",
                    source_id,
                    e,
                )

    def trigger_immediate_ingest(self, adapter_id: str) -> bool:
        """Trigger an immediate, one-shot ingest run for a specific adapter.

        Finds the registered (adapter, chunker) pair for the given adapter_id and
        schedules all sources registered to that adapter for immediate re-ingestion,
        bypassing the normal poll-interval gate. The ingest runs asynchronously
        in a background thread, allowing the HTTP response to return immediately.

        Prevents concurrent ingest of the same adapter using a busy flag. If an ingest
        is already in progress for this adapter, returns False.

        Background threads are tracked and joined during shutdown to ensure graceful
        cleanup. Failures in the background thread are logged but do not propagate.

        Args:
            adapter_id: The adapter ID to trigger ingest for

        Returns:
            True if a background ingest thread was successfully spawned, False if:
            - The adapter is not registered with the poller
            - The poller is stopped or not running
            - No sources are registered to the adapter
            - An ingest is already in progress for this adapter (race condition prevention)
        """
        # Return False if poller is stopped or not started
        if self._thread is None or not self._thread.is_alive() or self._stop_event.is_set():
            return False

        # Return False if an ingest is already in progress for this adapter
        if self._ingest_in_progress.get(adapter_id, False):
            logger.warning(
                "trigger_immediate_ingest: ingest already in progress for adapter %s",
                adapter_id,
            )
            return False

        # Find the adapter
        adapter, chunker = self._find_adapter(adapter_id)
        if adapter is None or chunker is None:
            return False

        # Get all sources for this adapter
        sources = self._document_store.get_sources_for_adapter(adapter_id)
        if not sources:
            return False

        # Mark this adapter as having an ingest in progress
        self._ingest_in_progress[adapter_id] = True

        # Spawn a background thread to process sources immediately (non-blocking)
        def process_sources() -> None:
            try:
                for source in sources:
                    source_id = source["source_id"]
                    try:
                        self._pipeline.ingest(
                            adapter, chunker, source_ref=source["origin_ref"]
                        )
                        # Update last_fetched_at on successful ingest
                        try:
                            self._document_store.update_last_fetched_at(source_id)
                        except Exception as e:
                            logger.exception(
                                "trigger_immediate_ingest: failed to update last_fetched_at "
                                "for source %s: %s",
                                source_id,
                                e,
                            )
                    except MemoryError:
                        # System-level memory exhaustion is fatal; propagate immediately
                        raise
                    except Exception as e:
                        logger.exception(
                            "trigger_immediate_ingest: ingest failed for source %s: %s",
                            source_id,
                            e,
                        )
            finally:
                # Always clear the in-progress flag and remove thread from tracking
                self._ingest_in_progress[adapter_id] = False
                with self._threads_lock:
                    self._background_threads.discard(threading.current_thread())

        # Use non-daemon threads and track them for graceful shutdown
        thread = threading.Thread(target=process_sources, daemon=False)
        with self._threads_lock:
            self._background_threads.add(thread)
        thread.start()

        return True

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
