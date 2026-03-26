"""Shared filesystem watcher utility for adapters.

Provides a unified interface for watching filesystem events with debouncing,
extension filtering, and atomic-save protection. Uses watchdog if available,
otherwise falls back to watchfiles.
"""

import logging
import threading
import gc
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from context_library.storage.models import EventType, PollStrategy

logger = logging.getLogger(__name__)

# Try to import watchdog and watchfiles (both are supported as primary or fallback)
HAS_WATCHDOG = False
HAS_WATCHFILES = False

try:
    from watchdog.observers import Observer
    from watchdog.events import FileSystemEventHandler, FileSystemEvent
    HAS_WATCHDOG = True
except ImportError:
    pass

# Always try to import watchfiles for use as fallback
try:
    import watchfiles as _watchfiles
    HAS_WATCHFILES = True
except ImportError:
    _watchfiles = None  # type: ignore


@dataclass(frozen=True)
class FileEvent:
    """Immutable representation of a filesystem event.

    Attributes:
        path: The filesystem path affected by the event
        event_type: Type of event (created, modified, or deleted)
    """
    path: Path
    event_type: EventType


class FileSystemWatcher:
    """Unified filesystem watcher with debouncing and atomic-save protection.

    Watches a directory for filesystem changes and invokes a callback with
    coalesced events. Automatically handles editor atomic-save patterns
    (vim, emacs, VS Code) by detecting deleted+created sequences within
    the debounce window and converting them to modified events.

    Each instance maintains independent state; multiple instances do not
    share watches or buffers.
    """

    def __init__(
        self,
        watch_path: Path,
        callback: Callable[[FileEvent], None],
        extensions: set[str] | None = None,
        debounce_ms: int = 500,
    ) -> None:
        """Initialize the filesystem watcher.

        Args:
            watch_path: Root directory to watch for changes
            callback: Function to invoke for each coalesced FileEvent
            extensions: Optional set of file extensions to watch (e.g., {'.md', '.txt'}).
                       If None, all events are included. Extensions should include
                       the leading dot (e.g., '.md').
            debounce_ms: Time in milliseconds to buffer events before dispatching.
                        Coalesces rapid events on the same path. Default is 500ms.
        """
        if not HAS_WATCHDOG and not HAS_WATCHFILES:
            raise RuntimeError(
                "Neither watchdog nor watchfiles is installed. "
                "Install one of: pip install watchdog  or  pip install watchfiles"
            )

        self._watch_path = Path(watch_path)
        self._callback = callback
        self._extensions = extensions
        self._debounce_ms = debounce_ms

        # Event buffering for debouncing
        self._event_buffer: dict[Path, EventType] = {}  # path -> event_type
        self._buffer_lock = threading.Lock()
        self._debounce_timer: threading.Timer | None = None
        self._stopped = False  # Flag to prevent callbacks after stop()

        # Observer state (only used with watchdog)
        self._observer: Any = None
        self._observer_started = False

        # Watchfiles state (only used with watchfiles)
        self._watchfiles_thread: threading.Thread | None = None
        self._watchfiles_stop_event: threading.Event | None = None
        self._watchfiles_failed = False  # Flag to track watchfiles thread failure
        self._watchfiles_initialized = threading.Event()  # Signals successful initialization

    def __del__(self) -> None:
        """Ensure cleanup when the watcher is garbage collected."""
        try:
            if self.is_alive:
                self.stop()
        except Exception:
            # Silently fail in __del__ to avoid issues during shutdown
            pass

    def start(self) -> None:
        """Start observing the watch_path for filesystem changes.

        Tries watchdog first, but falls back to watchfiles if watchdog
        hits the inotify limit or is not available.
        """
        if HAS_WATCHDOG:
            self._start_watchdog()
        elif HAS_WATCHFILES:
            self._start_watchfiles()
        else:
            raise RuntimeError(
                "Neither watchdog nor watchfiles is installed. "
                "Install one of: pip install watchdog  or  pip install watchfiles"
            )

    def stop(self) -> None:
        """Stop observing filesystem changes.

        Safe to call even if the watcher was never started.
        """
        if self._observer_started:
            self._stop_watchdog()
        elif self._watchfiles_thread is not None and self._watchfiles_thread.is_alive():
            self._stop_watchfiles()

    @property
    def is_alive(self) -> bool:
        """Check if the watcher is actively monitoring for changes.

        Returns False if:
        - Using watchdog and observer has not been started or has been stopped
        - Using watchfiles and the background thread has failed or been stopped
        - The watchfiles thread has encountered an exception and set the failed flag

        This property allows callers to detect if the watcher has silently died
        (e.g., watchfiles loop exception) so they can take remedial action.
        """
        # Check watchdog mode
        if self._observer_started:
            return not self._stopped
        # Check watchfiles mode
        if self._watchfiles_thread is not None and self._watchfiles_thread.is_alive():
            return not self._watchfiles_failed and not self._stopped
        return False

    def _start_watchdog(self) -> None:
        """Start watchdog observer."""
        if self._observer_started:
            return

        # Reset stopped flag to allow new watch cycle
        self._stopped = False
        handler = _WatchdogHandler(self._on_raw_event)
        self._observer = Observer()
        self._observer.schedule(handler, str(self._watch_path), recursive=True)
        try:
            self._observer.start()
        except OSError as e:
            # If we hit inotify limit, fall back to watchfiles
            if e.errno == 28:  # ENOSPC - inotify watch limit reached
                logger.warning(
                    f"inotify watch limit reached, falling back to watchfiles: {e}"
                )
                # Clean up the partially initialized observer
                try:
                    self._observer.unschedule_all()
                except (AttributeError, KeyError):
                    pass
                observer_ref = self._observer
                self._observer = None
                self._observer_started = False
                del observer_ref
                gc.collect()
                time.sleep(0.01)
                gc.collect()

                if HAS_WATCHFILES:
                    self._start_watchfiles()
                else:
                    raise RuntimeError(
                        "inotify watch limit reached and watchfiles not available"
                    )
                return
            raise
        self._observer_started = True
        logger.debug(f"Started watching {self._watch_path} with watchdog")

    def _stop_watchdog(self) -> None:
        """Stop watchdog observer and flush any pending events.

        Final buffered events are dispatched during this call. Any timer callbacks
        that race with this stop sequence will not invoke user callbacks (prevented
        by the _stopped flag).

        Ensures that:
        1. The observer is stopped (no new raw events can arrive)
        2. Any buffered events are dispatched exactly once during this call
        3. The _stopped flag prevents any pending timer callbacks from invoking
           user callbacks after this method returns
        """
        if not self._observer_started or self._observer is None:
            return

        # Stop the observer and wait for it to fully stop
        self._observer.stop()
        self._observer.join(timeout=2)

        # Explicitly unschedule all handlers to release OS resources (inotify watches)
        try:
            self._observer.unschedule_all()
        except (AttributeError, KeyError):
            pass

        # Clear observer reference to ensure garbage collection can fully release inotify watches
        observer_ref = self._observer
        self._observer = None
        self._observer_started = False

        # Delete the reference and force GC multiple times to reclaim inotify watches
        del observer_ref
        gc.collect()
        time.sleep(0.01)  # Give OS a moment to release inotify resources
        gc.collect()

        # Cancel the debounce timer and set stopped flag atomically, BEFORE flushing.
        # This closes the race window: any timer callback that fires after this point
        # will see _stopped=True and skip invoking user callbacks.
        with self._buffer_lock:
            self._stopped = True
            if self._debounce_timer is not None:
                self._debounce_timer.cancel()
                self._debounce_timer = None

        # Flush any buffered events AFTER marking stopped.
        # This ensures the stop-initiated flush is the only flush that invokes callbacks,
        # and any racing timer callback will not invoke user callbacks.
        self._flush_buffer(from_stop=True)

        logger.debug(f"Stopped watching {self._watch_path}")

    def _start_watchfiles(self) -> None:
        """Start watchfiles observer in a background thread.

        Raises:
            RuntimeError: If the watchfiles thread fails to initialize (e.g., due to
                         inotify limit). The caller can distinguish between initialization
                         failure and successful startup.
        """
        if self._watchfiles_thread is not None and self._watchfiles_thread.is_alive():
            return

        # Reset stopped flag to allow new watch cycle
        self._stopped = False
        self._watchfiles_failed = False
        self._watchfiles_initialized.clear()
        self._watchfiles_stop_event = threading.Event()
        self._watchfiles_thread = threading.Thread(
            target=self._watchfiles_loop,
            daemon=True,
        )
        self._watchfiles_thread.start()

        # Wait for the watchfiles thread to signal initialization or detect failure.
        # The thread sets _watchfiles_initialized after successfully entering watchfiles.watch().
        # This is more reliable than time-based heuristics.
        if not self._watchfiles_initialized.wait(timeout=2.0):
            if not self._watchfiles_thread.is_alive():
                # Thread died without signaling initialization - likely failed to call watchfiles.watch()
                self._watchfiles_failed = True
                raise RuntimeError(
                    f"watchfiles thread failed to initialize watching {self._watch_path}, "
                    "likely due to resource exhaustion (inotify limit reached)"
                )
            # Thread is still alive but hasn't signaled initialization within timeout.
            # Log a warning but allow it to continue (may be a slow system).
            logger.warning(
                f"watchfiles initialization taking longer than expected for {self._watch_path}, "
                "proceeding with caution"
            )

        logger.debug(f"Started watching {self._watch_path} with watchfiles")

    def _stop_watchfiles(self) -> None:
        """Stop watchfiles observer and flush any pending events.

        Final buffered events are dispatched during this call. Any timer callbacks
        that race with this stop sequence will not invoke user callbacks (prevented
        by the _stopped flag).

        Ensures that:
        1. The watchfiles thread is signaled to stop
        2. Any buffered events are dispatched exactly once during this call
        3. The _stopped flag prevents any pending timer callbacks from invoking
           user callbacks after this method returns
        """
        if self._watchfiles_thread is None or not self._watchfiles_thread.is_alive():
            return

        # Signal the watchfiles thread to stop
        if self._watchfiles_stop_event is not None:
            self._watchfiles_stop_event.set()

        # Wait for the thread to finish (with timeout as safety measure)
        if self._watchfiles_thread is not None:
            self._watchfiles_thread.join(timeout=2)
            self._watchfiles_thread = None

        # Cancel the debounce timer and set stopped flag atomically, BEFORE flushing.
        # This closes the race window: any timer callback that fires after this point
        # will see _stopped=True and skip invoking user callbacks.
        with self._buffer_lock:
            self._stopped = True
            if self._debounce_timer is not None:
                self._debounce_timer.cancel()
                self._debounce_timer = None

        # Flush any buffered events AFTER marking stopped.
        # This ensures the stop-initiated flush is the only flush that invokes callbacks,
        # and any racing timer callback will not invoke user callbacks.
        self._flush_buffer(from_stop=True)

        logger.debug(f"Stopped watching {self._watch_path}")

    def _watchfiles_loop(self) -> None:
        """Background thread loop that watches for filesystem changes using watchfiles.

        This runs in a separate thread and translates watchfiles changes into
        standardized FileEvent types. The loop runs until _watchfiles_stop_event
        is set, then exits cleanly.

        If an exception occurs, it marks the thread as failed so callers can detect
        that the watcher has ceased functioning.

        watchfiles.watch() yields sets of (change_type, path) tuples where
        change_type is a Change enum (1=added, 2=modified, 3=deleted).
        """
        try:
            if _watchfiles is None:
                logger.error("watchfiles module not available in watchfiles loop")
                self._watchfiles_failed = True
                return

            # Give the system a moment to settle before starting to watch
            # This helps avoid "OS file watch limit reached" errors when multiple
            # watchers are started in quick succession
            time.sleep(0.5)

            # Signal that initialization has begun (watchfiles.watch() is being called)
            # The caller's wait-for-initialization check will complete once this generator
            # is successfully created
            changes_iter = _watchfiles.watch(
                str(self._watch_path),
                watch_filter=None,
                stop_event=self._watchfiles_stop_event,
            )
            # Signal successful initialization
            self._watchfiles_initialized.set()

            for changes in changes_iter:
                # Process each change in the batch
                for change_type_int, changed_path in changes:
                    # watchfiles returns change_type as an int (Change enum)
                    # Convert to our standard event types: 1=Added -> CREATED, etc.
                    if change_type_int == 1:  # Change.Added
                        event_type = EventType.CREATED
                    elif change_type_int == 2:  # Change.Modified
                        event_type = EventType.MODIFIED
                    elif change_type_int == 3:  # Change.Deleted
                        event_type = EventType.DELETED
                    else:
                        # Unknown change type, skip
                        continue

                    # Process the event through our debouncing system
                    self._on_raw_event(Path(changed_path), event_type)

        except Exception as e:
            logger.error(f"Error in watchfiles loop: {e}", exc_info=True)
            self._watchfiles_failed = True

    def _on_raw_event(self, path: Path, event_type: EventType) -> None:
        """Handle a raw filesystem event with debouncing.

        Args:
            path: Path that triggered the event
            event_type: Type of event (created, modified, or deleted)
        """
        # Filter by extension if configured
        if self._extensions is not None:
            if path.suffix not in self._extensions:
                return

        with self._buffer_lock:
            # Cancel existing timer and update buffer
            if self._debounce_timer is not None:
                self._debounce_timer.cancel()

            # Handle atomic-save pattern: deleted + created -> modified
            # If we already have a deleted event for this path, and a created event
            # arrives, coalesce to modified
            if event_type == EventType.CREATED and path in self._event_buffer:
                existing_type = self._event_buffer[path]
                if existing_type == EventType.DELETED:
                    # Atomic save detected: convert to modified
                    self._event_buffer[path] = EventType.MODIFIED
                else:
                    # Normal case: later event overwrites earlier one
                    self._event_buffer[path] = event_type
            else:
                self._event_buffer[path] = event_type

            # Restart debounce timer
            self._debounce_timer = threading.Timer(
                self._debounce_ms / 1000.0,
                self._flush_buffer,
            )
            self._debounce_timer.start()

    def _flush_buffer(self, from_stop: bool = False) -> None:
        """Dispatch all buffered events and clear the buffer.

        Args:
            from_stop: If True, this flush is part of the stop sequence and should
                       always proceed. If False (default), this is a timer callback
                       and should skip if stopped.

        Acquires lock only to snapshot and clear the buffer. Callbacks are invoked
        outside the lock to:
        1. Allow new events to be buffered during callback execution
        2. Prevent slow callbacks from blocking the raw event handler
        3. Avoid deadlocks if callback tries to acquire the lock

        If called as a timer callback AFTER stop() has set _stopped=True,
        no callbacks will be invoked. This prevents race conditions where a pending
        debounce timer fires after stop() returns.
        """
        with self._buffer_lock:
            # If a timer callback arrives after stop() set _stopped=True, skip processing
            # But if this is the stop-initiated flush, always proceed
            if self._stopped and not from_stop:
                return

            # Snapshot buffer and clear it atomically
            buffer_snapshot = dict(self._event_buffer)
            self._event_buffer.clear()
            self._debounce_timer = None

        # Invoke callbacks outside the lock
        for path, event_type in buffer_snapshot.items():
            event = FileEvent(path=path, event_type=event_type)
            try:
                self._callback(event)
            except Exception as e:
                logger.error(
                    f"Error in filesystem watcher callback for {path}: {e}",
                    exc_info=True,
                )


if HAS_WATCHDOG:
    class _WatchdogHandler(FileSystemEventHandler):
        """Internal watchdog event handler that feeds events to the debouncing buffer."""

        def __init__(self, buffer_callback: Callable[[Path, EventType], None]) -> None:
            """Initialize the handler.

            Args:
                buffer_callback: Function to call for each raw event.
                               Called with (path: Path, event_type: EventType).
            """
            super().__init__()
            self._buffer_callback = buffer_callback

        def on_created(self, event: FileSystemEvent) -> None:
            """Handle file creation (directories are filtered out)."""
            if not event.is_directory:
                self._buffer_callback(Path(str(event.src_path)), EventType.CREATED)

        def on_modified(self, event: FileSystemEvent) -> None:
            """Handle file modification (directories are filtered out)."""
            if not event.is_directory:
                self._buffer_callback(Path(str(event.src_path)), EventType.MODIFIED)

        def on_deleted(self, event: FileSystemEvent) -> None:
            """Handle file deletion (directories are filtered out)."""
            if not event.is_directory:
                self._buffer_callback(Path(str(event.src_path)), EventType.DELETED)

        def on_moved(self, event: FileSystemEvent) -> None:
            """Handle file move (treat as modified on destination, directories are filtered out)."""
            if not event.is_directory:
                self._buffer_callback(Path(str(event.dest_path)), EventType.MODIFIED)
else:
    # Placeholder class when watchdog is not available
    class _WatchdogHandler:  # type: ignore
        """Placeholder handler when watchdog is not available."""
        def __init__(self, buffer_callback: Callable[[Path, EventType], None]) -> None:
            pass


# Export public API
__all__ = ["EventType", "FileEvent", "FileSystemWatcher", "PollStrategy"]
