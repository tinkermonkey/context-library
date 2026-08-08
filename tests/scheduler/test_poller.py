"""Tests for the scheduler poller (per-adapter scheduling).

The Poller schedules registered (adapter, chunker) pairs directly: an adapter is
due when its poll_interval_sec (or the poller tick interval) has elapsed since
its last *successful* run. It never queries the document store for per-source
poll rows, always passes source_ref="" to the pipeline (adapters drain from
their own persisted cursor), and calls adapter.ack() after a successful commit.
"""
import os
import tempfile
import threading
import time
from unittest.mock import Mock, patch

import pytest

from context_library.adapters.base import BaseAdapter
from context_library.core.differ import Differ
from context_library.core.embedder import Embedder
from context_library.core.pipeline import IngestionPipeline
from context_library.domains.base import BaseDomain
from context_library.scheduler.poller import Poller
from context_library.storage.document_store import DocumentStore
from context_library.storage.models import Domain, NormalizedContent


#: Minimal pipeline.ingest() result dict as returned on success.
def _pipeline_result(processed: int = 1, failed: int = 0) -> dict:
    return {
        "sources_processed": processed,
        "sources_failed": failed,
        "chunks_added": 0,
        "chunks_removed": 0,
        "chunks_unchanged": 0,
        "errors": [],
    }


def _wait_for(predicate, timeout: float = 3.0, interval: float = 0.01) -> bool:
    """Poll predicate until true or timeout; returns final predicate value."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        if predicate():
            return True
        time.sleep(interval)
    return bool(predicate())


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

        for _ in range(3):
            poller.start()
            time.sleep(0.05)
            poller.stop()
            assert poller._thread is None


class TestPollerTicking:
    """Tests for the per-adapter polling tick logic."""

    def test_tick_does_not_query_document_store_for_due_sources(
        self, pipeline, document_store
    ):
        """_tick() schedules per-adapter; it never calls get_sources_due_for_poll()."""
        adapter = MockAdapter("test-adapter", Domain.NOTES)
        chunker = MockDomain()

        poller = Poller(pipeline, document_store)
        poller.register(adapter, chunker)

        with (
            patch.object(document_store, "get_sources_due_for_poll") as mock_get_due,
            patch.object(pipeline, "ingest", return_value=_pipeline_result()),
        ):
            poller._tick()

            mock_get_due.assert_not_called()

    def test_tick_ingests_registered_adapter_with_empty_source_ref(
        self, pipeline, document_store
    ):
        """_tick() runs one ingest per due adapter with source_ref="" (adapter cursor)."""
        adapter = MockAdapter("test-adapter", Domain.NOTES)
        chunker = MockDomain()

        poller = Poller(pipeline, document_store)
        poller.register(adapter, chunker)

        with patch.object(pipeline, "ingest", return_value=_pipeline_result()) as mock_ingest:
            poller._tick()

            mock_ingest.assert_called_once_with(adapter, chunker, source_ref="")

    def test_tick_ingests_all_registered_adapters(self, pipeline, document_store):
        """_tick() should run one ingest for every registered (due) adapter."""
        adapter1 = MockAdapter("adapter-1", Domain.NOTES)
        adapter2 = MockAdapter("adapter-2", Domain.MESSAGES)
        chunker1 = MockDomain()
        chunker2 = MockDomain()

        poller = Poller(pipeline, document_store)
        poller.register(adapter1, chunker1)
        poller.register(adapter2, chunker2)

        with patch.object(pipeline, "ingest", return_value=_pipeline_result()) as mock_ingest:
            poller._tick()

            assert mock_ingest.call_count == 2
            called_adapters = [c.args[0] for c in mock_ingest.call_args_list]
            assert called_adapters == [adapter1, adapter2]

    def test_tick_skips_adapter_within_interval(self, pipeline, document_store):
        """After a successful run, the adapter is not due again until the interval elapses."""
        adapter = MockAdapter("test-adapter", Domain.NOTES)
        chunker = MockDomain()

        poller = Poller(pipeline, document_store, tick_interval=60.0)
        poller.register(adapter, chunker)

        with patch.object(pipeline, "ingest", return_value=_pipeline_result()) as mock_ingest:
            poller._tick()
            poller._tick()  # immediately again — interval (60s) has not elapsed

            mock_ingest.assert_called_once()

    def test_tick_polls_again_after_interval_elapsed(self, pipeline, document_store):
        """An adapter becomes due again once tick_interval has elapsed since last success."""
        adapter = MockAdapter("test-adapter", Domain.NOTES)
        chunker = MockDomain()

        poller = Poller(pipeline, document_store, tick_interval=60.0)
        poller.register(adapter, chunker)

        with patch.object(pipeline, "ingest", return_value=_pipeline_result()) as mock_ingest:
            poller._tick()
            assert mock_ingest.call_count == 1

            # Simulate the interval having elapsed
            poller._last_polled["test-adapter"] = time.monotonic() - 61.0
            poller._tick()

            assert mock_ingest.call_count == 2

    def test_tick_respects_adapter_poll_interval_sec_override(
        self, pipeline, document_store
    ):
        """adapter.poll_interval_sec overrides the poller tick_interval for dueness."""
        fast_adapter = MockAdapter("fast-adapter", Domain.NOTES)
        fast_adapter.poll_interval_sec = 5.0  # due after 5s despite 60s tick_interval
        slow_adapter = MockAdapter("slow-adapter", Domain.NOTES)  # defaults to tick_interval
        chunker = MockDomain()

        poller = Poller(pipeline, document_store, tick_interval=60.0)
        poller.register(fast_adapter, chunker)
        poller.register(slow_adapter, chunker)

        with patch.object(pipeline, "ingest", return_value=_pipeline_result()) as mock_ingest:
            poller._tick()
            assert mock_ingest.call_count == 2  # both due on first tick

            # 10 seconds "ago": past the fast adapter's 5s override,
            # but well within the slow adapter's 60s default.
            mark = time.monotonic() - 10.0
            poller._last_polled["fast-adapter"] = mark
            poller._last_polled["slow-adapter"] = mark
            poller._tick()

            assert mock_ingest.call_count == 3
            assert mock_ingest.call_args_list[-1].args[0] is fast_adapter

    def test_tick_none_poll_interval_falls_back_to_tick_interval(
        self, pipeline, document_store
    ):
        """poll_interval_sec=None falls back to the poller tick_interval."""
        adapter = MockAdapter("test-adapter", Domain.NOTES)
        adapter.poll_interval_sec = None
        chunker = MockDomain()

        poller = Poller(pipeline, document_store, tick_interval=60.0)
        poller.register(adapter, chunker)

        with patch.object(pipeline, "ingest", return_value=_pipeline_result()) as mock_ingest:
            poller._tick()
            poller._last_polled["test-adapter"] = time.monotonic() - 10.0
            poller._tick()  # 10s elapsed < 60s tick_interval — not due

            mock_ingest.assert_called_once()

    def test_tick_updates_last_polled_on_success(self, pipeline, document_store):
        """_tick() records the adapter's last successful poll time."""
        adapter = MockAdapter("test-adapter", Domain.NOTES)
        chunker = MockDomain()

        poller = Poller(pipeline, document_store)
        poller.register(adapter, chunker)

        with patch.object(pipeline, "ingest", return_value=_pipeline_result()):
            before = time.monotonic()
            poller._tick()

        assert "test-adapter" in poller._last_polled
        assert poller._last_polled["test-adapter"] >= before

    def test_tick_does_not_update_last_polled_on_failure_and_retries(
        self, pipeline, document_store
    ):
        """A failed run leaves _last_polled unset so the adapter retries next tick."""
        adapter = MockAdapter("test-adapter", Domain.NOTES)
        chunker = MockDomain()

        poller = Poller(pipeline, document_store, tick_interval=60.0)
        poller.register(adapter, chunker)

        with patch.object(
            pipeline,
            "ingest",
            side_effect=[Exception("Test error"), _pipeline_result()],
        ) as mock_ingest:
            poller._tick()
            assert "test-adapter" not in poller._last_polled

            # Failed adapter is immediately due again on the next tick
            poller._tick()

            assert mock_ingest.call_count == 2
            assert "test-adapter" in poller._last_polled

    def test_tick_does_not_call_update_last_fetched_at(self, pipeline, document_store):
        """The poller no longer touches per-source last_fetched_at (pipeline owns it)."""
        adapter = MockAdapter("test-adapter", Domain.NOTES)
        chunker = MockDomain()

        poller = Poller(pipeline, document_store)
        poller.register(adapter, chunker)

        with (
            patch.object(pipeline, "ingest", return_value=_pipeline_result()),
            patch.object(document_store, "update_last_fetched_at") as mock_update,
        ):
            poller._tick()

            mock_update.assert_not_called()

    def test_tick_isolates_per_adapter_failures(self, pipeline, document_store):
        """_tick() should continue polling other adapters after one adapter fails."""
        adapter1 = MockAdapter("adapter-1", Domain.NOTES)
        adapter2 = MockAdapter("adapter-2", Domain.MESSAGES)
        chunker = MockDomain()

        poller = Poller(pipeline, document_store)
        poller.register(adapter1, chunker)
        poller.register(adapter2, chunker)

        # First adapter's ingest raises, second succeeds
        pipeline.ingest = Mock(side_effect=[Exception("Test error"), _pipeline_result()])

        # Should not raise
        poller._tick()

        assert pipeline.ingest.call_count == 2
        # Only the successful adapter got a last-polled mark
        assert "adapter-1" not in poller._last_polled
        assert "adapter-2" in poller._last_polled

    def test_tick_skips_adapter_when_ingest_in_progress(self, pipeline, document_store):
        """_tick() skips (with a debug log) an adapter whose ingest slot is busy."""
        adapter = MockAdapter("test-adapter", Domain.NOTES)
        chunker = MockDomain()

        poller = Poller(pipeline, document_store)
        poller.register(adapter, chunker)

        # Claim the slot as another path (push route / manual trigger) would
        assert poller.try_begin_ingest("test-adapter") is True
        try:
            with (
                patch.object(pipeline, "ingest") as mock_ingest,
                patch("context_library.scheduler.poller.logger") as mock_logger,
            ):
                poller._tick()

                mock_ingest.assert_not_called()
                mock_logger.debug.assert_called_once()
                assert "already in progress" in str(mock_logger.debug.call_args)
        finally:
            poller.end_ingest("test-adapter")

    def test_tick_logs_failure_at_info_level_on_first_failure(
        self, pipeline, document_store
    ):
        """_tick() should log at INFO level on first/second failure (transient)."""
        adapter = MockAdapter("test-adapter", Domain.NOTES)
        chunker = MockDomain()

        poller = Poller(pipeline, document_store)
        poller.register(adapter, chunker)

        with patch.object(pipeline, "ingest", side_effect=Exception("Test error")):
            with patch("context_library.scheduler.poller.logger") as mock_logger:
                poller._tick()

                # First failure should log at INFO level (transient)
                mock_logger.info.assert_called_once()
                call_args = str(mock_logger.info.call_args)
                assert "test-adapter" in call_args
                assert "transient" in call_args

    def test_tick_logs_failure_at_warning_level_after_3_failures(
        self, pipeline, document_store
    ):
        """_tick() should log at WARNING level after 3 consecutive adapter failures."""
        adapter = MockAdapter("test-adapter", Domain.NOTES)
        chunker = MockDomain()

        poller = Poller(pipeline, document_store)
        poller.register(adapter, chunker)

        # A failing adapter never gets a _last_polled mark, so it stays due every tick.
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
                assert "test-adapter" in call_args
                assert "WARNING level" in call_args

    def test_tick_logs_failure_at_error_level_after_6_failures(
        self, pipeline, document_store
    ):
        """_tick() should log at ERROR level after 6 consecutive adapter failures."""
        adapter = MockAdapter("test-adapter", Domain.NOTES)
        chunker = MockDomain()

        poller = Poller(pipeline, document_store)
        poller.register(adapter, chunker)

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
                        assert "test-adapter" in call_args
                        assert "ERROR level" in call_args

    def test_tick_clears_error_tracker_on_success(self, pipeline, document_store):
        """A success resets the consecutive-failure count for the adapter."""
        adapter = MockAdapter("test-adapter", Domain.NOTES)
        chunker = MockDomain()

        poller = Poller(pipeline, document_store)
        poller.register(adapter, chunker)

        with patch.object(
            pipeline,
            "ingest",
            side_effect=[Exception("boom"), Exception("boom"), _pipeline_result()],
        ):
            poller._tick()
            poller._tick()
            assert poller._error_tracker["test-adapter"].consecutive_failures == 2

            poller._tick()
            assert poller._error_tracker["test-adapter"].consecutive_failures == 0

    def test_tick_detects_programming_errors(self, pipeline, document_store):
        """_tick() should log programming errors at ERROR level immediately."""
        adapter = MockAdapter("test-adapter", Domain.NOTES)
        chunker = MockDomain()

        # Simulate a programming error (TypeError)
        def ingest_with_type_error(*args, **kwargs):
            raise TypeError("Wrong argument type")

        with patch.object(pipeline, "ingest", side_effect=ingest_with_type_error):
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

        poller.start()

        # Let it run for ~0.3 seconds (should have at least 2 ticks)
        time.sleep(0.3)

        poller.stop()

        # Should have ticked at least twice
        assert tick_count["count"] >= 2

    def test_stop_event_halts_thread(self, pipeline, document_store):
        """Setting _stop_event should halt the thread within tick_interval."""
        poller = Poller(pipeline, document_store, tick_interval=1.0)

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
        pipeline.ingest.return_value = _pipeline_result()
        adapter = MockAdapter("test-adapter", Domain.NOTES)
        chunker = MockDomain()

        poller = Poller(pipeline, document_store, tick_interval=0.1)
        poller.register(adapter, chunker)

        poller.start()
        assert _wait_for(lambda: pipeline.ingest.called), "Pipeline was never invoked"
        poller.stop()

        # Pipeline.ingest should have been called for the registered adapter,
        # draining from the adapter's own cursor (source_ref="")
        assert pipeline.ingest.called
        first_call = pipeline.ingest.call_args_list[0]
        assert first_call.args[0] is adapter
        assert first_call.args[1] is chunker
        assert first_call.kwargs == {"source_ref": ""}


class TestIngestSlot:
    """Tests for the public try_begin_ingest()/end_ingest() slot API."""

    def test_try_begin_ingest_claims_slot(self, pipeline, document_store):
        """First claim succeeds, second is rejected until the slot is released."""
        poller = Poller(pipeline, document_store)

        assert poller.try_begin_ingest("adapter-x") is True
        assert poller.try_begin_ingest("adapter-x") is False

        poller.end_ingest("adapter-x")
        assert poller.try_begin_ingest("adapter-x") is True
        poller.end_ingest("adapter-x")

    def test_slots_are_per_adapter(self, pipeline, document_store):
        """A busy slot for one adapter does not block another adapter."""
        poller = Poller(pipeline, document_store)

        assert poller.try_begin_ingest("adapter-a") is True
        assert poller.try_begin_ingest("adapter-b") is True
        poller.end_ingest("adapter-a")
        poller.end_ingest("adapter-b")

    def test_try_begin_ingest_is_atomic_under_contention(self, pipeline, document_store):
        """Exactly one of many racing claimants wins the slot."""
        poller = Poller(pipeline, document_store)

        wins = []
        barrier = threading.Barrier(8)

        def claim():
            barrier.wait()
            if poller.try_begin_ingest("adapter-x"):
                wins.append(threading.current_thread().name)

        threads = [threading.Thread(target=claim) for _ in range(8)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(wins) == 1
        poller.end_ingest("adapter-x")


class TestTriggerImmediateIngest:
    """Tests for trigger_immediate_ingest() method."""

    def _started_poller(
        self, pipeline, document_store, adapter, chunker, tick_interval=60.0
    ) -> Poller:
        """Build, register, and start a poller whose first tick won't ingest.

        Pre-marks the adapter as freshly polled so the immediate first tick
        skips it (trigger_immediate_ingest bypasses the interval gate), keeping
        pipeline call counts deterministic in these tests.
        """
        poller = Poller(pipeline, document_store, tick_interval=tick_interval)
        poller.register(adapter, chunker)
        poller._last_polled[adapter.adapter_id] = time.monotonic()
        poller.start()
        return poller

    def test_trigger_raises_if_poller_stopped(self, pipeline, document_store):
        """trigger_immediate_ingest() should raise PollerNotRunningError if poller is stopped."""
        from context_library.scheduler.exceptions import PollerNotRunningError

        poller = Poller(pipeline, document_store)
        adapter = MockAdapter("test-adapter", Domain.NOTES)
        chunker = MockDomain()

        poller.register(adapter, chunker)

        # Poller not started, so should raise PollerNotRunningError
        with pytest.raises(PollerNotRunningError):
            poller.trigger_immediate_ingest("test-adapter")

    def test_trigger_raises_if_adapter_not_registered(self, pipeline, document_store):
        """trigger_immediate_ingest() should raise AdapterNotRegisteredError for unknown adapter."""
        from context_library.scheduler.exceptions import AdapterNotRegisteredError

        poller = Poller(pipeline, document_store, tick_interval=0.5)
        poller.start()

        try:
            with pytest.raises(AdapterNotRegisteredError):
                poller.trigger_immediate_ingest("unknown-adapter")
        finally:
            poller.stop()

    def test_trigger_works_with_zero_sources(self, pipeline, document_store):
        """An adapter with no source rows can be triggered (the bootstrap case).

        NoSourcesError is gone from this path: the adapter drains from its own
        cursor, so a freshly registered adapter with zero sources must still run.
        """
        adapter = MockAdapter("test-adapter", Domain.NOTES)
        chunker = MockDomain()

        with patch.object(
            pipeline, "ingest", return_value=_pipeline_result(processed=0)
        ) as mock_ingest:
            poller = self._started_poller(pipeline, document_store, adapter, chunker)
            try:
                result = poller.trigger_immediate_ingest("test-adapter")
                assert result is True

                assert _wait_for(
                    lambda: poller.get_ingest_result("test-adapter") is not None
                ), "Background ingest did not complete"

                mock_ingest.assert_called_once_with(adapter, chunker, source_ref="")
            finally:
                poller.stop()

    def test_trigger_runs_single_adapter_ingest_with_empty_source_ref(
        self, pipeline, document_store
    ):
        """trigger runs exactly ONE pipeline.ingest for the adapter, source_ref=""."""
        adapter = MockAdapter("test-adapter", Domain.NOTES)
        chunker = MockDomain()

        with patch.object(
            pipeline, "ingest", return_value=_pipeline_result(processed=3)
        ) as mock_ingest:
            poller = self._started_poller(pipeline, document_store, adapter, chunker)
            try:
                result = poller.trigger_immediate_ingest("test-adapter")
                assert result is True

                assert _wait_for(
                    lambda: poller.get_ingest_result("test-adapter") is not None
                )

                # One ingest per trigger — no per-source loop, no origin_refs
                mock_ingest.assert_called_once_with(adapter, chunker, source_ref="")
            finally:
                poller.stop()

    def test_trigger_acks_after_successful_ingest(self, pipeline, document_store):
        """adapter.ack() is called after the pipeline commits a triggered ingest."""
        adapter = _AckableAdapter("test-adapter", Domain.NOTES)
        chunker = MockDomain()

        with patch.object(pipeline, "ingest", return_value=_pipeline_result()):
            poller = self._started_poller(pipeline, document_store, adapter, chunker)
            try:
                poller.trigger_immediate_ingest("test-adapter")
                assert _wait_for(
                    lambda: poller.get_ingest_result("test-adapter") is not None
                )
                assert adapter.ack_calls == 1
            finally:
                poller.stop()

    def test_trigger_does_not_ack_on_failure(self, pipeline, document_store):
        """adapter.ack() is NOT called when the triggered ingest fails."""
        adapter = _AckableAdapter("test-adapter", Domain.NOTES)
        chunker = MockDomain()

        with patch.object(pipeline, "ingest", side_effect=RuntimeError("ingest blew up")):
            poller = self._started_poller(pipeline, document_store, adapter, chunker)
            try:
                poller.trigger_immediate_ingest("test-adapter")
                assert _wait_for(
                    lambda: poller.get_ingest_result("test-adapter") is not None
                )
                assert adapter.ack_calls == 0
            finally:
                poller.stop()

    def test_trigger_sets_last_polled_on_success(self, pipeline, document_store):
        """A successful triggered ingest advances the adapter's last-polled mark."""
        adapter = MockAdapter("test-adapter", Domain.NOTES)
        chunker = MockDomain()

        with patch.object(pipeline, "ingest", return_value=_pipeline_result()):
            poller = self._started_poller(pipeline, document_store, adapter, chunker)
            mark_before = poller._last_polled["test-adapter"]
            try:
                poller.trigger_immediate_ingest("test-adapter")
                assert _wait_for(
                    lambda: poller._last_polled["test-adapter"] > mark_before
                ), "last-polled mark was not advanced"
            finally:
                poller.stop()

    def test_trigger_does_not_set_last_polled_on_failure(self, pipeline, document_store):
        """A failed triggered ingest leaves the last-polled mark unchanged."""
        adapter = MockAdapter("test-adapter", Domain.NOTES)
        chunker = MockDomain()

        with patch.object(pipeline, "ingest", side_effect=RuntimeError("boom")):
            poller = self._started_poller(pipeline, document_store, adapter, chunker)
            mark_before = poller._last_polled["test-adapter"]
            try:
                poller.trigger_immediate_ingest("test-adapter")
                assert _wait_for(
                    lambda: poller.get_ingest_result("test-adapter") is not None
                )
                assert poller._last_polled["test-adapter"] == mark_before
            finally:
                poller.stop()

    def test_trigger_non_blocking(self, pipeline, document_store):
        """trigger_immediate_ingest() should return immediately (non-blocking)."""
        adapter = MockAdapter("test-adapter", Domain.NOTES)
        chunker = MockDomain()

        def slow_ingest(*args, **kwargs):
            time.sleep(0.5)  # Simulate slow ingest
            return _pipeline_result()

        with patch.object(pipeline, "ingest", side_effect=slow_ingest):
            poller = self._started_poller(pipeline, document_store, adapter, chunker)
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

    def test_trigger_raises_when_ingest_already_in_progress(self, pipeline, document_store):
        """trigger_immediate_ingest() should raise IngestAlreadyInProgressError if busy."""
        from context_library.scheduler.exceptions import IngestAlreadyInProgressError

        adapter = MockAdapter("test-adapter", Domain.NOTES)
        chunker = MockDomain()

        ingest_started = threading.Event()

        def slow_ingest(*args, **kwargs):
            ingest_started.set()
            time.sleep(0.5)  # Slow enough to trigger second call before completion
            return _pipeline_result()

        with patch.object(pipeline, "ingest", side_effect=slow_ingest):
            poller = self._started_poller(pipeline, document_store, adapter, chunker)
            try:
                # First call should succeed
                result1 = poller.trigger_immediate_ingest("test-adapter")
                assert result1 is True
                assert ingest_started.wait(timeout=2.0)

                # Second call while first is still in progress should raise
                with pytest.raises(IngestAlreadyInProgressError):
                    poller.trigger_immediate_ingest("test-adapter")
            finally:
                poller.stop()

    def test_trigger_race_condition_protection_with_lock(self, pipeline, document_store):
        """trigger_immediate_ingest() check-and-set should be atomic (try_begin_ingest)."""
        from context_library.scheduler.exceptions import IngestAlreadyInProgressError

        adapter = MockAdapter("test-adapter", Domain.NOTES)
        chunker = MockDomain()

        call_count = {"count": 0}
        condition = threading.Condition()

        def slow_ingest(*args, **kwargs):
            # Signal that we're about to process
            with condition:
                call_count["count"] += 1
                condition.notify()
            time.sleep(0.5)
            return _pipeline_result()

        with patch.object(pipeline, "ingest", side_effect=slow_ingest):
            poller = self._started_poller(pipeline, document_store, adapter, chunker)
            try:
                # First call should succeed
                result1 = poller.trigger_immediate_ingest("test-adapter")
                assert result1 is True

                # Wait briefly for first ingest to start
                with condition:
                    condition.wait_for(lambda: call_count["count"] > 0, timeout=1.0)

                # Second call should raise (not spawn another thread)
                with pytest.raises(IngestAlreadyInProgressError):
                    poller.trigger_immediate_ingest("test-adapter")

                # Wait for background thread to finish
                assert _wait_for(
                    lambda: poller.get_ingest_result("test-adapter") is not None
                )

                # Only one ingest should have been run (not two)
                assert call_count["count"] == 1
            finally:
                poller.stop()

    def test_stop_joins_background_threads(self, pipeline, document_store):
        """stop() should wait for background ingest threads to complete."""
        adapter = MockAdapter("test-adapter", Domain.NOTES)
        chunker = MockDomain()

        ingest_started = threading.Event()
        ingest_finished = threading.Event()

        def slow_ingest(*args, **kwargs):
            ingest_started.set()
            time.sleep(0.3)  # Simulate work
            ingest_finished.set()
            return _pipeline_result()

        with patch.object(pipeline, "ingest", side_effect=slow_ingest):
            poller = self._started_poller(pipeline, document_store, adapter, chunker)
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

    def test_tick_skips_adapter_when_background_ingest_in_progress(
        self, pipeline, document_store
    ):
        """_tick() must not ingest an adapter whose background ingest is running."""
        adapter = MockAdapter("test-adapter", Domain.NOTES)
        chunker = MockDomain()

        ingest_started = threading.Event()

        def slow_ingest(*args, **kwargs):
            ingest_started.set()
            time.sleep(0.5)  # Hold the ingest slot for a while
            return _pipeline_result()

        with patch.object(pipeline, "ingest", side_effect=slow_ingest) as mock_ingest:
            poller = self._started_poller(pipeline, document_store, adapter, chunker)
            try:
                # Trigger background ingest
                result = poller.trigger_immediate_ingest("test-adapter")
                assert result is True

                # Wait for background ingest to start (slot held)
                assert ingest_started.wait(timeout=2.0), "Background ingest did not start"

                # Make the adapter due, then tick while the slot is busy —
                # the tick must skip it because the ingest slot is claimed.
                poller._last_polled.pop("test-adapter", None)
                initial_ingest_calls = mock_ingest.call_count

                poller._tick()

                assert mock_ingest.call_count == initial_ingest_calls
            finally:
                if poller._thread and poller._thread.is_alive():
                    poller.stop()

    def test_stop_clears_stale_ingest_in_progress_flags(self, pipeline, document_store):
        """The per-adapter in-progress flag is set during ingest and cleared after stop()."""
        adapter = MockAdapter("test-adapter", Domain.NOTES)
        chunker = MockDomain()

        ingest_started = threading.Event()

        def slow_ingest(*args, **kwargs):
            ingest_started.set()
            time.sleep(0.3)
            return _pipeline_result()

        with patch.object(pipeline, "ingest", side_effect=slow_ingest):
            poller = self._started_poller(pipeline, document_store, adapter, chunker)
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
        """get_ingest_result() reflects the pipeline result dict on success."""
        adapter = MockAdapter("test-adapter", Domain.NOTES)
        chunker = MockDomain()

        with patch.object(
            pipeline, "ingest", return_value=_pipeline_result(processed=2, failed=0)
        ):
            poller = self._started_poller(pipeline, document_store, adapter, chunker)
            try:
                result = poller.trigger_immediate_ingest("test-adapter")
                assert result is True

                assert _wait_for(
                    lambda: poller.get_ingest_result("test-adapter") is not None
                )

                ingest_result = poller.get_ingest_result("test-adapter")
                assert ingest_result is not None
                assert ingest_result.adapter_id == "test-adapter"
                assert ingest_result.sources_attempted == 2
                assert ingest_result.sources_succeeded == 2
                assert ingest_result.sources_failed == 0
                assert ingest_result.overall_success is True
                assert ingest_result.completed_at is not None
            finally:
                poller.stop()

    def test_get_ingest_result_tracks_partial_failures(self, pipeline, document_store):
        """get_ingest_result() reflects per-source failures reported by the pipeline."""
        adapter = MockAdapter("test-adapter", Domain.NOTES)
        chunker = MockDomain()

        with patch.object(
            pipeline, "ingest", return_value=_pipeline_result(processed=1, failed=1)
        ):
            poller = self._started_poller(pipeline, document_store, adapter, chunker)
            try:
                result = poller.trigger_immediate_ingest("test-adapter")
                assert result is True

                assert _wait_for(
                    lambda: poller.get_ingest_result("test-adapter") is not None
                )

                ingest_result = poller.get_ingest_result("test-adapter")
                assert ingest_result is not None
                assert ingest_result.sources_attempted == 2
                assert ingest_result.sources_succeeded == 1
                assert ingest_result.sources_failed == 1
                assert ingest_result.overall_success is False
                assert ingest_result.partial_success is True
            finally:
                poller.stop()

    def test_get_ingest_result_tracks_whole_fetch_exception(self, pipeline, document_store):
        """An exception from pipeline.ingest is recorded as a failed result."""
        adapter = MockAdapter("test-adapter", Domain.NOTES)
        chunker = MockDomain()

        with patch.object(pipeline, "ingest", side_effect=TypeError("bad call")):
            poller = self._started_poller(pipeline, document_store, adapter, chunker)
            try:
                poller.trigger_immediate_ingest("test-adapter")
                assert _wait_for(
                    lambda: poller.get_ingest_result("test-adapter") is not None
                )

                ingest_result = poller.get_ingest_result("test-adapter")
                assert ingest_result is not None
                assert ingest_result.sources_failed >= 1
                assert ingest_result.overall_success is False
                # TypeError is a programming error and is flagged as such
                assert ingest_result.had_programming_errors is True
            finally:
                poller.stop()


class _AckableAdapter(MockAdapter):
    """Mock adapter exposing ack() to exercise the poller's commit-ack flow."""

    def __init__(self, adapter_id: str, domain: Domain):
        super().__init__(adapter_id, domain)
        self.ack_calls = 0
        self.ack_should_raise = False

    def ack(self) -> None:
        self.ack_calls += 1
        if self.ack_should_raise:
            raise RuntimeError("ack endpoint unreachable")


class TestPollerCommitAck:
    """Commit-ack: adapter.ack() is called after a successful pipeline commit."""

    def test_tick_acks_after_successful_ingest(self, pipeline, document_store):
        adapter = _AckableAdapter("filesystem_helper:default", Domain.DOCUMENTS)
        chunker = MockDomain()
        with patch.object(pipeline, "ingest", return_value={}):
            poller = Poller(pipeline, document_store, tick_interval=0.1)
            poller.register(adapter, chunker)
            poller._tick()

        assert adapter.ack_calls == 1

    def test_tick_does_not_ack_after_failed_ingest(self, pipeline, document_store):
        adapter = _AckableAdapter("filesystem_helper:default", Domain.DOCUMENTS)
        chunker = MockDomain()
        with patch.object(pipeline, "ingest", side_effect=RuntimeError("ingest blew up")):
            poller = Poller(pipeline, document_store, tick_interval=0.1)
            poller.register(adapter, chunker)
            poller._tick()

        assert adapter.ack_calls == 0
