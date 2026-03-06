"""Shared filesystem watcher utility for adapters.

Provides a unified interface for watching filesystem events with debouncing,
extension filtering, and atomic-save protection. Wraps watchdog with optional
watchfiles fallback.
"""

import logging
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from context_library.storage.models import PollStrategy

logger = logging.getLogger(__name__)

# Try to import watchdog, fall back to watchfiles if not available
HAS_WATCHDOG = False
HAS_WATCHFILES = False

try:
    from watchdog.observers import Observer
    from watchdog.events import FileSystemEventHandler, FileSystemEvent
    HAS_WATCHDOG = True
except ImportError:
    pass

if not HAS_WATCHDOG:
    try:
        import watchfiles as _watchfiles  # noqa: F401
        HAS_WATCHFILES = True
    except ImportError:
        pass


@dataclass(frozen=True)
class FileEvent:
    """Immutable representation of a filesystem event.

    Attributes:
        path: The filesystem path affected by the event
        event_type: Type of event ('created', 'modified', 'deleted')
    """
    path: Path
    event_type: str  # 'created', 'modified', 'deleted'


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
            callback: Function to invoke for each coalesced event
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
        self._event_buffer: dict[Path, str] = {}  # path -> event_type
        self._buffer_lock = threading.Lock()
        self._debounce_timer: threading.Timer | None = None

        # Observer state (only used with watchdog)
        self._observer: Any = None
        self._observer_started = False

    def start(self) -> None:
        """Start observing the watch_path for filesystem changes."""
        if HAS_WATCHDOG:
            self._start_watchdog()
        elif HAS_WATCHFILES:
            self._start_watchfiles()

    def stop(self) -> None:
        """Stop observing filesystem changes.

        Safe to call even if the watcher was never started.
        """
        if HAS_WATCHDOG and self._observer_started:
            self._stop_watchdog()
        elif HAS_WATCHFILES:
            self._stop_watchfiles()

    def _start_watchdog(self) -> None:
        """Start watchdog observer."""
        if self._observer_started:
            return

        handler = _WatchdogHandler(self._on_raw_event)
        self._observer = Observer()
        self._observer.schedule(handler, str(self._watch_path), recursive=True)
        self._observer.start()
        self._observer_started = True
        logger.debug(f"Started watching {self._watch_path} with watchdog")

    def _stop_watchdog(self) -> None:
        """Stop watchdog observer and flush pending events.

        Ensures that:
        1. The observer is stopped (no new raw events can arrive)
        2. The debounce timer is cancelled (no pending flush from timer thread)
        3. Any buffered events are dispatched exactly once
        4. No callbacks are invoked after this method returns
        """
        if not self._observer_started or self._observer is None:
            return

        self._observer.stop()
        self._observer.join(timeout=2)
        self._observer_started = False

        # Cancel any pending debounce timer atomically
        # This prevents the timer thread from calling _flush_buffer() after we return
        with self._buffer_lock:
            if self._debounce_timer is not None:
                self._debounce_timer.cancel()
                self._debounce_timer = None

        # Flush any buffered events using the standard _flush_buffer path
        # This ensures consistent callback invocation and error handling
        self._flush_buffer()

        logger.debug(f"Stopped watching {self._watch_path}")

    def _start_watchfiles(self) -> None:
        """Start watchfiles observer in a background thread."""
        raise NotImplementedError(
            "watchfiles backend is not yet implemented. "
            "Please install watchdog: pip install watchdog"
        )

    def _stop_watchfiles(self) -> None:
        """Stop watchfiles observer."""
        raise NotImplementedError(
            "watchfiles backend is not yet implemented. "
            "Please install watchdog: pip install watchdog"
        )

    def _on_raw_event(self, path: Path, event_type: str) -> None:
        """Handle a raw filesystem event with debouncing.

        Args:
            path: Path that triggered the event
            event_type: Type of event ('created', 'modified', 'deleted')
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
            if event_type == "created" and path in self._event_buffer:
                existing_type = self._event_buffer[path]
                if existing_type == "deleted":
                    # Atomic save detected: convert to modified
                    self._event_buffer[path] = "modified"
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

    def _flush_buffer(self) -> None:
        """Dispatch all buffered events and clear the buffer.

        Acquires lock only to snapshot and clear the buffer. Callbacks are invoked
        outside the lock to:
        1. Allow new events to be buffered during callback execution
        2. Prevent slow callbacks from blocking the raw event handler
        3. Avoid deadlocks if callback tries to acquire the lock
        """
        with self._buffer_lock:
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

        def __init__(self, buffer_callback: Callable[[Path, str], None]) -> None:
            """Initialize the handler.

            Args:
                buffer_callback: Function to call for each raw event.
                               Called with (path: Path, event_type: str).
            """
            super().__init__()
            self._buffer_callback = buffer_callback

        def on_created(self, event: FileSystemEvent) -> None:
            """Handle file/directory creation."""
            if not event.is_directory:
                self._buffer_callback(Path(str(event.src_path)), "created")

        def on_modified(self, event: FileSystemEvent) -> None:
            """Handle file/directory modification."""
            if not event.is_directory:
                self._buffer_callback(Path(str(event.src_path)), "modified")

        def on_deleted(self, event: FileSystemEvent) -> None:
            """Handle file/directory deletion."""
            if not event.is_directory:
                self._buffer_callback(Path(str(event.src_path)), "deleted")

        def on_moved(self, event: FileSystemEvent) -> None:
            """Handle file/directory move (treat as modified on destination)."""
            if not event.is_directory:
                self._buffer_callback(Path(str(event.dest_path)), "modified")
else:
    # Placeholder class when watchdog is not available
    class _WatchdogHandler:  # type: ignore
        """Placeholder handler when watchdog is not available."""
        def __init__(self, buffer_callback: Callable[[Path, str], None]) -> None:
            pass


# Export public API
__all__ = ["FileEvent", "FileSystemWatcher", "PollStrategy"]
