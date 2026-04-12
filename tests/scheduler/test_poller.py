"""Tests for the scheduler poller."""
import os

import tempfile
import threading
import time
from unittest.mock import Mock, patch

import pytest

from context_library.adapters.base import BaseAdapter
from context_library.core.embedder import Embedder
from context_library.core.pipeline import IngestionPipeline
from context_library.core.differ import Differ
from context_library.domains.base import BaseDomain
from context_library.scheduler.poller import Poller
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


class TestPollerInitialization:
    """Tests for Poller initialization and validation."""

    def test_initialization_with_defaults(self, pipeline, document_store):
        """Poller initializes with default tick_interval."""
        poller = Poller(pipeline, document_store)

        assert poller._tick_interval == 60.0

    def test_initialization_with_custom_interval(self, pipeline, document_store):
        """Poller initializes with custom tick_interval."""
        poller = Poller(pipeline, document_store, tick_interval=30.0)

        assert poller._tick_interval == 30.0

    def test_initialization_rejects_zero_tick_interval(self, pipeline, document_store):
        """Poller rejects tick_interval=0.0."""
        with pytest.raises(ValueError, match="tick_interval must be a positive number"):
            Poller(pipeline, document_store, tick_interval=0.0)

    def test_initialization_rejects_negative_tick_interval(self, pipeline, document_store):
        """Poller rejects negative tick_interval."""
        with pytest.raises(ValueError, match="tick_interval must be a positive number"):
            Poller(pipeline, document_store, tick_interval=-1.0)

    def test_initialization_rejects_negative_tick_interval_large(
        self, pipeline, document_store
    ):
        """Poller rejects large negative tick_interval."""
        with pytest.raises(ValueError, match="tick_interval must be a positive number"):
            Poller(pipeline, document_store, tick_interval=-60.0)


class TestPollerRegistration:
    """Tests for adapter registration."""

    def test_register_adds_adapter_to_registry(self, pipeline, document_store):
        """register() should add adapter/chunker pair to internal registry."""
        poller = Poller(pipeline, document_store)
        adapter = MockAdapter("test-adapter", Domain.NOTES)
        chunker = MockDomain()

        poller.register(adapter, chunker)

        assert len(poller._registered) == 1
        assert poller._registered[0] == (adapter, chunker)

    def test_register_multiple_adapters(self, pipeline, document_store):
        """register() should allow multiple adapter registrations."""
        poller = Poller(pipeline, document_store)
        adapter1 = MockAdapter("adapter-1", Domain.NOTES)
        adapter2 = MockAdapter("adapter-2", Domain.MESSAGES)
        chunker1 = MockDomain()
        chunker2 = MockDomain()

        poller.register(adapter1, chunker1)
        poller.register(adapter2, chunker2)

        assert len(poller._registered) == 2
        assert (adapter1, chunker1) in poller._registered
        assert (adapter2, chunker2) in poller._registered

    def test_register_no_error(self, pipeline, document_store):
        """register() should not raise any errors."""
        poller = Poller(pipeline, document_store)
        adapter = MockAdapter("test-adapter", Domain.NOTES)
        chunker = MockDomain()

        # Should not raise
        poller.register(adapter, chunker)


class TestPollerLifecycle:
    """Tests for start() and stop() lifecycle."""

    def test_start_spawns_daemon_thread(self, pipeline, document_store):
        """start() should spawn a daemon thread."""
        poller = Poller(pipeline, document_store, tick_interval=0.5)

        with patch.object(
            document_store, "get_sources_due_for_poll", return_value=[]
        ):
            poller.start()

            try:
                assert poller._thread is not None
                assert poller._thread.is_alive()
                assert poller._thread.daemon is True
            finally:
                poller.stop()

    def test_stop_joins_thread(self, pipeline, document_store):
        """stop() should wait for thread to exit."""
        poller = Poller(pipeline, document_store, tick_interval=0.5)

        with patch.object(
            document_store, "get_sources_due_for_poll", return_value=[]
        ):
            poller.start()

            assert poller._thread is not None
            assert poller._thread.is_alive()

            poller.stop()

            # After stop(), thread should have exited and _thread should be None
            assert poller._thread is None

    def test_stop_before_start_no_error(self, pipeline, document_store):
        """Calling stop() before start() should not raise."""
        poller = Poller(pipeline, document_store)

        # Should not raise
        poller.stop()

    def test_stop_clears_stop_event(self, pipeline, document_store):
        """After stop(), calling start() again should work (event cleared)."""
        poller = Poller(pipeline, document_store, tick_interval=0.1)

        with patch.object(
            document_store, "get_sources_due_for_poll", return_value=[]
        ):
            poller.start()
            poller.stop()

            # Should be able to start again
            poller.start()
            try:
                assert poller._thread is not None
                assert poller._thread.is_alive()
            finally:
                poller.stop()

    def test_start_already_running_is_noop(self, pipeline, document_store):
        """Calling start() when thread is already running should be a no-op."""
        poller = Poller(pipeline, document_store, tick_interval=0.5)

        with patch.object(
            document_store, "get_sources_due_for_poll", return_value=[]
        ):
            poller.start()

            thread1 = poller._thread
            time.sleep(0.1)

            # Call start again
            poller.start()
            thread2 = poller._thread

            # Should be the same thread
            assert thread1 is thread2

            poller.stop()

    def test_start_stop_cycle_repeatable(self, pipeline, document_store):
        """Poller should be restartable after stop()."""
        poller = Poller(pipeline, document_store, tick_interval=0.1)

        with patch.object(
            document_store, "get_sources_due_for_poll", return_value=[]
        ):
            for _ in range(3):
                poller.start()
                time.sleep(0.05)
                poller.stop()
                assert poller._thread is None


class TestPollerTicking:
    """Tests for polling tick logic."""

    def test_tick_queries_due_sources(self, pipeline, document_store):
        """_tick() should query document_store.get_sources_due_for_poll()."""
        poller = Poller(pipeline, document_store)

        with patch.object(
            document_store, "get_sources_due_for_poll", return_value=[]
        ) as mock_get_due:
            poller._tick()

            mock_get_due.assert_called_once()

    def test_tick_ingests_due_sources(self, pipeline, document_store):
        """_tick() should call pipeline.ingest() for each due source with source_ref."""
        adapter = MockAdapter("test-adapter", Domain.NOTES)
        chunker = MockDomain()

        poller = Poller(pipeline, document_store)
        poller.register(adapter, chunker)

        # Mock document_store to return a due source
        due_source = {
            "source_id": "source-1",
            "adapter_id": "test-adapter",
            "origin_ref": "/path/to/source",
            "poll_interval_sec": 60,
            "last_fetched_at": None,
        }

        with patch.object(
            document_store, "get_sources_due_for_poll", return_value=[due_source]
        ):
            with patch.object(pipeline, "ingest") as mock_ingest:
                poller._tick()

                mock_ingest.assert_called_once_with(
                    adapter, chunker, source_ref="/path/to/source"
                )

    def test_tick_updates_last_fetched_at_on_success(self, pipeline, document_store):
        """_tick() should call update_last_fetched_at() after successful ingest."""
        adapter = MockAdapter("test-adapter", Domain.NOTES)
        chunker = MockDomain()

        poller = Poller(pipeline, document_store)
        poller.register(adapter, chunker)

        due_source = {
            "source_id": "source-1",
            "adapter_id": "test-adapter",
            "origin_ref": "/path/to/source",
            "poll_interval_sec": 60,
            "last_fetched_at": None,
        }

        with patch.object(
            document_store, "get_sources_due_for_poll", return_value=[due_source]
        ):
            with patch.object(pipeline, "ingest"):
                with patch.object(
                    document_store, "update_last_fetched_at"
                ) as mock_update:
                    poller._tick()

                    mock_update.assert_called_once_with("source-1")

    def test_tick_handles_missing_adapter(self, pipeline, document_store):
        """_tick() should handle missing adapter gracefully."""
        poller = Poller(pipeline, document_store)

        due_source = {
            "source_id": "source-1",
            "adapter_id": "missing-adapter",
            "origin_ref": "/path/to/source",
            "poll_interval_sec": 60,
            "last_fetched_at": None,
        }

        with patch.object(
            document_store, "get_sources_due_for_poll", return_value=[due_source]
        ):
            with patch.object(pipeline, "ingest") as mock_ingest:
                # Should not raise
                poller._tick()

                # Should not have called ingest
                mock_ingest.assert_not_called()

    def test_tick_isolates_per_source_failures(self, pipeline, document_store):
        """_tick() should continue processing after one source fails."""
        adapter = MockAdapter("test-adapter", Domain.NOTES)
        chunker = MockDomain()

        poller = Poller(pipeline, document_store)
        poller.register(adapter, chunker)

        due_sources = [
            {
                "source_id": "source-1",
                "adapter_id": "test-adapter",
                "origin_ref": "/path/to/source-1",
                "poll_interval_sec": 60,
                "last_fetched_at": None,
            },
            {
                "source_id": "source-2",
                "adapter_id": "test-adapter",
                "origin_ref": "/path/to/source-2",
                "poll_interval_sec": 60,
                "last_fetched_at": None,
            },
        ]

        with patch.object(
            document_store, "get_sources_due_for_poll", return_value=due_sources
        ):
            # Make first ingest raise, second succeed
            pipeline.ingest = Mock(side_effect=[Exception("Test error"), {}])

            with patch.object(
                document_store, "update_last_fetched_at"
            ) as mock_update:
                # Should not raise
                poller._tick()

                # Both sources should have been attempted
                assert pipeline.ingest.call_count == 2
                # update_last_fetched_at should only be called for the successful source
                mock_update.assert_called_once_with("source-2")

    def test_tick_logs_failure_at_info_level_on_first_failure(
        self, pipeline, document_store
    ):
        """_tick() should log at INFO level on first/second failure (transient)."""
        adapter = MockAdapter("test-adapter", Domain.NOTES)
        chunker = MockDomain()

        poller = Poller(pipeline, document_store)
        poller.register(adapter, chunker)

        due_source = {
            "source_id": "source-1",
            "adapter_id": "test-adapter",
            "origin_ref": "/path/to/source",
            "poll_interval_sec": 60,
            "last_fetched_at": None,
        }

        with patch.object(
            document_store, "get_sources_due_for_poll", return_value=[due_source]
        ):
            with patch.object(pipeline, "ingest", side_effect=Exception("Test error")):
                with patch("context_library.scheduler.poller.logger") as mock_logger:
                    poller._tick()

                    # First failure should log at INFO level (transient)
                    mock_logger.info.assert_called_once()
                    call_args = str(mock_logger.info.call_args)
                    assert "source-1" in call_args
                    assert "transient" in call_args

    def test_tick_logs_failure_at_warning_level_after_3_failures(
        self, pipeline, document_store
    ):
        """_tick() should log at WARNING level after 3 consecutive failures."""
        adapter = MockAdapter("test-adapter", Domain.NOTES)
        chunker = MockDomain()

        poller = Poller(pipeline, document_store)
        poller.register(adapter, chunker)

        due_source = {
            "source_id": "source-1",
            "adapter_id": "test-adapter",
            "origin_ref": "/path/to/source",
            "poll_interval_sec": 60,
            "last_fetched_at": None,
        }

        with patch.object(
            document_store, "get_sources_due_for_poll", return_value=[due_source]
        ):
            with patch.object(pipeline, "ingest", side_effect=Exception("Test error")):
                with patch("context_library.scheduler.poller.logger") as mock_logger:
                    # First tick: failure 1 (INFO level)
                    poller._tick()
                    mock_logger.info.assert_called_once()
                    mock_logger.warning.assert_not_called()

                    # Second tick: failure 2 (INFO level)
                    mock_logger.reset_mock()
                    poller._tick()
                    mock_logger.info.assert_called_once()
                    mock_logger.warning.assert_not_called()

                    # Third tick: failure 3 (WARNING level)
                    mock_logger.reset_mock()
                    poller._tick()
                    mock_logger.warning.assert_called_once()
                    call_args = str(mock_logger.warning.call_args)
                    assert "source-1" in call_args
                    assert "WARNING level" in call_args

    def test_tick_logs_failure_at_error_level_after_6_failures(
        self, pipeline, document_store
    ):
        """_tick() should log at ERROR level after 6 consecutive failures."""
        adapter = MockAdapter("test-adapter", Domain.NOTES)
        chunker = MockDomain()

        poller = Poller(pipeline, document_store)
        poller.register(adapter, chunker)

        due_source = {
            "source_id": "source-1",
            "adapter_id": "test-adapter",
            "origin_ref": "/path/to/source",
            "poll_interval_sec": 60,
            "last_fetched_at": None,
        }

        with patch.object(
            document_store, "get_sources_due_for_poll", return_value=[due_source]
        ):
            with patch.object(pipeline, "ingest", side_effect=Exception("Test error")):
                with patch("context_library.scheduler.poller.logger") as mock_logger:
                    # Simulate 6 failures (ticks 1-6)
                    for tick_num in range(6):
                        mock_logger.reset_mock()
                        poller._tick()

                        if tick_num < 2:
                            # Failures 1-2: INFO level
                            mock_logger.info.assert_called_once()
                            mock_logger.error.assert_not_called()
                        elif tick_num < 5:
                            # Failures 3-5: WARNING level
                            mock_logger.warning.assert_called_once()
                            mock_logger.error.assert_not_called()
                        else:
                            # Failure 6+: ERROR level
                            mock_logger.error.assert_called_once()
                            call_args = str(mock_logger.error.call_args)
                            assert "source-1" in call_args
                            assert "ERROR level" in call_args


class TestPollerBackgroundThread:
    """Tests for background thread behavior."""

    def test_background_thread_periodically_ticks(self, pipeline, document_store):
        """Background thread should call _tick() periodically."""
        poller = Poller(pipeline, document_store, tick_interval=0.1)

        tick_count = {"count": 0}

        original_tick = poller._tick

        def counting_tick():
            tick_count["count"] += 1
            original_tick()

        poller._tick = counting_tick

        with patch.object(
            document_store, "get_sources_due_for_poll", return_value=[]
        ):
            poller.start()

            # Let it run for ~0.3 seconds (should have at least 2 ticks)
            time.sleep(0.3)

            poller.stop()

        # Should have ticked at least twice
        assert tick_count["count"] >= 2

    def test_stop_event_halts_thread(self, pipeline, document_store):
        """Setting _stop_event should halt the thread within tick_interval."""
        poller = Poller(pipeline, document_store, tick_interval=1.0)

        with patch.object(
            document_store, "get_sources_due_for_poll", return_value=[]
        ):
            poller.start()
            thread = poller._thread

            # Stop should complete quickly (within a couple seconds)
            start_time = time.time()
            poller.stop()
            elapsed = time.time() - start_time

            # Thread should have joined quickly (much less than tick_interval)
            assert elapsed < 3.0
            assert not thread.is_alive()

    def test_stop_timeout_on_hung_thread(self, pipeline, document_store):
        """stop() should timeout if thread is hung on network call and log error."""
        import threading as thread_module

        poller = Poller(pipeline, document_store, tick_interval=0.1)

        # Use an event to make the background thread hang indefinitely during _run
        hung_event = thread_module.Event()
        resume_event = thread_module.Event()

        # Patch _run to hang instead of the normal loop

        def hanging_run():
            # Signal that we're about to hang
            hung_event.set()
            # Hang indefinitely - simulating thread stuck in network call
            resume_event.wait(timeout=10.0)

        poller._run = hanging_run

        with patch.object(
            document_store, "get_sources_due_for_poll", return_value=[]
        ):
            poller.start()
            thread = poller._thread

            # Wait for thread to be hanging
            hung_event.wait(timeout=2.0)

            # Call stop - should timeout since thread is hung
            with patch("context_library.scheduler.poller.logger") as mock_logger:
                poller.stop()

                # Should have logged an error about timeout
                mock_logger.error.assert_called_once()
                error_call = str(mock_logger.error.call_args)
                assert "timeout" in error_call.lower() or "did not exit" in error_call

            # _thread should NOT be cleared because thread didn't exit
            assert poller._thread is not None

            # Clean up: resume the hung thread
            resume_event.set()
            thread.join(timeout=1.0)


class TestPollerIntegration:
    """Integration tests with real pipeline and document store."""

    def test_poller_imports_correctly(self):
        """Poller should be importable from context_library.scheduler.poller."""
        from context_library.scheduler.poller import Poller as ImportedPoller

        assert ImportedPoller is not None

    def test_full_lifecycle_with_mocked_pipeline(self, document_store, embedder, differ):
        """Test full start/register/stop lifecycle with mocked pipeline."""
        pipeline = Mock(spec=IngestionPipeline)
        adapter = MockAdapter("test-adapter", Domain.NOTES)
        chunker = MockDomain()

        poller = Poller(pipeline, document_store, tick_interval=0.1)
        poller.register(adapter, chunker)

        # Mock document_store to return a due source on first call
        call_count = {"count": 0}

        def counting_get_due():
            call_count["count"] += 1
            if call_count["count"] == 1:
                return [
                    {
                        "source_id": "source-1",
                        "adapter_id": "test-adapter",
                        "origin_ref": "/path/to/source",
                        "poll_interval_sec": 60,
                        "last_fetched_at": None,
                    }
                ]
            return []

        document_store.get_sources_due_for_poll = counting_get_due

        poller.start()
        time.sleep(0.2)
        poller.stop()

        # Pipeline.ingest should have been called at least once
        assert pipeline.ingest.called


class TestTriggerImmediateIngest:
    """Tests for trigger_immediate_ingest() method."""

    def test_trigger_returns_false_if_poller_stopped(self, pipeline, document_store):
        """trigger_immediate_ingest() should raise PollerNotRunningError if poller is stopped."""
        from context_library.scheduler.exceptions import PollerNotRunningError

        poller = Poller(pipeline, document_store)
        adapter = MockAdapter("test-adapter", Domain.NOTES)
        chunker = MockDomain()

        poller.register(adapter, chunker)

        # Poller not started, so should raise PollerNotRunningError
        with pytest.raises(PollerNotRunningError):
            poller.trigger_immediate_ingest("test-adapter")

    def test_trigger_returns_false_if_adapter_not_registered(self, pipeline, document_store):
        """trigger_immediate_ingest() should raise AdapterNotRegisteredError for unknown adapter."""
        from context_library.scheduler.exceptions import AdapterNotRegisteredError

        poller = Poller(pipeline, document_store, tick_interval=0.5)

        with patch.object(
            document_store, "get_sources_due_for_poll", return_value=[]
        ):
            poller.start()

            try:
                with pytest.raises(AdapterNotRegisteredError):
                    poller.trigger_immediate_ingest("unknown-adapter")
            finally:
                poller.stop()

    def test_trigger_returns_false_if_no_sources(self, pipeline, document_store):
        """trigger_immediate_ingest() should raise NoSourcesError if adapter has no sources."""
        from context_library.scheduler.exceptions import NoSourcesError

        adapter = MockAdapter("test-adapter", Domain.NOTES)
        chunker = MockDomain()

        poller = Poller(pipeline, document_store, tick_interval=0.5)
        poller.register(adapter, chunker)

        with patch.object(
            document_store, "get_sources_due_for_poll", return_value=[]
        ):
            with patch.object(
                document_store, "get_sources_for_adapter", return_value=[]
            ):
                poller.start()

                try:
                    with pytest.raises(NoSourcesError):
                        poller.trigger_immediate_ingest("test-adapter")
                finally:
                    poller.stop()

    def test_trigger_calls_ingest_for_all_sources(self, pipeline, document_store):
        """trigger_immediate_ingest() should call ingest for all sources of the adapter."""
        adapter = MockAdapter("test-adapter", Domain.NOTES)
        chunker = MockDomain()

        poller = Poller(pipeline, document_store, tick_interval=0.5)
        poller.register(adapter, chunker)

        # Mock sources for the adapter
        sources = [
            {"source_id": "source-1", "adapter_id": "test-adapter", "origin_ref": "/path/1"},
            {"source_id": "source-2", "adapter_id": "test-adapter", "origin_ref": "/path/2"},
            {"source_id": "source-3", "adapter_id": "test-adapter", "origin_ref": "/path/3"},
        ]

        with (
            patch.object(document_store, "get_sources_due_for_poll", return_value=[]),
            patch.object(document_store, "get_sources_for_adapter", return_value=sources),
            patch.object(pipeline, "ingest"),
            patch.object(document_store, "update_last_fetched_at"),
        ):
            poller.start()

            try:
                result = poller.trigger_immediate_ingest("test-adapter")
                assert result is True

                # Wait for background thread to process
                time.sleep(0.2)

                # Should have called ingest 3 times (once per source)
                assert pipeline.ingest.call_count == 3
            finally:
                poller.stop()

    def test_trigger_passes_correct_source_ref(self, pipeline, document_store):
        """trigger_immediate_ingest() should pass origin_ref as source_ref to ingest."""
        adapter = MockAdapter("test-adapter", Domain.NOTES)
        chunker = MockDomain()

        poller = Poller(pipeline, document_store, tick_interval=0.5)
        poller.register(adapter, chunker)

        sources = [
            {"source_id": "source-1", "adapter_id": "test-adapter", "origin_ref": "/specific/path"},
        ]

        with (
            patch.object(document_store, "get_sources_due_for_poll", return_value=[]),
            patch.object(document_store, "get_sources_for_adapter", return_value=sources),
            patch.object(pipeline, "ingest") as mock_ingest,
            patch.object(document_store, "update_last_fetched_at"),
        ):
            poller.start()

            try:
                poller.trigger_immediate_ingest("test-adapter")
                time.sleep(0.2)

                # Verify ingest was called with correct source_ref
                mock_ingest.assert_called_once_with(
                    adapter, chunker, source_ref="/specific/path"
                )
            finally:
                poller.stop()

    def test_trigger_updates_last_fetched_at_on_success(self, pipeline, document_store):
        """trigger_immediate_ingest() should update last_fetched_at after successful ingest."""
        adapter = MockAdapter("test-adapter", Domain.NOTES)
        chunker = MockDomain()

        poller = Poller(pipeline, document_store, tick_interval=0.5)
        poller.register(adapter, chunker)

        sources = [
            {"source_id": "source-1", "adapter_id": "test-adapter", "origin_ref": "/path"},
        ]

        with (
            patch.object(document_store, "get_sources_due_for_poll", return_value=[]),
            patch.object(document_store, "get_sources_for_adapter", return_value=sources),
            patch.object(pipeline, "ingest"),
            patch.object(document_store, "update_last_fetched_at") as mock_update,
        ):
            poller.start()

            try:
                poller.trigger_immediate_ingest("test-adapter")
                time.sleep(0.2)

                # Should have called update_last_fetched_at for the source
                mock_update.assert_called_once_with("source-1")
            finally:
                poller.stop()

    def test_trigger_handles_ingest_failure_gracefully(self, pipeline, document_store):
        """trigger_immediate_ingest() should continue on ingest failure (per-source isolation)."""
        adapter = MockAdapter("test-adapter", Domain.NOTES)
        chunker = MockDomain()

        poller = Poller(pipeline, document_store, tick_interval=0.5)
        poller.register(adapter, chunker)

        sources = [
            {"source_id": "source-1", "adapter_id": "test-adapter", "origin_ref": "/path/1"},
            {"source_id": "source-2", "adapter_id": "test-adapter", "origin_ref": "/path/2"},
        ]

        with (
            patch.object(document_store, "get_sources_due_for_poll", return_value=[]),
            patch.object(document_store, "get_sources_for_adapter", return_value=sources),
            # Make first ingest fail, second succeed
            patch.object(pipeline, "ingest", side_effect=[Exception("Test error"), None]),
            patch.object(document_store, "update_last_fetched_at") as mock_update,
        ):
            poller.start()

            try:
                poller.trigger_immediate_ingest("test-adapter")
                time.sleep(0.2)

                # Both sources should have been attempted
                assert pipeline.ingest.call_count == 2
                # Only second source should have been updated
                mock_update.assert_called_once_with("source-2")
            finally:
                poller.stop()

    def test_trigger_non_blocking(self, pipeline, document_store):
        """trigger_immediate_ingest() should return immediately (non-blocking)."""
        adapter = MockAdapter("test-adapter", Domain.NOTES)
        chunker = MockDomain()

        poller = Poller(pipeline, document_store, tick_interval=0.5)
        poller.register(adapter, chunker)

        # Create a source that would take time to process
        sources = [
            {"source_id": "source-1", "adapter_id": "test-adapter", "origin_ref": "/path"},
        ]

        def slow_ingest(*args, **kwargs):
            time.sleep(0.5)  # Simulate slow ingest

        with (
            patch.object(document_store, "get_sources_due_for_poll", return_value=[]),
            patch.object(document_store, "get_sources_for_adapter", return_value=sources),
            patch.object(pipeline, "ingest", side_effect=slow_ingest),
            patch.object(document_store, "update_last_fetched_at"),
        ):
            poller.start()

            try:
                # trigger_immediate_ingest should return quickly
                start_time = time.time()
                result = poller.trigger_immediate_ingest("test-adapter")
                elapsed = time.time() - start_time

                assert result is True
                # Should return almost immediately (much less than the 0.5s ingest time)
                assert elapsed < 0.2
            finally:
                poller.stop()

    def test_trigger_returns_false_when_ingest_already_in_progress(self, pipeline, document_store):
        """trigger_immediate_ingest() should raise IngestAlreadyInProgressError if ingest already in progress."""
        from context_library.scheduler.exceptions import IngestAlreadyInProgressError

        adapter = MockAdapter("test-adapter", Domain.NOTES)
        chunker = MockDomain()

        poller = Poller(pipeline, document_store, tick_interval=0.5)
        poller.register(adapter, chunker)

        # Create sources with slow ingest to allow us to call trigger before completion
        sources = [
            {"source_id": "source-1", "adapter_id": "test-adapter", "origin_ref": "/path"},
        ]

        def slow_ingest(*args, **kwargs):
            time.sleep(0.5)  # Slow enough to trigger second call before completion

        with (
            patch.object(document_store, "get_sources_due_for_poll", return_value=[]),
            patch.object(document_store, "get_sources_for_adapter", return_value=sources),
            patch.object(pipeline, "ingest", side_effect=slow_ingest),
            patch.object(document_store, "update_last_fetched_at"),
        ):
            poller.start()

            try:
                # First call should succeed
                result1 = poller.trigger_immediate_ingest("test-adapter")
                assert result1 is True

                # Second call while first is still in progress should raise IngestAlreadyInProgressError
                with pytest.raises(IngestAlreadyInProgressError):
                    poller.trigger_immediate_ingest("test-adapter")
            finally:
                poller.stop()

    def test_trigger_race_condition_protection_with_lock(self, pipeline, document_store):
        """trigger_immediate_ingest() check-and-set should be atomic (protected by lock)."""
        from context_library.scheduler.exceptions import IngestAlreadyInProgressError

        adapter = MockAdapter("test-adapter", Domain.NOTES)
        chunker = MockDomain()

        poller = Poller(pipeline, document_store, tick_interval=0.5)
        poller.register(adapter, chunker)

        sources = [
            {"source_id": "source-1", "adapter_id": "test-adapter", "origin_ref": "/path"},
        ]

        call_count = {"count": 0}
        condition = threading.Condition()

        def slow_ingest(*args, **kwargs):
            # Signal that we're about to process
            with condition:
                call_count["count"] += 1
                condition.notify()
            time.sleep(0.5)

        with (
            patch.object(document_store, "get_sources_due_for_poll", return_value=[]),
            patch.object(document_store, "get_sources_for_adapter", return_value=sources),
            patch.object(pipeline, "ingest", side_effect=slow_ingest),
            patch.object(document_store, "update_last_fetched_at"),
        ):
            poller.start()

            try:
                # First call should succeed
                result1 = poller.trigger_immediate_ingest("test-adapter")
                assert result1 is True

                # Wait briefly for first ingest to start
                with condition:
                    condition.wait_for(lambda: call_count["count"] > 0, timeout=1.0)

                # Second call should raise IngestAlreadyInProgressError (not spawn another thread)
                with pytest.raises(IngestAlreadyInProgressError):
                    poller.trigger_immediate_ingest("test-adapter")

                # Wait for background threads to finish
                time.sleep(0.6)

                # Only one ingest should have been called (not two)
                assert call_count["count"] == 1
            finally:
                poller.stop()

    def test_stop_joins_background_threads(self, pipeline, document_store):
        """stop() should wait for background ingest threads to complete."""
        adapter = MockAdapter("test-adapter", Domain.NOTES)
        chunker = MockDomain()

        poller = Poller(pipeline, document_store, tick_interval=0.5)
        poller.register(adapter, chunker)

        sources = [
            {"source_id": "source-1", "adapter_id": "test-adapter", "origin_ref": "/path"},
        ]

        ingest_started = threading.Event()
        ingest_finished = threading.Event()

        def slow_ingest(*args, **kwargs):
            ingest_started.set()
            time.sleep(0.3)  # Simulate work
            ingest_finished.set()

        with (
            patch.object(document_store, "get_sources_due_for_poll", return_value=[]),
            patch.object(document_store, "get_sources_for_adapter", return_value=sources),
            patch.object(pipeline, "ingest", side_effect=slow_ingest),
            patch.object(document_store, "update_last_fetched_at"),
        ):
            poller.start()
            try:
                # Trigger background ingest
                result = poller.trigger_immediate_ingest("test-adapter")
                assert result is True

                # Wait for ingest to start
                assert ingest_started.wait(timeout=2.0), "Ingest did not start"

                # Stop should wait for thread to finish
                poller.stop()

                # After stop returns, thread should have completed
                assert ingest_finished.is_set(), "Background thread was not waited for"
                assert len(poller._background_threads) == 0, "Background thread not removed from set"
            finally:
                if poller._thread and poller._thread.is_alive():
                    poller.stop()

    def test_tick_skips_sources_when_background_ingest_in_progress(self, pipeline, document_store):
        """_tick() should skip sources when a background ingest is in progress for that adapter."""
        adapter = MockAdapter("test-adapter", Domain.NOTES)
        chunker = MockDomain()

        poller = Poller(pipeline, document_store, tick_interval=0.1)
        poller.register(adapter, chunker)

        # Set up a due source
        due_source = {
            "source_id": "source-1",
            "adapter_id": "test-adapter",
            "origin_ref": "/path/to/source",
            "poll_interval_sec": 60,
            "last_fetched_at": None,
        }

        ingest_started = threading.Event()

        def slow_ingest(*args, **kwargs):
            ingest_started.set()
            time.sleep(0.5)  # Hold ingest lock for a while

        with (
            patch.object(document_store, "get_sources_due_for_poll", return_value=[due_source]),
            patch.object(document_store, "get_sources_for_adapter", return_value=[due_source]),
            patch.object(pipeline, "ingest", side_effect=slow_ingest),
            patch.object(document_store, "update_last_fetched_at"),
        ):
            poller.start()
            try:
                # Trigger background ingest
                result = poller.trigger_immediate_ingest("test-adapter")
                assert result is True

                # Wait for background ingest to start
                assert ingest_started.wait(timeout=2.0), "Background ingest did not start"

                # Now tick while ingest is in progress
                # The tick should skip this source since _ingest_in_progress is set
                initial_ingest_calls = pipeline.ingest.call_count

                poller._tick()

                # Should not have called ingest again (would be initial_ingest_calls + 1)
                # since the background ingest is in progress
                assert pipeline.ingest.call_count == initial_ingest_calls
            finally:
                if poller._thread and poller._thread.is_alive():
                    poller.stop()

    def test_stop_clears_stale_ingest_in_progress_flags(self, pipeline, document_store):
        """stop() should clear stale _ingest_in_progress flags after shutdown."""
        adapter = MockAdapter("test-adapter", Domain.NOTES)
        chunker = MockDomain()

        poller = Poller(pipeline, document_store, tick_interval=0.5)
        poller.register(adapter, chunker)

        sources = [
            {"source_id": "source-1", "adapter_id": "test-adapter", "origin_ref": "/path"},
        ]

        ingest_started = threading.Event()

        def slow_ingest(*args, **kwargs):
            ingest_started.set()
            time.sleep(0.3)

        with (
            patch.object(document_store, "get_sources_due_for_poll", return_value=[]),
            patch.object(document_store, "get_sources_for_adapter", return_value=sources),
            patch.object(pipeline, "ingest", side_effect=slow_ingest),
            patch.object(document_store, "update_last_fetched_at"),
        ):
            poller.start()
            try:
                # Trigger background ingest
                result = poller.trigger_immediate_ingest("test-adapter")
                assert result is True

                # Wait for ingest to start so flag is set
                assert ingest_started.wait(timeout=2.0), "Ingest did not start"

                # Verify flag is set while ingest is running
                assert poller._ingest_in_progress.get("test-adapter", False) is True

                # Stop should clear the flag
                poller.stop()

                # Flag should be cleared after stop
                assert poller._ingest_in_progress.get("test-adapter", False) is False
            finally:
                if poller._thread and poller._thread.is_alive():
                    poller.stop()

    def test_get_ingest_result_returns_none_before_ingest(self, pipeline, document_store):
        """get_ingest_result() should return None if no ingest has been triggered."""
        adapter = MockAdapter("test-adapter", Domain.NOTES)
        chunker = MockDomain()
        poller = Poller(pipeline, document_store, tick_interval=0.1)
        poller.register(adapter, chunker)

        result = poller.get_ingest_result("test-adapter")
        assert result is None

    def test_get_ingest_result_tracks_success(self, pipeline, document_store):
        """get_ingest_result() should track successful ingest for all sources."""
        adapter = MockAdapter("test-adapter", Domain.NOTES)
        chunker = MockDomain()

        sources = [
            {"source_id": "source-1", "adapter_id": "test-adapter", "origin_ref": "/path1"},
            {"source_id": "source-2", "adapter_id": "test-adapter", "origin_ref": "/path2"},
        ]

        with (
            patch.object(document_store, "get_sources_for_adapter", return_value=sources),
            patch.object(pipeline, "ingest"),
            patch.object(document_store, "update_last_fetched_at"),
        ):
            poller = Poller(pipeline, document_store, tick_interval=0.1)
            poller.register(adapter, chunker)
            poller.start()

            try:
                result = poller.trigger_immediate_ingest("test-adapter")
                assert result is True

                # Wait for background thread to complete
                time.sleep(0.5)

                ingest_result = poller.get_ingest_result("test-adapter")
                assert ingest_result is not None
                assert ingest_result.adapter_id == "test-adapter"
                assert ingest_result.sources_attempted == 2
                assert ingest_result.sources_succeeded == 2
                assert ingest_result.sources_failed == 0
                assert ingest_result.overall_success is True
                assert ingest_result.completed_at is not None
            finally:
                if poller._thread and poller._thread.is_alive():
                    poller.stop()

    def test_get_ingest_result_tracks_failures(self, pipeline, document_store):
        """get_ingest_result() should track per-source failures."""
        adapter = MockAdapter("test-adapter", Domain.NOTES)
        chunker = MockDomain()

        sources = [
            {"source_id": "source-1", "adapter_id": "test-adapter", "origin_ref": "/path1"},
            {"source_id": "source-2", "adapter_id": "test-adapter", "origin_ref": "/path2"},
        ]

        def ingest_side_effect(*args, **kwargs):
            # Fail on the second source
            if kwargs.get("source_ref") == "/path2":
                raise RuntimeError("Test error")

        with (
            patch.object(document_store, "get_sources_for_adapter", return_value=sources),
            patch.object(pipeline, "ingest", side_effect=ingest_side_effect),
            patch.object(document_store, "update_last_fetched_at"),
        ):
            poller = Poller(pipeline, document_store, tick_interval=0.1)
            poller.register(adapter, chunker)
            poller.start()

            try:
                result = poller.trigger_immediate_ingest("test-adapter")
                assert result is True

                # Wait for background thread to complete
                time.sleep(0.5)

                ingest_result = poller.get_ingest_result("test-adapter")
                assert ingest_result is not None
                assert ingest_result.sources_attempted == 2
                assert ingest_result.sources_succeeded == 1
                assert ingest_result.sources_failed == 1
                assert ingest_result.overall_success is False
                assert ingest_result.partial_success is True
            finally:
                if poller._thread and poller._thread.is_alive():
                    poller.stop()

    def test_tick_detects_programming_errors(self, pipeline, document_store):
        """_tick() should log programming errors at ERROR level immediately."""
        adapter = MockAdapter("test-adapter", Domain.NOTES)
        chunker = MockDomain()

        source = {
            "source_id": "source-1",
            "adapter_id": "test-adapter",
            "origin_ref": "/path",
            "poll_interval_sec": 60,
            "last_fetched_at": None,
        }

        # Simulate a programming error (TypeError)
        def ingest_with_type_error(*args, **kwargs):
            raise TypeError("Wrong argument type")

        with (
            patch.object(document_store, "get_sources_due_for_poll", return_value=[source]),
            patch.object(pipeline, "ingest", side_effect=ingest_with_type_error),
        ):
            poller = Poller(pipeline, document_store, tick_interval=0.1)
            poller.register(adapter, chunker)

            with patch("context_library.scheduler.poller.logger") as mock_logger:
                poller._tick()

                # Should log at ERROR level immediately (not INFO)
                # and not record multiple failures for escalation
                error_calls = [
                    call for call in mock_logger.error.call_args_list
                    if "programming error" in str(call).lower()
                ]
                assert len(error_calls) > 0, "Programming error was not logged at ERROR level"
