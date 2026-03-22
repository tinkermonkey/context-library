"""Tests for the scheduler poller."""
import os

import tempfile
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
