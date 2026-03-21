"""End-to-end integration tests for health domain ingestion pipeline.

Tests the full pipeline from adapter fetch → normalization → chunking → embedding → storage.
Verifies that health data flows through the entire ingestion system correctly.
"""

import tempfile

import pytest

# Guard against missing sentence_transformers at collection time.
# This must come before any imports that transitively depend on it (e.g., IngestionPipeline).
pytest.importorskip("sentence_transformers")

from context_library.adapters.apple_health import AppleHealthAdapter
from context_library.adapters.oura import OuraAdapter
from context_library.core.differ import Differ
from context_library.core.pipeline import IngestionPipeline
from context_library.domains.health import HealthDomain
from context_library.storage.chromadb_store import ChromaDBVectorStore
from context_library.storage.document_store import DocumentStore


@pytest.fixture
def document_store():
    """Create an in-memory document store for testing."""
    # Use a temporary file instead of :memory: to support multi-threaded access.
    # SQLite :memory: databases are per-connection, so each thread gets its own
    # isolated empty database. File-based databases work correctly across threads.
    import tempfile
    import os

    temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=".db")
    temp_path = temp_file.name
    temp_file.close()

    store = DocumentStore(temp_path)
    yield store
    store.close()

    # Cleanup: delete temporary file
    try:
        os.unlink(temp_path)
    except OSError:
        pass  # File might already be deleted


@pytest.fixture
def embedder():
    """Create an embedder instance."""
    from context_library.core.embedder import Embedder
    return Embedder(model_name="all-MiniLM-L6-v2")


@pytest.fixture
def differ():
    """Create a differ instance."""
    return Differ()


@pytest.fixture
def health_domain():
    """Create a HealthDomain chunker instance."""
    return HealthDomain(hard_limit=1024)


@pytest.fixture
def pipeline(document_store, embedder, differ):
    """Create a pipeline instance with temporary vector store."""
    with tempfile.TemporaryDirectory() as tmpdir:
        vector_store = ChromaDBVectorStore(tmpdir)
        pipeline_obj = IngestionPipeline(
            document_store=document_store,
            embedder=embedder,
            differ=differ,
            vector_store=vector_store,
        )
        yield pipeline_obj


class TestHealthDomainIntegration:
    """End-to-end integration tests for health domain pipeline."""

    def test_apple_health_full_pipeline_single_record(
        self, pipeline, health_domain, mock_all_health_endpoints_integration
    ):
        """Test full pipeline: Apple Health adapter → chunking → embedding → storage."""
        # Setup adapter with test data
        adapter = AppleHealthAdapter(api_url="http://127.0.0.1:7124", api_key="test-token")

        # Configure a single workout record
        mock_all_health_endpoints_integration.set_response("http://127.0.0.1:7124/workouts", [
            {
                "id": "workout-001",
                "activityType": "running",
                "startDate": "2026-03-07T08:00:00+00:00",
                "endDate": "2026-03-07T08:30:00+00:00",
                "durationSeconds": 1800,
                "totalEnergyBurned": 450.0,
                "totalDistance": 3000.0,
                "averageHeartRate": 150.0,
                "notes": "Morning run",
            }
        ])

        # Run ingestion pipeline
        result = pipeline.ingest(adapter, health_domain)

        # Verify ingestion succeeded
        assert result["sources_processed"] == 1
        assert result["chunks_added"] > 0
        assert result["chunks_removed"] == 0

        # Verify data in document store (source_id format is {activity_type}/workout-{id})
        versions = pipeline.document_store.get_version_history("running/workout-001")
        assert len(versions) >= 1
        version = versions[0]
        assert len(version.chunk_hashes) > 0

        # Verify chunks contain health metadata
        chunks, _ = pipeline.document_store.get_chunks_by_source("running/workout-001")
        assert len(chunks) > 0
        chunk = chunks[0]
        assert chunk.domain_metadata is not None
        assert chunk.domain_metadata["health_type"] == "workout_session"
        assert chunk.domain_metadata["source_type"] == "apple_health"
        assert chunk.domain_metadata["date"] == "2026-03-07"

        # Verify chunks have proper context headers
        assert "workout_session" in chunk.context_header
        assert "2026-03-07" in chunk.context_header


    def test_apple_health_multiple_endpoint_types(
        self, pipeline, health_domain, mock_all_health_endpoints_integration
    ):
        """Test pipeline handles multiple workout types from Apple Health."""
        # Note: Apple Health adapter only exposes workouts; sleep and other metrics
        # are served by the Oura collector (separate adapter).
        adapter = AppleHealthAdapter(api_url="http://127.0.0.1:7124", api_key="test-token")

        # Configure multiple workout records
        mock_all_health_endpoints_integration.set_response("http://127.0.0.1:7124/workouts", [
            {
                "id": "workout-001",
                "activityType": "running",
                "startDate": "2026-03-07T08:00:00+00:00",
                "endDate": "2026-03-07T08:30:00+00:00",
                "durationSeconds": 1800,
            },
            {
                "id": "workout-002",
                "activityType": "cycling",
                "startDate": "2026-03-07T17:00:00+00:00",
                "endDate": "2026-03-07T17:45:00+00:00",
                "durationSeconds": 2700,
            }
        ])

        # Run pipeline
        result = pipeline.ingest(adapter, health_domain)

        # Should process both workouts
        assert result["sources_processed"] >= 2  # two workouts
        assert result["chunks_added"] >= 2

        # Verify both workouts in document store
        running_chunks, _ = pipeline.document_store.get_chunks_by_source("running/workout-001")
        cycling_chunks, _ = pipeline.document_store.get_chunks_by_source("cycling/workout-002")

        assert len(running_chunks) > 0
        assert len(cycling_chunks) > 0

        # Verify health types are correct
        assert running_chunks[0].domain_metadata["health_type"] == "workout_session"
        assert cycling_chunks[0].domain_metadata["health_type"] == "workout_session"

    def test_cross_adapter_health_types(
        self, pipeline, health_domain, mock_all_health_endpoints_integration
    ):
        """Test pipeline can process and store multiple health types from different adapters (cross-type coverage).

        Verifies that the system maintains separate data for both workout (Apple Health) and sleep
        (Oura) health metric types. This test covers Apple Health workouts; Oura sleep is tested
        separately to avoid fixture composition issues across independent adapter mocks.
        """
        # Configure Apple Health workout data
        mock_all_health_endpoints_integration.set_response("http://127.0.0.1:7124/workouts", [
            {
                "id": "workout-001",
                "activityType": "running",
                "startDate": "2026-03-07T08:00:00+00:00",
                "endDate": "2026-03-07T08:30:00+00:00",
                "durationSeconds": 1800,
            },
            {
                "id": "workout-002",
                "activityType": "cycling",
                "startDate": "2026-03-08T09:00:00+00:00",
                "endDate": "2026-03-08T10:00:00+00:00",
                "durationSeconds": 3600,
            }
        ])

        # Ingest workout data from Apple Health
        apple_adapter = AppleHealthAdapter(api_url="http://127.0.0.1:7124", api_key="test-token")
        result = pipeline.ingest(apple_adapter, health_domain)
        assert result["sources_processed"] >= 2
        assert result["chunks_added"] > 0

        # Verify both workout types are stored correctly
        running_chunks, _ = pipeline.document_store.get_chunks_by_source("running/workout-001")
        cycling_chunks, _ = pipeline.document_store.get_chunks_by_source("cycling/workout-002")

        assert len(running_chunks) > 0
        assert len(cycling_chunks) > 0

        # Verify correct health type for workouts
        assert running_chunks[0].domain_metadata["health_type"] == "workout_session"
        assert cycling_chunks[0].domain_metadata["health_type"] == "workout_session"

    def test_oura_full_pipeline_single_record(
        self, pipeline, health_domain, mock_all_oura_endpoints_integration
    ):
        """Test full pipeline with Oura adapter: fetch → chunk → embed → store."""
        adapter = OuraAdapter(api_url="http://localhost:8000", api_key="test-token")

        # Configure a single sleep record
        mock_all_oura_endpoints_integration.set_response("http://localhost:8000/oura/sleep", [
            {
                "id": "sleep-oura-001",
                "date": "2026-03-07",
                "score": 88,
                "totalSleepMinutes": 470,
                "deepSleepMinutes": 110,
                "remSleepMinutes": 150,
                "lightSleepMinutes": 210,
                "awakeMinutes": 10,
            }
        ])

        # Run ingestion pipeline
        result = pipeline.ingest(adapter, health_domain)

        # Verify ingestion succeeded
        assert result["sources_processed"] >= 1
        assert result["chunks_added"] > 0

        # Verify data in document store (source_id format is {adapter_source}/{health_type}/{id})
        versions = pipeline.document_store.get_version_history("oura/sleep/sleep-oura-001")
        assert len(versions) >= 1

        # Verify chunks contain correct metadata
        chunks, _ = pipeline.document_store.get_chunks_by_source("oura/sleep/sleep-oura-001")
        assert len(chunks) > 0
        chunk = chunks[0]
        assert chunk.domain_metadata["health_type"] == "sleep_summary"
        assert chunk.domain_metadata["source_type"] == "oura"
        assert chunk.domain_metadata["date"] == "2026-03-07"
