"""Tests for the scheduler watcher."""
import os

import tempfile
from pathlib import Path
from unittest.mock import Mock, patch, call

import pytest

from context_library.adapters.base import BaseAdapter
from context_library.adapters._watching import FileEvent, FileSystemWatcher
from context_library.core.embedder import Embedder
from context_library.core.pipeline import IngestionPipeline
from context_library.core.differ import Differ
from context_library.domains.base import BaseDomain
from context_library.scheduler.watcher import Watcher
from context_library.storage.document_store import DocumentStore
from context_library.storage.models import Domain, NormalizedContent


class MockAdapter(BaseAdapter):
    """Mock adapter for testing."""

    def __init__(self, adapter_id: str, domain: Domain):
        self._adapter_id = adapter_id
        self._domain = domain
        self.fetch_called = False

    def fetch(self, source_ref: str):
        self.fetch_called = True
        return iter([])

    @property
    def adapter_id(self) -> str:
        return self._adapter_id

    @property
    def domain(self) -> Domain:
        return self._domain

    @property
    def normalizer_version(self) -> str:
        return "1.0"


class MockDomain(BaseDomain):
    """Mock domain chunker for testing."""

    def chunk(self, content: NormalizedContent):
        return []


@pytest.fixture
def document_store():
    """Create an in-memory document store."""
    # Use file-based DB to support multi-threaded access
    temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=".db")
    temp_path = temp_file.name
    temp_file.close()
    store = DocumentStore(temp_path)
    yield store
    store.close()
    try:
        os.unlink(temp_path)
    except OSError:
        pass


@pytest.fixture
def embedder():
    """Create an embedder instance."""
    return Embedder(model_name="all-MiniLM-L6-v2")


@pytest.fixture
def differ():
    """Create a differ instance."""
    return Differ()


@pytest.fixture
def pipeline(document_store, embedder, differ):
    """Create a pipeline instance with temp vector store directory."""
    from context_library.storage.chromadb_store import ChromaDBVectorStore
    with tempfile.TemporaryDirectory() as tmpdir:
        vector_store = ChromaDBVectorStore(tmpdir)
        pipeline_obj = IngestionPipeline(
            document_store=document_store,
            embedder=embedder,
            differ=differ,
            vector_store=vector_store,
        )
        yield pipeline_obj


class TestWatcherRegistration:
    """Tests for adapter and watcher registration."""

    def test_register_adds_registration_to_list(self, pipeline):
        """register() should add adapter/chunker/watcher tuple to internal registry."""
        watcher = Watcher(pipeline)
        adapter = MockAdapter("test-adapter", Domain.NOTES)
        chunker = MockDomain()
        file_watcher = Mock(spec=FileSystemWatcher)

        watcher.register(adapter, chunker, file_watcher)

        assert len(watcher._registrations) == 1
        assert watcher._registrations[0] == (adapter, chunker, file_watcher)

    def test_register_multiple_watchers(self, pipeline):
        """register() should allow multiple adapter/watcher registrations."""
        watcher = Watcher(pipeline)
        adapter1 = MockAdapter("adapter-1", Domain.NOTES)
        adapter2 = MockAdapter("adapter-2", Domain.MESSAGES)
        chunker1 = MockDomain()
        chunker2 = MockDomain()
        file_watcher1 = Mock(spec=FileSystemWatcher)
        file_watcher2 = Mock(spec=FileSystemWatcher)

        watcher.register(adapter1, chunker1, file_watcher1)
        watcher.register(adapter2, chunker2, file_watcher2)

        assert len(watcher._registrations) == 2
        assert (adapter1, chunker1, file_watcher1) in watcher._registrations
        assert (adapter2, chunker2, file_watcher2) in watcher._registrations

    def test_register_no_error(self, pipeline):
        """register() should not raise any errors."""
        watcher = Watcher(pipeline)
        adapter = MockAdapter("test-adapter", Domain.NOTES)
        chunker = MockDomain()
        file_watcher = Mock(spec=FileSystemWatcher)

        # Should not raise
        watcher.register(adapter, chunker, file_watcher)

    def test_register_sets_callback_on_file_watcher(self, pipeline):
        """register() should set _callback on the file_watcher."""
        watcher = Watcher(pipeline)
        adapter = MockAdapter("test-adapter", Domain.NOTES)
        chunker = MockDomain()
        file_watcher = Mock(spec=FileSystemWatcher)

        watcher.register(adapter, chunker, file_watcher)

        # Callback should have been set
        assert file_watcher._callback is not None
        assert callable(file_watcher._callback)

    def test_register_callback_calls_handle_webhook(self, pipeline):
        """The registered callback should call handle_webhook() with correct arguments."""
        watcher = Watcher(pipeline)
        adapter = MockAdapter("test-adapter", Domain.NOTES)
        chunker = MockDomain()
        file_watcher = Mock(spec=FileSystemWatcher)

        watcher.register(adapter, chunker, file_watcher)

        # Mock handle_webhook to verify it's called
        watcher.handle_webhook = Mock()

        # Simulate a filesystem event
        event = FileEvent(path=Path("/test/file.txt"), event_type="modified")
        file_watcher._callback(event)

        # handle_webhook should have been called with correct args
        watcher.handle_webhook.assert_called_once_with(
            source_ref="/test/file.txt",
            adapter=adapter,
            domain_chunker=chunker,
        )


class TestWatcherHandleWebhook:
    """Tests for webhook handling and pipeline integration."""

    def test_handle_webhook_calls_pipeline_ingest(self, pipeline):
        """handle_webhook() should call pipeline.ingest() with adapter, chunker, and source_ref."""
        watcher = Watcher(pipeline)
        adapter = MockAdapter("test-adapter", Domain.NOTES)
        chunker = MockDomain()

        with patch.object(pipeline, "ingest") as mock_ingest:
            watcher.handle_webhook(
                source_ref="/test/file.txt",
                adapter=adapter,
                domain_chunker=chunker,
            )

            mock_ingest.assert_called_once_with(adapter, chunker, source_ref="/test/file.txt")

    def test_handle_webhook_logs_exception_on_failure(self, pipeline):
        """handle_webhook() should catch and log exceptions without propagating."""
        watcher = Watcher(pipeline)
        adapter = MockAdapter("test-adapter", Domain.NOTES)
        chunker = MockDomain()

        with patch.object(pipeline, "ingest", side_effect=Exception("Test error")):
            with patch("context_library.scheduler.watcher.logger") as mock_logger:
                # Should not raise
                watcher.handle_webhook(
                    source_ref="/test/file.txt",
                    adapter=adapter,
                    domain_chunker=chunker,
                )

                # logger.exception should have been called
                mock_logger.exception.assert_called_once()
                call_args = mock_logger.exception.call_args[0]
                assert "/test/file.txt" in str(call_args)

    def test_handle_webhook_does_not_propagate_exception(self, pipeline):
        """handle_webhook() should not propagate exceptions."""
        watcher = Watcher(pipeline)
        adapter = MockAdapter("test-adapter", Domain.NOTES)
        chunker = MockDomain()

        with patch.object(
            pipeline, "ingest", side_effect=RuntimeError("Pipeline failed")
        ):
            # Should not raise
            result = watcher.handle_webhook(
                source_ref="/test/file.txt",
                adapter=adapter,
                domain_chunker=chunker,
            )

            # Should return False to indicate failure
            assert result is False
            # Event should be queued for retry
            assert watcher.get_retry_queue_size() == 1


class TestWatcherLifecycle:
    """Tests for start() and stop() lifecycle."""

    def test_start_calls_file_watcher_start(self, pipeline):
        """start() should call start() on all registered file_watchers."""
        watcher = Watcher(pipeline)
        file_watcher1 = Mock(spec=FileSystemWatcher)
        file_watcher2 = Mock(spec=FileSystemWatcher)

        adapter1 = MockAdapter("adapter-1", Domain.NOTES)
        adapter2 = MockAdapter("adapter-2", Domain.MESSAGES)
        chunker1 = MockDomain()
        chunker2 = MockDomain()

        watcher.register(adapter1, chunker1, file_watcher1)
        watcher.register(adapter2, chunker2, file_watcher2)

        watcher.start()

        file_watcher1.start.assert_called_once()
        file_watcher2.start.assert_called_once()

    def test_start_with_no_registrations(self, pipeline):
        """start() should not raise even with no registrations."""
        watcher = Watcher(pipeline)

        # Should not raise
        watcher.start()

    def test_stop_calls_file_watcher_stop(self, pipeline):
        """stop() should call stop() on all registered file_watchers."""
        watcher = Watcher(pipeline)
        file_watcher1 = Mock(spec=FileSystemWatcher)
        file_watcher2 = Mock(spec=FileSystemWatcher)

        adapter1 = MockAdapter("adapter-1", Domain.NOTES)
        adapter2 = MockAdapter("adapter-2", Domain.MESSAGES)
        chunker1 = MockDomain()
        chunker2 = MockDomain()

        watcher.register(adapter1, chunker1, file_watcher1)
        watcher.register(adapter2, chunker2, file_watcher2)

        watcher.stop()

        file_watcher1.stop.assert_called_once()
        file_watcher2.stop.assert_called_once()

    def test_stop_before_start_no_error(self, pipeline):
        """Calling stop() before start() should not raise."""
        watcher = Watcher(pipeline)
        file_watcher = Mock(spec=FileSystemWatcher)

        adapter = MockAdapter("test-adapter", Domain.NOTES)
        chunker = MockDomain()

        watcher.register(adapter, chunker, file_watcher)

        # Should not raise
        watcher.stop()

        file_watcher.stop.assert_called_once()

    def test_stop_with_no_registrations(self, pipeline):
        """stop() should not raise even with no registrations."""
        watcher = Watcher(pipeline)

        # Should not raise
        watcher.stop()

    def test_start_stop_cycle_repeatable(self, pipeline):
        """Watcher should be repeatable with multiple start/stop cycles."""
        watcher = Watcher(pipeline)
        file_watcher = Mock(spec=FileSystemWatcher)

        adapter = MockAdapter("test-adapter", Domain.NOTES)
        chunker = MockDomain()

        watcher.register(adapter, chunker, file_watcher)

        for _ in range(3):
            watcher.start()
            watcher.stop()

        assert file_watcher.start.call_count == 3
        assert file_watcher.stop.call_count == 3


class TestWatcherEventIsolation:
    """Tests for per-event failure isolation."""

    def test_multiple_events_isolated_from_failures(self, pipeline):
        """One failed event should not prevent subsequent events from being processed."""
        watcher = Watcher(pipeline)
        adapter = MockAdapter("test-adapter", Domain.NOTES)
        chunker = MockDomain()
        file_watcher = Mock(spec=FileSystemWatcher)

        watcher.register(adapter, chunker, file_watcher)

        # Mock pipeline.ingest to fail on first call, succeed on second
        with patch.object(
            pipeline, "ingest", side_effect=[Exception("First failure"), None]
        ):
            with patch("context_library.scheduler.watcher.logger"):
                # First event (fails)
                watcher.handle_webhook(
                    source_ref="/test/file1.txt",
                    adapter=adapter,
                    domain_chunker=chunker,
                )

                # Second event (succeeds)
                watcher.handle_webhook(
                    source_ref="/test/file2.txt",
                    adapter=adapter,
                    domain_chunker=chunker,
                )

                # Both should have attempted to call ingest
                assert pipeline.ingest.call_count == 2


class TestWatcherImportability:
    """Tests for module imports."""

    def test_watcher_imports_correctly(self):
        """Watcher should be importable from context_library.scheduler.watcher."""
        from context_library.scheduler.watcher import Watcher as ImportedWatcher

        assert ImportedWatcher is not None

    def test_watcher_can_be_imported_from_scheduler_package(self):
        """Watcher should be importable from context_library.scheduler."""
        from context_library.scheduler import watcher as watcher_module

        assert hasattr(watcher_module, "Watcher")


class TestWatcherIntegration:
    """Integration tests with mocked components."""

    def test_full_event_flow_with_mocked_components(self, pipeline):
        """Test complete event flow: register -> event -> handle_webhook -> ingest."""
        watcher = Watcher(pipeline)
        adapter = MockAdapter("test-adapter", Domain.NOTES)
        chunker = MockDomain()
        file_watcher = Mock(spec=FileSystemWatcher)

        watcher.register(adapter, chunker, file_watcher)

        # Capture the callback that was set
        callback = file_watcher._callback

        with patch.object(pipeline, "ingest") as mock_ingest:
            # Simulate a filesystem event
            event = FileEvent(path=Path("/test/changed.txt"), event_type="modified")
            callback(event)

            # Pipeline should have been ingested with source_ref
            mock_ingest.assert_called_once_with(adapter, chunker, source_ref="/test/changed.txt")

    def test_multiple_adapters_independent_events(self, pipeline):
        """Events from different adapters should be handled independently."""
        watcher = Watcher(pipeline)
        adapter1 = MockAdapter("adapter-1", Domain.NOTES)
        adapter2 = MockAdapter("adapter-2", Domain.MESSAGES)
        chunker1 = MockDomain()
        chunker2 = MockDomain()
        file_watcher1 = Mock(spec=FileSystemWatcher)
        file_watcher2 = Mock(spec=FileSystemWatcher)

        watcher.register(adapter1, chunker1, file_watcher1)
        watcher.register(adapter2, chunker2, file_watcher2)

        with patch.object(pipeline, "ingest") as mock_ingest:
            # Trigger events from both adapters
            event1 = FileEvent(path=Path("/test/file1.txt"), event_type="modified")
            file_watcher1._callback(event1)

            event2 = FileEvent(path=Path("/test/file2.txt"), event_type="created")
            file_watcher2._callback(event2)

            # Both should have called ingest
            assert mock_ingest.call_count == 2
            calls = mock_ingest.call_args_list
            assert call(adapter1, chunker1, source_ref="/test/file1.txt") in calls
            assert call(adapter2, chunker2, source_ref="/test/file2.txt") in calls

    def test_watcher_with_mocked_pipeline(self):
        """Test Watcher with a completely mocked pipeline."""
        pipeline = Mock(spec=IngestionPipeline)
        watcher = Watcher(pipeline)

        adapter = MockAdapter("test-adapter", Domain.NOTES)
        chunker = MockDomain()
        file_watcher = Mock(spec=FileSystemWatcher)

        watcher.register(adapter, chunker, file_watcher)

        callback = file_watcher._callback
        event = FileEvent(path=Path("/test/file.txt"), event_type="modified")

        callback(event)

        # Pipeline.ingest should have been called with source_ref
        pipeline.ingest.assert_called_once_with(adapter, chunker, source_ref="/test/file.txt")


class TestWatcherCallbackChaining:
    """Tests for callback chaining to preserve adapter's internal callbacks."""

    def test_register_chains_original_callback(self, pipeline):
        """register() should chain the original callback before the webhook handler."""
        watcher = Watcher(pipeline)
        adapter = MockAdapter("test-adapter", Domain.NOTES)
        chunker = MockDomain()

        # Create a mock with an existing callback
        original_callback = Mock()
        file_watcher = Mock(spec=FileSystemWatcher)
        file_watcher._callback = original_callback

        watcher.register(adapter, chunker, file_watcher)

        # Simulate a filesystem event
        event = FileEvent(path=Path("/test/file.txt"), event_type="modified")
        file_watcher._callback(event)

        # Original callback should have been called first
        original_callback.assert_called_once_with(event)

    def test_register_chains_original_callback_with_webhook(self, pipeline):
        """register() should call both original callback and webhook handler."""
        watcher = Watcher(pipeline)
        adapter = MockAdapter("test-adapter", Domain.NOTES)
        chunker = MockDomain()

        # Create a mock with an existing callback
        original_callback = Mock()
        file_watcher = Mock(spec=FileSystemWatcher)
        file_watcher._callback = original_callback

        watcher.register(adapter, chunker, file_watcher)

        # Patch handle_webhook to verify it's called
        with patch.object(watcher, "handle_webhook") as mock_webhook:
            event = FileEvent(path=Path("/test/file.txt"), event_type="modified")
            file_watcher._callback(event)

            # Both should have been called
            original_callback.assert_called_once_with(event)
            mock_webhook.assert_called_once_with(
                source_ref="/test/file.txt",
                adapter=adapter,
                domain_chunker=chunker,
            )

    def test_register_handles_original_callback_exception(self, pipeline):
        """register() should catch exceptions from original callback and NOT continue to handle_webhook."""
        watcher = Watcher(pipeline)
        adapter = MockAdapter("test-adapter", Domain.NOTES)
        chunker = MockDomain()

        # Create a callback that raises
        original_callback = Mock(side_effect=RuntimeError("Callback failed"))
        file_watcher = Mock(spec=FileSystemWatcher)
        file_watcher._callback = original_callback

        watcher.register(adapter, chunker, file_watcher)

        # Should not raise even though original callback fails
        with patch("context_library.scheduler.watcher.logger"):
            with patch.object(watcher, "handle_webhook") as mock_webhook:
                event = FileEvent(path=Path("/test/file.txt"), event_type="modified")
                file_watcher._callback(event)

                # Original callback was called and failed
                original_callback.assert_called_once_with(event)
                # Webhook handler should NOT be called if adapter callback fails
                # (could leave adapter state inconsistent, e.g., stale vault cache)
                mock_webhook.assert_not_called()


class TestWatcherRetryMechanism:
    """Tests for retry queue and failed event handling."""

    def test_failed_event_queued_for_retry(self, pipeline):
        """Failed events should be queued for retry."""
        watcher = Watcher(pipeline)
        adapter = MockAdapter("test-adapter", Domain.NOTES)
        chunker = MockDomain()

        with patch.object(
            pipeline, "ingest", side_effect=RuntimeError("Pipeline failed")
        ):
            with patch("context_library.scheduler.watcher.logger"):
                watcher.handle_webhook(
                    source_ref="/test/file.txt",
                    adapter=adapter,
                    domain_chunker=chunker,
                )

                # Should be in retry queue
                assert watcher.get_retry_queue_size() == 1

    def test_retry_queue_respects_max_retries(self, pipeline):
        """Events should be dropped after max_retries is exceeded."""
        watcher = Watcher(pipeline, max_retries=2)
        adapter = MockAdapter("test-adapter", Domain.NOTES)
        chunker = MockDomain()

        with patch.object(
            pipeline, "ingest", side_effect=RuntimeError("Pipeline failed")
        ):
            with patch("context_library.scheduler.watcher.logger"):
                # First failure
                watcher.handle_webhook(
                    source_ref="/test/file.txt",
                    adapter=adapter,
                    domain_chunker=chunker,
                    retry_count=0,
                )
                assert watcher.get_retry_queue_size() == 1

                # Second failure (retry 1)
                watcher.handle_webhook(
                    source_ref="/test/file.txt",
                    adapter=adapter,
                    domain_chunker=chunker,
                    retry_count=1,
                )
                assert watcher.get_retry_queue_size() == 2

                # Third failure (retry 2) - should not be queued (exceeds max_retries)
                watcher.handle_webhook(
                    source_ref="/test/file.txt",
                    adapter=adapter,
                    domain_chunker=chunker,
                    retry_count=2,
                )
                assert watcher.get_retry_queue_size() == 2

    def test_flush_retry_queue_retries_events(self, pipeline):
        """flush_retry_queue() should process queued events."""
        watcher = Watcher(pipeline)
        adapter = MockAdapter("test-adapter", Domain.NOTES)
        chunker = MockDomain()

        # Queue a failed event
        with patch.object(
            pipeline, "ingest", side_effect=RuntimeError("Pipeline failed")
        ):
            with patch("context_library.scheduler.watcher.logger"):
                watcher.handle_webhook(
                    source_ref="/test/file.txt",
                    adapter=adapter,
                    domain_chunker=chunker,
                )

        assert watcher.get_retry_queue_size() == 1

        # Mock ingest to succeed on retry
        with patch.object(pipeline, "ingest") as mock_ingest:
            watcher.flush_retry_queue()

            # Retry queue should be processed and empty
            assert watcher.get_retry_queue_size() == 0
            # ingest should have been called during flush with source_ref
            mock_ingest.assert_called_once_with(adapter, chunker, source_ref="/test/file.txt")

    def test_successful_handle_webhook_not_queued(self, pipeline):
        """Successful events should not be queued."""
        watcher = Watcher(pipeline)
        adapter = MockAdapter("test-adapter", Domain.NOTES)
        chunker = MockDomain()

        with patch.object(pipeline, "ingest"):
            result = watcher.handle_webhook(
                source_ref="/test/file.txt",
                adapter=adapter,
                domain_chunker=chunker,
            )

            # Should return True for success
            assert result is True
            # No retry queue
            assert watcher.get_retry_queue_size() == 0

    def test_stop_flushes_retry_queue(self, pipeline):
        """stop() should flush the retry queue before returning."""
        watcher = Watcher(pipeline)
        file_watcher = Mock(spec=FileSystemWatcher)
        adapter = MockAdapter("test-adapter", Domain.NOTES)
        chunker = MockDomain()

        watcher.register(adapter, chunker, file_watcher)

        # Queue a failed event
        with patch.object(
            pipeline, "ingest", side_effect=RuntimeError("Pipeline failed")
        ):
            with patch("context_library.scheduler.watcher.logger"):
                watcher.handle_webhook(
                    source_ref="/test/file.txt",
                    adapter=adapter,
                    domain_chunker=chunker,
                )

        assert watcher.get_retry_queue_size() == 1

        # Mock ingest to succeed on stop's retry flush
        with patch.object(pipeline, "ingest"):
            watcher.stop()

            # Queue should be flushed
            assert watcher.get_retry_queue_size() == 0
            # file_watcher.stop() should have been called
            file_watcher.stop.assert_called_once()


class TestWatcherPollStrategyValidation:
    """Tests for poll_strategy validation."""

    def test_register_rejects_pull_strategy(self, pipeline):
        """register() should reject adapters with PULL poll_strategy."""
        from context_library.storage.models import PollStrategy

        watcher = Watcher(pipeline)
        adapter = MockAdapter("test-adapter", Domain.NOTES)
        # Mock an adapter with PULL strategy
        adapter._poll_strategy = PollStrategy.PULL
        chunker = MockDomain()
        file_watcher = Mock(spec=FileSystemWatcher)

        with pytest.raises(ValueError, match="PollStrategy.PULL"):
            watcher.register(adapter, chunker, file_watcher)

    def test_register_rejects_webhook_strategy(self, pipeline):
        """register() should reject adapters with WEBHOOK poll_strategy."""
        from context_library.storage.models import PollStrategy

        watcher = Watcher(pipeline)
        adapter = MockAdapter("test-adapter", Domain.NOTES)
        # Mock an adapter with WEBHOOK strategy
        adapter._poll_strategy = PollStrategy.WEBHOOK
        chunker = MockDomain()
        file_watcher = Mock(spec=FileSystemWatcher)

        with pytest.raises(ValueError, match="PollStrategy.WEBHOOK"):
            watcher.register(adapter, chunker, file_watcher)

    def test_register_accepts_push_strategy(self, pipeline):
        """register() should accept adapters with PUSH poll_strategy."""
        from context_library.storage.models import PollStrategy

        watcher = Watcher(pipeline)
        adapter = MockAdapter("test-adapter", Domain.NOTES)
        # Mock an adapter with PUSH strategy
        adapter._poll_strategy = PollStrategy.PUSH
        chunker = MockDomain()
        file_watcher = Mock(spec=FileSystemWatcher)

        # Should not raise
        watcher.register(adapter, chunker, file_watcher)
        assert len(watcher._registrations) == 1

    def test_register_accepts_adapter_without_poll_strategy(self, pipeline):
        """register() should accept adapters without _poll_strategy attribute."""
        watcher = Watcher(pipeline)
        adapter = MockAdapter("test-adapter", Domain.NOTES)
        # No _poll_strategy attribute set
        chunker = MockDomain()
        file_watcher = Mock(spec=FileSystemWatcher)

        # Should not raise
        watcher.register(adapter, chunker, file_watcher)
        assert len(watcher._registrations) == 1


class TestWatcherPeriodicDraining:
    """Tests for periodic retry queue draining."""

    def test_periodic_drain_thread_started_on_start(self, pipeline):
        """start() should start the periodic drain thread."""
        watcher = Watcher(pipeline, drain_interval_sec=0.1)
        file_watcher = Mock(spec=FileSystemWatcher)
        adapter = MockAdapter("test-adapter", Domain.NOTES)
        chunker = MockDomain()

        watcher.register(adapter, chunker, file_watcher)
        watcher.start()

        # Drain thread should be running
        assert watcher._drain_thread is not None
        assert watcher._drain_thread.is_alive()

        # Clean up
        watcher.stop()

    def test_periodic_drain_stops_on_stop(self, pipeline):
        """stop() should stop the periodic drain thread."""
        watcher = Watcher(pipeline, drain_interval_sec=0.1)
        file_watcher = Mock(spec=FileSystemWatcher)
        adapter = MockAdapter("test-adapter", Domain.NOTES)
        chunker = MockDomain()

        watcher.register(adapter, chunker, file_watcher)
        watcher.start()

        assert watcher._drain_thread is not None
        assert watcher._drain_thread.is_alive()

        watcher.stop()

        # Drain thread should have stopped
        assert not watcher._drain_thread.is_alive()

    def test_periodic_drain_flushes_queue(self, pipeline):
        """Periodic drain should flush the retry queue."""
        import time
        watcher = Watcher(pipeline, drain_interval_sec=0.2, max_retries=1)
        adapter = MockAdapter("test-adapter", Domain.NOTES)
        chunker = MockDomain()
        file_watcher = Mock(spec=FileSystemWatcher)

        watcher.register(adapter, chunker, file_watcher)

        # Mock pipeline.ingest to fail initially, then succeed
        call_count = {"count": 0}

        def ingest_side_effect(*args, **kwargs):
            call_count["count"] += 1
            # First call (from handle_webhook) fails; subsequent calls (from drain) succeed
            if call_count["count"] == 1:
                raise RuntimeError("Pipeline failed initially")
            # Subsequent calls succeed (drain succeeds)

        with patch.object(pipeline, "ingest", side_effect=ingest_side_effect):
            with patch("context_library.scheduler.watcher.logger"):
                # Initial event handling - this will fail and queue the event
                watcher.handle_webhook(
                    source_ref="/test/file.txt",
                    adapter=adapter,
                    domain_chunker=chunker,
                )

        assert watcher.get_retry_queue_size() == 1

        # Start watcher to trigger periodic drain
        watcher.start()

        # Wait for drain cycles to complete and process the queue
        # With drain_interval=0.2, we need ~0.4s for at least 2 drain cycles
        time.sleep(0.6)

        watcher.stop()

        # Verify queue is empty after successful drain
        assert watcher.get_retry_queue_size() == 0, "Retry queue should be empty after successful drain"
