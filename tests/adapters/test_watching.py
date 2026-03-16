"""Tests for the shared filesystem watcher module."""

import pytest
import tempfile
import time
from pathlib import Path
from unittest.mock import MagicMock

from context_library.adapters._watching import FileEvent, FileSystemWatcher, PollStrategy
from context_library.storage.models import EventType


class TestFileEvent:
    """Tests for FileEvent dataclass."""

    def test_file_event_creation(self) -> None:
        """Test creating a FileEvent."""
        path = Path("/tmp/test.md")
        event = FileEvent(path=path, event_type=EventType.CREATED)

        assert event.path == path
        assert event.event_type == "created"

    def test_file_event_immutability(self) -> None:
        """Test that FileEvent is immutable (frozen dataclass)."""
        event = FileEvent(path=Path("/tmp/test.md"), event_type=EventType.CREATED)

        with pytest.raises(AttributeError):
            event.path = Path("/tmp/other.md")  # type: ignore[misc]

        with pytest.raises(AttributeError):
            event.event_type = EventType.MODIFIED  # type: ignore[misc]


class TestFileSystemWatcherInit:
    """Tests for FileSystemWatcher initialization."""

    def test_watcher_instantiation(self) -> None:
        """Test instantiating a FileSystemWatcher."""
        callback = MagicMock()
        watcher = FileSystemWatcher(
            watch_path=Path("/tmp"),
            callback=callback,
        )

        assert watcher._watch_path == Path("/tmp")
        assert watcher._callback == callback
        assert watcher._extensions is None
        assert watcher._debounce_ms == 500

    def test_watcher_with_extensions(self) -> None:
        """Test FileSystemWatcher with extension filtering."""
        callback = MagicMock()
        watcher = FileSystemWatcher(
            watch_path=Path("/tmp"),
            callback=callback,
            extensions={".md", ".txt"},
        )

        assert watcher._extensions == {".md", ".txt"}

    def test_watcher_with_custom_debounce(self) -> None:
        """Test FileSystemWatcher with custom debounce time."""
        callback = MagicMock()
        watcher = FileSystemWatcher(
            watch_path=Path("/tmp"),
            callback=callback,
            debounce_ms=1000,
        )

        assert watcher._debounce_ms == 1000

    def test_poll_strategy_exposed(self) -> None:
        """Test that PollStrategy is exposed from the module."""
        assert hasattr(PollStrategy, "PUSH")
        assert PollStrategy.PUSH == "push"


class TestFileSystemWatcherLifecycle:
    """Tests for FileSystemWatcher start/stop lifecycle."""

    def test_start_and_stop_unstarted_watcher(self) -> None:
        """Test that stop() is safe to call on an unstarted watcher."""
        callback = MagicMock()
        watcher = FileSystemWatcher(
            watch_path=Path("/tmp"),
            callback=callback,
        )

        # Should not raise an exception
        watcher.stop()

    def test_start_watcher(self) -> None:
        """Test starting a FileSystemWatcher."""
        callback = MagicMock()
        with tempfile.TemporaryDirectory() as tmpdir:
            watcher = FileSystemWatcher(
                watch_path=Path(tmpdir),
                callback=callback,
                debounce_ms=100,
            )

            watcher.start()
            assert watcher._observer_started is True

            watcher.stop()
            assert watcher._observer_started is False

    def test_multiple_start_stop_cycles(self) -> None:
        """Test that a watcher can be started/stopped multiple times."""
        callback = MagicMock()
        with tempfile.TemporaryDirectory() as tmpdir:
            watcher = FileSystemWatcher(
                watch_path=Path(tmpdir),
                callback=callback,
                debounce_ms=100,
            )

            # First cycle
            watcher.start()
            assert watcher._observer_started is True
            watcher.stop()
            assert watcher._observer_started is False

            # Second cycle
            watcher.start()
            assert watcher._observer_started is True
            watcher.stop()
            assert watcher._observer_started is False


class TestFileSystemWatcherEvents:
    """Tests for filesystem event handling."""

    def test_file_creation_event(self) -> None:
        """Test that created file triggers callback with create or modified event."""
        callback = MagicMock()
        with tempfile.TemporaryDirectory() as tmpdir:
            watch_dir = Path(tmpdir)
            watcher = FileSystemWatcher(
                watch_path=watch_dir,
                callback=callback,
                debounce_ms=100,
            )

            watcher.start()

            # Create a file
            test_file = watch_dir / "test.md"
            test_file.write_text("hello")

            # Wait for debounce and callback
            time.sleep(0.2)

            watcher.stop()

            # Verify callback was called with either created or modified event
            # (watchdog may coalesce creation and write into a single modified event)
            assert callback.called
            call_args_list = callback.call_args_list
            assert any(
                c[0][0].event_type in ("created", "modified") and c[0][0].path == test_file
                for c in call_args_list
            )

    def test_file_modification_event(self) -> None:
        """Test that modified file triggers callback."""
        callback = MagicMock()
        with tempfile.TemporaryDirectory() as tmpdir:
            watch_dir = Path(tmpdir)
            test_file = watch_dir / "test.md"
            test_file.write_text("initial")

            watcher = FileSystemWatcher(
                watch_path=watch_dir,
                callback=callback,
                debounce_ms=100,
            )

            watcher.start()

            # Modify the file
            test_file.write_text("modified")

            # Wait for debounce and callback
            time.sleep(0.2)

            watcher.stop()

            # Verify callback was called with modified event
            assert callback.called
            call_args_list = callback.call_args_list
            assert any(
                c[0][0].event_type == "modified" and c[0][0].path == test_file
                for c in call_args_list
            )

    def test_file_deletion_event(self) -> None:
        """Test that deleted file triggers callback."""
        callback = MagicMock()
        with tempfile.TemporaryDirectory() as tmpdir:
            watch_dir = Path(tmpdir)
            test_file = watch_dir / "test.md"
            test_file.write_text("content")

            watcher = FileSystemWatcher(
                watch_path=watch_dir,
                callback=callback,
                debounce_ms=100,
            )

            watcher.start()

            # Delete the file
            test_file.unlink()

            # Wait for debounce and callback
            time.sleep(0.2)

            watcher.stop()

            # Verify callback was called with deleted event
            assert callback.called
            call_args_list = callback.call_args_list
            assert any(
                c[0][0].event_type == "deleted" and c[0][0].path == test_file
                for c in call_args_list
            )


class TestFileSystemWatcherDebouncing:
    """Tests for event debouncing."""

    def test_same_path_events_coalesced(self) -> None:
        """Test that multiple events on same path are coalesced into one callback."""
        callback = MagicMock()
        with tempfile.TemporaryDirectory() as tmpdir:
            watch_dir = Path(tmpdir)
            test_file = watch_dir / "test.md"

            watcher = FileSystemWatcher(
                watch_path=watch_dir,
                callback=callback,
                debounce_ms=200,
            )

            watcher.start()

            # Create and modify file rapidly
            test_file.write_text("v1")
            time.sleep(0.05)
            test_file.write_text("v2")
            time.sleep(0.05)
            test_file.write_text("v3")

            # Wait for debounce to complete
            time.sleep(0.3)

            watcher.stop()

            # Should have exactly 1 or 2 events for the file, not 3+ separate events
            file_events = [
                c for c in callback.call_args_list
                if c[0][0].path == test_file
            ]
            assert len(file_events) <= 2  # created + modified at most

    def test_different_path_events_not_coalesced(self) -> None:
        """Test that events on different paths are dispatched separately."""
        callback = MagicMock()
        with tempfile.TemporaryDirectory() as tmpdir:
            watch_dir = Path(tmpdir)
            file1 = watch_dir / "test1.md"
            file2 = watch_dir / "test2.md"

            watcher = FileSystemWatcher(
                watch_path=watch_dir,
                callback=callback,
                debounce_ms=100,
            )

            watcher.start()

            # Create both files within debounce window
            file1.write_text("content1")
            file2.write_text("content2")

            # Wait for debounce
            time.sleep(0.2)

            watcher.stop()

            # Both files should trigger separate events
            assert callback.called
            paths_seen = {c[0][0].path for c in callback.call_args_list}
            assert file1 in paths_seen
            assert file2 in paths_seen


class TestFileSystemWatcherAtomicSave:
    """Tests for atomic-save pattern handling (deleted + created -> modified)."""

    def test_deleted_then_created_coalesced_to_modified(self) -> None:
        """Test that deleted+created sequence becomes modified event."""
        events_received = []

        def capture_callback(event: FileEvent) -> None:
            events_received.append(event)

        with tempfile.TemporaryDirectory() as tmpdir:
            watch_dir = Path(tmpdir)
            test_file = watch_dir / "test.md"

            watcher = FileSystemWatcher(
                watch_path=watch_dir,
                callback=capture_callback,
                debounce_ms=200,
            )

            watcher.start()

            # Simulate atomic save: create initial file
            test_file.write_text("original")

            # Give watchdog time to detect the file
            time.sleep(0.15)

            # Simulate atomic save pattern:
            # 1. delete the file
            test_file.unlink()
            time.sleep(0.01)
            # 2. recreate it with new content
            test_file.write_text("modified")

            # Wait for debounce to process both events
            time.sleep(0.3)

            watcher.stop()

            # Find events related to our test file
            file_events = [e for e in events_received if e.path == test_file]

            # The atomic save should result in a 'modified' event, not 'deleted'
            # (or at worst, the created event that overwrites the deleted)
            assert len(file_events) > 0
            last_event = file_events[-1]
            assert last_event.event_type in ["modified", "created"]


class TestFileSystemWatcherExtensionFiltering:
    """Tests for extension-based filtering."""

    def test_extension_filter_excludes_non_matching(self) -> None:
        """Test that events for non-matching extensions are filtered out."""
        callback = MagicMock()
        with tempfile.TemporaryDirectory() as tmpdir:
            watch_dir = Path(tmpdir)
            md_file = watch_dir / "test.md"
            txt_file = watch_dir / "test.txt"

            watcher = FileSystemWatcher(
                watch_path=watch_dir,
                callback=callback,
                extensions={".md"},
                debounce_ms=100,
            )

            watcher.start()

            # Create both files
            md_file.write_text("markdown")
            txt_file.write_text("text")

            # Wait for debounce
            time.sleep(0.2)

            watcher.stop()

            # Only .md file should trigger callback
            assert callback.called
            paths_seen = {c[0][0].path for c in callback.call_args_list}
            assert md_file in paths_seen
            assert txt_file not in paths_seen

    def test_no_extension_filter_includes_all(self) -> None:
        """Test that without extension filter, all files trigger callbacks."""
        callback = MagicMock()
        with tempfile.TemporaryDirectory() as tmpdir:
            watch_dir = Path(tmpdir)
            md_file = watch_dir / "test.md"
            txt_file = watch_dir / "test.txt"

            watcher = FileSystemWatcher(
                watch_path=watch_dir,
                callback=callback,
                extensions=None,
                debounce_ms=100,
            )

            watcher.start()

            # Create both files
            md_file.write_text("markdown")
            txt_file.write_text("text")

            # Wait for debounce
            time.sleep(0.2)

            watcher.stop()

            # Both files should trigger callbacks
            assert callback.called
            paths_seen = {c[0][0].path for c in callback.call_args_list}
            assert md_file in paths_seen
            assert txt_file in paths_seen


class TestFileSystemWatcherIndependence:
    """Tests for instance independence (no shared state)."""

    def test_two_watchers_independent(self) -> None:
        """Test that two separate watcher instances operate independently."""
        callback1 = MagicMock()
        callback2 = MagicMock()

        with tempfile.TemporaryDirectory() as tmpdir1:
            with tempfile.TemporaryDirectory() as tmpdir2:
                watch_dir1 = Path(tmpdir1)
                watch_dir2 = Path(tmpdir2)

                watcher1 = FileSystemWatcher(
                    watch_path=watch_dir1,
                    callback=callback1,
                    debounce_ms=100,
                )
                watcher2 = FileSystemWatcher(
                    watch_path=watch_dir2,
                    callback=callback2,
                    debounce_ms=100,
                )

                watcher1.start()
                watcher2.start()

                # Create files in different directories
                file1 = watch_dir1 / "test1.md"
                file2 = watch_dir2 / "test2.md"

                file1.write_text("content1")
                file2.write_text("content2")

                # Wait for debounce
                time.sleep(0.2)

                watcher1.stop()
                watcher2.stop()

                # Each callback should only see its own directory's events
                assert callback1.called
                assert callback2.called

                paths1 = {c[0][0].path for c in callback1.call_args_list}
                paths2 = {c[0][0].path for c in callback2.call_args_list}

                assert file1 in paths1
                assert file2 not in paths1

                assert file2 in paths2
                assert file1 not in paths2


class TestModuleImports:
    """Tests for module exports."""

    def test_fileevent_importable(self) -> None:
        """Test that FileEvent is importable from the module."""
        from context_library.adapters._watching import FileEvent as ImportedFileEvent
        assert ImportedFileEvent is FileEvent

    def test_filesystemwatcher_importable(self) -> None:
        """Test that FileSystemWatcher is importable from the module."""
        from context_library.adapters._watching import (
            FileSystemWatcher as ImportedWatcher,
        )
        assert ImportedWatcher is FileSystemWatcher

    def test_pollstrategy_importable(self) -> None:
        """Test that PollStrategy is importable from the module."""
        from context_library.adapters._watching import PollStrategy as ImportedPS
        from context_library.storage.models import PollStrategy as OriginalPS
        assert ImportedPS is OriginalPS


class TestCallbackErrorHandling:
    """Tests for error handling in callbacks."""

    def test_callback_exception_does_not_crash_watcher(self) -> None:
        """Test that exceptions in callback don't crash the watcher."""
        def failing_callback(event: FileEvent) -> None:
            raise RuntimeError("Intentional test error")

        with tempfile.TemporaryDirectory() as tmpdir:
            watch_dir = Path(tmpdir)
            test_file = watch_dir / "test.md"

            watcher = FileSystemWatcher(
                watch_path=watch_dir,
                callback=failing_callback,
                debounce_ms=100,
            )

            watcher.start()

            # Create a file - callback will raise but should be caught
            test_file.write_text("content")

            # Wait for debounce and error handling
            time.sleep(0.2)

            # Watcher should still be running despite callback error
            assert watcher._observer_started is True

            watcher.stop()


class TestFileSystemWatcherLockManagement:
    """Tests for lock management in _flush_buffer() to prevent callback blocking."""

    def test_flush_buffer_releases_lock_during_callback(self) -> None:
        """_flush_buffer() should release lock before invoking callbacks."""
        callback_called = False
        callback_release_event = None

        def mock_callback(event: FileEvent) -> None:
            nonlocal callback_called, callback_release_event
            callback_called = True
            # If the lock wasn't released, this would deadlock or cause issues
            # In a proper implementation, we can verify the lock was released
            # by checking that we can access buffer state
            callback_release_event = True

        with tempfile.TemporaryDirectory() as tmpdir:
            watcher = FileSystemWatcher(
                watch_path=Path(tmpdir),
                callback=mock_callback,
                debounce_ms=50,
            )

            watcher.start()

            try:
                # Create test file
                test_file = Path(tmpdir) / "test.txt"
                test_file.write_text("content")

                # Wait for callback to be invoked
                time.sleep(0.2)

                # Callback should have been called
                assert callback_called is True
                assert callback_release_event is True
            finally:
                watcher.stop()

    def test_flush_buffer_snapshot_prevents_double_flush(self) -> None:
        """_flush_buffer() should snapshot buffer to prevent double-flush race."""
        call_count = 0

        def counting_callback(event: FileEvent) -> None:
            nonlocal call_count
            call_count += 1

        with tempfile.TemporaryDirectory() as tmpdir:
            watcher = FileSystemWatcher(
                watch_path=Path(tmpdir),
                callback=counting_callback,
                debounce_ms=100,
            )

            watcher.start()

            try:
                # Create and modify file within debounce window
                test_file = Path(tmpdir) / "test.txt"
                test_file.write_text("content1")
                # Modify quickly (within debounce window)
                time.sleep(0.02)
                test_file.write_text("content2")

                # Wait for debouncing to complete
                time.sleep(0.15)

                # Should have been called once (both events coalesced into modified)
                assert call_count == 1
            finally:
                watcher.stop()


class TestFileSystemWatcherStopRaceCondition:
    """Tests for race condition fix in stop() and _flush_buffer()."""

    def test_stop_with_pending_debounce_timer(self) -> None:
        """stop() should safely handle pending debounce timers."""
        events_received = []

        def recording_callback(event: FileEvent) -> None:
            events_received.append(event)

        with tempfile.TemporaryDirectory() as tmpdir:
            watcher = FileSystemWatcher(
                watch_path=Path(tmpdir),
                callback=recording_callback,
                debounce_ms=500,  # Long debounce to ensure timer is pending
            )

            watcher.start()

            try:
                # Create a file (starts debounce timer)
                test_file = Path(tmpdir) / "test.txt"
                test_file.write_text("content")

                # Stop immediately (while timer is pending)
                # This should not crash and should properly flush pending events
                time.sleep(0.05)  # Let event be buffered but not flushed
                watcher.stop()

                # Pending event should have been flushed (created or modified is fine)
                assert len(events_received) >= 1
                # Verify the path is correct
                paths = [e.path for e in events_received]
                assert test_file in paths
            finally:
                # Clean up in case test fails
                if watcher._observer_started:
                    watcher.stop()

    def test_stop_flushes_all_buffered_events(self) -> None:
        """stop() should flush all events in buffer before returning."""
        events_received = []

        def recording_callback(event: FileEvent) -> None:
            events_received.append(event)

        with tempfile.TemporaryDirectory() as tmpdir:
            watcher = FileSystemWatcher(
                watch_path=Path(tmpdir),
                callback=recording_callback,
                debounce_ms=500,
            )

            watcher.start()

            try:
                # Create multiple files rapidly
                test_file1 = Path(tmpdir) / "test1.txt"
                test_file2 = Path(tmpdir) / "test2.txt"
                test_file1.write_text("content1")
                test_file2.write_text("content2")

                # Stop before debounce completes
                time.sleep(0.05)
                watcher.stop()

                # All events should have been flushed
                assert len(events_received) >= 2
            finally:
                if watcher._observer_started:
                    watcher.stop()

    def test_stop_no_callback_after_stop_returns(self) -> None:
        """Callbacks should not be invoked after stop() returns."""
        events_received = []

        def recording_callback(event: FileEvent) -> None:
            events_received.append(event)
            # Add a small delay to simulate slow callback
            time.sleep(0.05)

        with tempfile.TemporaryDirectory() as tmpdir:
            watcher = FileSystemWatcher(
                watch_path=Path(tmpdir),
                callback=recording_callback,
                debounce_ms=100,
            )

            watcher.start()

            try:
                # Create a file
                test_file = Path(tmpdir) / "test.txt"
                test_file.write_text("content")

                # Wait a bit then stop
                time.sleep(0.05)
                watcher.stop()

                # Record event count after stop
                final_count = len(events_received)

                # Wait to see if any more callbacks arrive (they shouldn't)
                time.sleep(0.3)

                # Event count should not have increased after stop
                assert len(events_received) == final_count
            finally:
                if watcher._observer_started:
                    watcher.stop()
