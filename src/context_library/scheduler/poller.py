"""Polling-based ingestion trigger; schedules registered PULL adapters per-adapter."""

import logging
import threading
import time
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from context_library.telemetry.tracer import get_tracer, get_status_code
from context_library import telemetry as tel
from context_library.core.pipeline import IngestionPipeline
from context_library.storage.document_store import DocumentStore
from context_library.adapters.base import BaseAdapter
from context_library.domains.base import BaseDomain
from context_library.scheduler.exceptions import (
    PollerNotRunningError,
    AdapterNotRegisteredError,
    IngestAlreadyInProgressError,
)

logger = logging.getLogger(__name__)
tracer = get_tracer(__name__)
StatusCode = get_status_code()


def _is_programming_error(exc: Exception) -> bool:
    """Detect programming bugs that should escalate to ERROR level immediately.

    Programming errors are indicative of bugs in the code (adapter, domain, pipeline)
    rather than transient network or system issues. These should be surfaced at ERROR
    level immediately, not after 6+ retries.

    Examples:
    - TypeError: Wrong argument type passed to a function
    - AttributeError: Accessing a non-existent attribute (e.g., missing adapter method)
    - KeyError: Missing key in dictionary (e.g., missing field in normalized content)
    - IndexError: Accessing out-of-bounds list index
    - ValueError: Invalid value for a function parameter
    - NotImplementedError: Method not implemented
    - AssertionError: Assertion failed in code

    Transient errors (retried normally):
    - Network errors (httpx, requests, urllib)
    - Database errors (sqlite3.OperationalError for lock/I/O)
    - MemoryError (already handled separately)
    """
    error_types = (
        TypeError,
        AttributeError,
        KeyError,
        IndexError,
        ValueError,
        NotImplementedError,
        AssertionError,
    )
    return isinstance(exc, error_types)


@dataclass
class IngestResult:
    """Result of a background ingest operation.

    Tracks success/failure counts and the time the ingest completed.
    Per-source exceptions are logged but not stored (to avoid keeping references
    to large error objects in memory).
    """

    adapter_id: str
    sources_attempted: int = 0
    sources_succeeded: int = 0
    sources_failed: int = 0
    completed_at: Optional[datetime] = None
    had_programming_errors: bool = False  # True if any programming errors were detected

    @property
    def overall_success(self) -> bool:
        """True if all sources succeeded (zero failures)."""
        return self.sources_attempted > 0 and self.sources_failed == 0

    @property
    def partial_success(self) -> bool:
        """True if some sources succeeded but not all."""
        return self.sources_succeeded > 0 and self.sources_failed > 0


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
    """Background scheduler that periodically polls registered PULL adapters.

    Manages a background thread that runs one ingest per registered adapter when
    that adapter's poll interval has elapsed. Provides clean lifecycle management
    via start/stop.

    Scheduling is per-adapter, not per-source: helper adapters drain all of their
    changed sources in a single fetch() from their own persisted cursor, so the
    unit of schedulable work is the adapter. (An earlier design scheduled from
    sources.poll_interval_sec rows, but nothing ever populated that column, so no
    source was ever due and registered adapters were never polled. Per-adapter
    scheduling also bootstraps adapters that have no source rows yet.)

    Key features:
    - Polls each registered adapter every poll_interval_sec (adapter attribute,
      defaulting to the poller tick interval) after its last successful run
    - Delegates to IngestionPipeline (adapter.fetch() drains from the adapter's
      own cursor) and calls adapter.ack() after the pipeline commits
    - Isolates per-adapter failures — one failing adapter doesn't prevent others
      from being polled; failures retry on the next tick with escalating logging
    - Exposes the per-adapter in-progress flag (try_begin_ingest/end_ingest) so
      the push route and manual triggers cannot race a running poll
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
        # Track per-adapter error state for escalation
        self._error_tracker: dict[str, SourceErrorTracker] = {}
        # Monotonic timestamp of each adapter's last successful poll
        self._last_polled: dict[str, float] = {}
        # Prevent concurrent ingest of the same adapter
        self._ingest_in_progress: dict[str, bool] = {}
        # Track background ingest threads for graceful shutdown
        self._background_threads: set[threading.Thread] = set()
        # Map from background thread to adapter_id for selective flag clearing
        self._ingest_thread_adapters: dict[threading.Thread, str] = {}
        # Lock for thread-safe management of background threads
        self._threads_lock = threading.Lock()
        # Store the last ingest result per adapter_id (keyed by adapter_id)
        self._ingest_results: dict[str, IngestResult] = {}
        # Lock for thread-safe access to ingest results
        self._results_lock = threading.Lock()

    def get_ingest_result(self, adapter_id: str) -> Optional[IngestResult]:
        """Retrieve the result of the last background ingest for an adapter.

        Returns the IngestResult from the most recent call to trigger_immediate_ingest()
        for the given adapter, or None if no ingest has been triggered yet.

        Args:
            adapter_id: The adapter ID to query

        Returns:
            IngestResult if an ingest has been triggered, otherwise None
        """
        with self._results_lock:
            return self._ingest_results.get(adapter_id)

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
        ctx = tel.capture_context()

        def _run_with_context() -> None:
            with tel.run_in_context(ctx):
                self._run()

        self._thread = threading.Thread(target=_run_with_context, daemon=True)
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
                    "It may still be running a network call or database operation. "
                    "Adapter may remain locked until thread exits."
                )
            else:
                # Only clear the in-progress flag if the thread actually exited
                with self._threads_lock:
                    adapter_id = self._ingest_thread_adapters.get(thread)
                    if adapter_id:
                        self._ingest_in_progress.pop(adapter_id, None)
            # Always remove from tracking set, whether thread exited or not
            with self._threads_lock:
                self._background_threads.discard(thread)
                self._ingest_thread_adapters.pop(thread, None)

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

    def try_begin_ingest(self, adapter_id: str) -> bool:
        """Atomically claim the per-adapter ingest slot.

        Shared by the poller tick, trigger_immediate_ingest(), and the push route
        (targeted ``?adapter_id=``) so no two paths ingest the same adapter
        concurrently: concurrent runs share one adapter instance and would race
        its in-memory cursor and interleave ack() against the same helper
        collector (commit_push_cursors is collector-global on the helper).

        Returns:
            True if the slot was claimed — the caller MUST call end_ingest()
            when done. False if an ingest is already in progress.
        """
        with self._threads_lock:
            if self._ingest_in_progress.get(adapter_id, False):
                return False
            self._ingest_in_progress[adapter_id] = True
            return True

    def end_ingest(self, adapter_id: str) -> None:
        """Release the per-adapter ingest slot claimed by try_begin_ingest()."""
        with self._threads_lock:
            self._ingest_in_progress[adapter_id] = False

    def _tick(self) -> None:
        """Single polling cycle (internal).

        Runs one ingest for each registered adapter whose poll interval has
        elapsed. Per-adapter errors are caught, logged, and do not prevent other
        adapters from being polled.

        An adapter is due when poll_interval_sec (adapter attribute, defaulting
        to the poller tick interval) has elapsed since its last *successful*
        run. A failed run leaves the last-polled mark unchanged, so the adapter
        retries on the next tick.

        Error escalation (consecutive failures per adapter):
        - 1-2 failures: INFO level (transient issues expected)
        - 3-5 failures: WARNING level (persistent issue)
        - 6+ failures: ERROR level (critical, may be permanently broken)

        The in-progress flag is held for the whole ingest+ack so the push route
        and manual triggers cannot run the same adapter concurrently.
        """
        with tracer.start_as_current_span("scheduler.poll") as tick_span:
            tick_span.set_attribute("adapters_registered", len(self._registered))
            adapters_polled = 0

            for adapter, chunker in self._registered:
                if self._stop_event.is_set():
                    break

                adapter_id = adapter.adapter_id
                interval = getattr(adapter, "poll_interval_sec", None) or self._tick_interval
                last = self._last_polled.get(adapter_id)
                if last is not None and (time.monotonic() - last) < interval:
                    continue

                if not self.try_begin_ingest(adapter_id):
                    logger.debug(
                        "Poller: skipping adapter %s; ingest already in progress",
                        adapter_id,
                    )
                    continue

                if adapter_id not in self._error_tracker:
                    self._error_tracker[adapter_id] = SourceErrorTracker()

                with tracer.start_as_current_span("scheduler.poll.adapter") as adapter_span:
                    adapter_span.set_attribute("adapter_id", adapter_id)

                    try:
                        # source_ref="" — the adapter drains from its own
                        # persisted cursor; per-source origin_refs are not
                        # cursors and must not be passed here.
                        self._pipeline.ingest(adapter, chunker, source_ref="")
                        # Commit-ack: confirm to the helper that the page was durably
                        # persisted so it advances its staged delivery cursor (no-op
                        # for adapters not using commit-ack; best-effort, never raises).
                        adapter.ack()
                        self._error_tracker[adapter_id].clear()
                        self._last_polled[adapter_id] = time.monotonic()
                        adapters_polled += 1
                    except MemoryError:
                        # System-level memory exhaustion is fatal; propagate immediately
                        raise
                    except Exception as e:
                        error_tracker = self._error_tracker[adapter_id]
                        error_msg = f"ingest failed: {e}"
                        error_tracker.record_failure()

                        adapter_span.set_status(StatusCode.ERROR)
                        adapter_span.record_exception(e)
                        adapter_span.set_attribute("error.consecutive_failures", error_tracker.consecutive_failures)

                        # Programming bugs (TypeError, AttributeError, etc.) indicate code issues
                        # that won't be fixed by retrying. Log them at ERROR level immediately
                        # rather than waiting for 6+ cycles.
                        if _is_programming_error(e):
                            logger.error(
                                "Poller: adapter %s encountered a programming error (escalated immediately): %s",
                                adapter_id,
                                error_msg,
                                exc_info=True,
                            )
                        # Log at escalated level based on consecutive failure count for transient errors
                        elif error_tracker.should_log_at_error_level():
                            logger.error(
                                "Poller: adapter %s has failed %d times (ERROR level): %s",
                                adapter_id,
                                error_tracker.consecutive_failures,
                                error_msg,
                            )
                        elif error_tracker.should_log_at_warning_level():
                            logger.warning(
                                "Poller: adapter %s has failed %d times (WARNING level): %s",
                                adapter_id,
                                error_tracker.consecutive_failures,
                                error_msg,
                            )
                        else:
                            logger.info(
                                "Poller: adapter %s ingestion attempt failed (transient): %s",
                                adapter_id,
                                error_msg,
                            )
                    finally:
                        self.end_ingest(adapter_id)

            tick_span.set_attribute("adapters_polled", adapters_polled)

    def trigger_immediate_ingest(self, adapter_id: str) -> bool:
        """Trigger an immediate, one-shot ingest run for a specific adapter.

        Finds the registered (adapter, chunker) pair for the given adapter_id and
        runs one ingest for it immediately, bypassing the poll-interval gate. The
        ingest runs asynchronously in a background thread, allowing the HTTP
        response to return immediately.

        The adapter drains from its own persisted cursor (source_ref=""), so this
        also works for a freshly registered adapter with no source rows yet — the
        bootstrap case a manual trigger exists for. After the pipeline commits,
        adapter.ack() confirms delivery to the helper so its staged cursor
        advances (previously manual triggers never acked, leaving the helper
        cursor staged until the next scheduled poll).

        Prevents concurrent ingest of the same adapter via the shared per-adapter
        ingest slot (try_begin_ingest). Background threads are tracked and joined
        during shutdown. The result is stored in _ingest_results for querying
        (via get_ingest_result).

        Args:
            adapter_id: The adapter ID to trigger ingest for

        Returns:
            True if a background ingest thread was successfully spawned

        Raises:
            PollerNotRunningError: If the poller is stopped or not running
            AdapterNotRegisteredError: If the adapter is not registered with the poller
            IngestAlreadyInProgressError: If an ingest is already in progress for this adapter
        """
        # Raise if poller is stopped or not started
        if self._thread is None or not self._thread.is_alive() or self._stop_event.is_set():
            raise PollerNotRunningError("Poller is not running")

        # Find the adapter
        adapter, chunker = self._find_adapter(adapter_id)
        if adapter is None or chunker is None:
            raise AdapterNotRegisteredError(f"Adapter '{adapter_id}' is not registered")

        # Claim the shared per-adapter ingest slot (atomic check-and-set; also
        # blocks the poller tick and the push route while this run is active).
        if not self.try_begin_ingest(adapter_id):
            logger.warning(
                "trigger_immediate_ingest: ingest already in progress for adapter %s",
                adapter_id,
            )
            raise IngestAlreadyInProgressError(
                f"Ingest is already in progress for adapter '{adapter_id}'"
            )

        # Capture OTel context from the calling thread (HTTP request) so the
        # background thread's spans are parented to the incoming request trace.
        _ingest_ctx = tel.capture_context()

        # Spawn a background thread to run the ingest immediately (non-blocking)
        def process_adapter() -> None:
            with tel.run_in_context(_ingest_ctx):
                with tracer.start_as_current_span("scheduler.poll.immediate") as immediate_span:
                    immediate_span.set_attribute("adapter_id", adapter_id)
                    immediate_span.set_attribute("trigger", "manual")

                    result = IngestResult(adapter_id=adapter_id)
                    try:
                        ingest_result = self._pipeline.ingest(
                            adapter, chunker, source_ref=""
                        )
                        # Commit-ack: confirm to the helper that the page was durably
                        # persisted so it advances its staged delivery cursor (no-op
                        # for adapters not using commit-ack; best-effort, never raises).
                        adapter.ack()
                        processed = ingest_result.get("sources_processed", 0)
                        failed = ingest_result.get("sources_failed", 0)
                        result.sources_attempted = processed + failed
                        result.sources_succeeded = processed
                        result.sources_failed = failed
                        self._last_polled[adapter_id] = time.monotonic()
                    except MemoryError:
                        # System-level memory exhaustion is fatal; propagate immediately
                        raise
                    except Exception as e:
                        result.sources_attempted = max(result.sources_attempted, 1)
                        result.sources_failed = max(result.sources_failed, 1)
                        if _is_programming_error(e):
                            result.had_programming_errors = True
                            logger.error(
                                "trigger_immediate_ingest: adapter %s encountered a programming error: %s",
                                adapter_id,
                                e,
                                exc_info=True,
                            )
                        else:
                            logger.exception(
                                "trigger_immediate_ingest: ingest failed for adapter %s: %s",
                                adapter_id,
                                e,
                            )
                    finally:
                        # Mark result as completed and store it
                        result.completed_at = datetime.now()
                        with self._results_lock:
                            self._ingest_results[adapter_id] = result

                        # Set span error status if any sources failed
                        if result.sources_failed > 0:
                            immediate_span.set_status(StatusCode.ERROR)

                        # Always clear the in-progress flag and remove thread from tracking
                        # CRITICAL: Clear flag inside lock to prevent race conditions
                        with self._threads_lock:
                            self._ingest_in_progress[adapter_id] = False
                            self._background_threads.discard(threading.current_thread())
                            self._ingest_thread_adapters.pop(threading.current_thread(), None)

        # Use non-daemon threads and track them for graceful shutdown
        thread = threading.Thread(target=process_adapter, daemon=False)
        with self._threads_lock:
            self._background_threads.add(thread)
            self._ingest_thread_adapters[thread] = adapter_id
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
