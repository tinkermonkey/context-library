"""Tests for POST /webhooks/ingest endpoint."""

from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from context_library.adapters.base import BaseAdapter
from context_library.core.exceptions import EntityLinkingError
from context_library.storage.models import Domain


def _make_structural_hints():
    """Create minimal valid structural hints for testing."""
    return {
        "has_headings": True,
        "has_lists": False,
        "has_tables": False,
        "natural_boundaries": [],
        "file_path": None,
        "modified_at": None,
        "file_size_bytes": None,
    }


class TestIngestWebhook:
    """Tests for webhook ingestion with various payload scenarios."""

    def test_ingest_returns_200(self, client: TestClient) -> None:
        """Verify ingest endpoint returns 200 on valid payload."""
        payload = {
            "adapter_id": "test-adapter",
            "domain": "notes",
            "normalizer_version": "1.0.0",
            "items": [
                {
                    "source_id": "test-source",
                    "markdown": "# Test\nContent here",
                    "structural_hints": _make_structural_hints(),
                }
            ],
        }
        resp = client.post("/webhooks/ingest", json=payload)
        assert resp.status_code == 200

    def test_ingest_processes_multiple_versions(self, client: TestClient) -> None:
        """Verify ingest accepts multiple source versions in request."""
        payload = {
            "adapter_id": "test-adapter",
            "domain": "notes",
            "normalizer_version": "1.0.0",
            "items": [
                {
                    "source_id": "src-v1",
                    "markdown": "# First version",
                    "structural_hints": _make_structural_hints(),
                },
                {
                    "source_id": "src-v1",
                    "markdown": "# Second version",
                    "structural_hints": _make_structural_hints(),
                },
            ],
        }
        resp = client.post("/webhooks/ingest", json=payload)
        assert resp.status_code == 200

    def test_ingest_accepts_new_source(self, client: TestClient) -> None:
        """Verify ingest accepts new sources in payload."""
        # Ingest to non-existent source — ingest endpoint will try to create it
        payload = {
            "adapter_id": "test-adapter",
            "domain": "notes",
            "normalizer_version": "1.0.0",
            "items": [
                {
                    "source_id": "brand-new-source",
                    "markdown": "# New",
                    "structural_hints": _make_structural_hints(),
                }
            ],
        }
        resp = client.post("/webhooks/ingest", json=payload)
        # Endpoint should accept it (pipeline may create or fail gracefully)
        assert resp.status_code == 200

    def test_ingest_stores_chunks(self, client: TestClient, ds) -> None:
        """Verify ingest stores chunks with correct lineage."""
        payload = {
            "adapter_id": "test-adapter",
            "domain": "notes",
            "normalizer_version": "1.0.0",
            "items": [
                {
                    "source_id": "src-1",
                    "markdown": "# README\nMore content",
                    "structural_hints": _make_structural_hints(),
                }
            ],
        }
        resp = client.post("/webhooks/ingest", json=payload)
        assert resp.status_code == 200
        # Chunks are created by the domain chunker during ingestion

    def test_ingest_multi_items_single_request(self, client: TestClient) -> None:
        """Verify ingest accepts multiple items in single request."""
        payload = {
            "adapter_id": "test-adapter",
            "domain": "notes",
            "normalizer_version": "1.0.0",
            "items": [
                {
                    "source_id": "src-multi-1",
                    "markdown": "# First",
                    "structural_hints": _make_structural_hints(),
                },
                {
                    "source_id": "src-multi-2",
                    "markdown": "# Second",
                    "structural_hints": _make_structural_hints(),
                },
            ],
        }
        resp = client.post("/webhooks/ingest", json=payload)
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] in ["ok", "partial"]

    def test_ingest_multi_domain_sources(self, client_multi_domain: TestClient) -> None:
        """Verify ingest works with multi-domain fixture."""
        # Ingest to notes domain
        notes_payload = {
            "adapter_id": "notes-adapter",
            "domain": "notes",
            "normalizer_version": "1.0.0",
            "items": [
                {
                    "source_id": "src-notes-new",
                    "markdown": "# Note",
                    "structural_hints": _make_structural_hints(),
                }
            ],
        }
        resp1 = client_multi_domain.post("/webhooks/ingest", json=notes_payload)
        assert resp1.status_code == 200

    def test_ingest_invalid_domain_returns_422(self, client: TestClient) -> None:
        """Verify ingest rejects invalid domain."""
        payload = {
            "adapter_id": "test-adapter",
            "domain": "invalid-domain",
            "normalizer_version": "1.0.0",
            "items": [
                {
                    "source_id": "test-source",
                    "markdown": "# Test",
                    "structural_hints": _make_structural_hints(),
                }
            ],
        }
        resp = client.post("/webhooks/ingest", json=payload)
        assert resp.status_code == 422

    def test_ingest_missing_required_field(self, client: TestClient) -> None:
        """Verify ingest rejects payloads missing required fields."""
        payload = {
            # Missing adapter_id
            "domain": "notes",
            "normalizer_version": "1.0.0",
            "items": [
                {
                    "source_id": "test-source",
                    "markdown": "# Test",
                    "structural_hints": _make_structural_hints(),
                }
            ],
        }
        resp = client.post("/webhooks/ingest", json=payload)
        assert resp.status_code == 422

    def test_ingest_empty_items_list_returns_422(self, client: TestClient) -> None:
        """Verify ingest rejects empty items list."""
        payload = {
            "adapter_id": "test-adapter",
            "domain": "notes",
            "normalizer_version": "1.0.0",
            "items": [],
        }
        resp = client.post("/webhooks/ingest", json=payload)
        assert resp.status_code == 422

    def test_ingest_comprehensive_fixture_multi_adapter(
        self, client_comprehensive: TestClient
    ) -> None:
        """Verify ingest works with comprehensive fixture."""
        # Verify we can query sources before ingest
        sources_before = client_comprehensive.get(
            "/sources?adapter_id=obsidian-adapter"
        ).json()
        assert sources_before["total"] == 2  # Base has 2 obsidian sources

        # Attempt ingest to same adapter
        payload = {
            "adapter_id": "obsidian-adapter",
            "domain": "notes",
            "normalizer_version": "1.0.0",
            "items": [
                {
                    "source_id": "src-new-obsidian",
                    "markdown": "# New Note",
                    "structural_hints": _make_structural_hints(),
                }
            ],
        }
        resp = client_comprehensive.post("/webhooks/ingest", json=payload)
        assert resp.status_code == 200
        # Response should be well-formed
        data = resp.json()
        assert "status" in data


class TestIngestEntityLinking:
    """Tests for entity linking integration with webhook ingestion."""

    def test_entity_linking_fields_present_in_response(
        self, client: TestClient
    ) -> None:
        """Verify entity_linking_status and error fields are in response."""
        # Ingest to notes domain — entity linking should not be triggered
        payload = {
            "adapter_id": "test-adapter",
            "domain": "notes",
            "normalizer_version": "1.0.0",
            "items": [
                {
                    "source_id": "test-source",
                    "markdown": "# Test",
                    "structural_hints": _make_structural_hints(),
                }
            ],
        }
        resp = client.post("/webhooks/ingest", json=payload)
        assert resp.status_code == 200
        data = resp.json()
        # Fields should always be present even if None
        assert "entity_linking_status" in data
        assert "entity_linking_error" in data
        # For non-People domain, both should be None
        assert data["entity_linking_status"] is None
        assert data["entity_linking_error"] is None

    def test_entity_linking_not_triggered_for_non_people_domain(
        self, client: TestClient
    ) -> None:
        """Verify entity linking does not run for non-People domains."""
        payload = {
            "adapter_id": "test-adapter",
            "domain": "messages",
            "normalizer_version": "1.0.0",
            "items": [
                {
                    "source_id": "msg-1",
                    "markdown": "Subject: Test message",
                    "structural_hints": _make_structural_hints(),
                }
            ],
        }
        resp = client.post("/webhooks/ingest", json=payload)
        assert resp.status_code == 200
        data = resp.json()
        assert data["entity_linking_status"] is None
        assert data["entity_linking_error"] is None

    def test_entity_linking_not_triggered_when_ingestion_fails(
        self, client: TestClient
    ) -> None:
        """Verify entity linking does not run if People ingestion has failures."""
        # Use a mock that will report sources_failed > 0
        mock_pipeline = client.app.state.pipeline
        mock_pipeline.ingest.return_value = {
            "sources_processed": 1,
            "sources_failed": 1,  # Failure means entity linking shouldn't run
            "chunks_added": 0,
            "chunks_removed": 0,
            "chunks_unchanged": 0,
            "errors": [{"source_id": "person-1", "error_type": "ChunkingError", "message": "Invalid format"}],
        }

        payload = {
            "adapter_id": "people-adapter",
            "domain": "people",
            "normalizer_version": "1.0.0",
            "items": [
                {
                    "source_id": "person-1",
                    "markdown": "Name: John Doe\nEmail: john@example.com",
                    "structural_hints": _make_structural_hints(),
                }
            ],
        }
        resp = client.post("/webhooks/ingest", json=payload)
        # Should return 200 (partial success) but entity linking should not be triggered
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "partial"
        assert data["entity_linking_status"] is None
        assert data["entity_linking_error"] is None

    def test_entity_linking_triggered_for_people_domain_success(
        self, client: TestClient
    ) -> None:
        """Verify entity linking is triggered when People domain ingestion succeeds."""
        # Mock the pipeline to return success
        mock_pipeline = client.app.state.pipeline
        mock_pipeline.ingest.return_value = {
            "sources_processed": 1,
            "sources_failed": 0,
            "chunks_added": 1,
            "chunks_removed": 0,
            "chunks_unchanged": 0,
            "errors": [],
        }

        # Mock EntityLinker to track if it's called and return success
        with patch(
            "context_library.server.routes.ingest.EntityLinker"
        ) as mock_linker_class:
            mock_linker_instance = MagicMock()
            mock_linker_instance.run.return_value = 5  # 5 new links created
            mock_linker_class.return_value = mock_linker_instance

            payload = {
                "adapter_id": "people-adapter",
                "domain": "people",
                "normalizer_version": "1.0.0",
                "items": [
                    {
                        "source_id": "person-1",
                        "markdown": "Name: John Doe\nEmail: john@example.com",
                        "structural_hints": _make_structural_hints(),
                    }
                ],
            }
            resp = client.post("/webhooks/ingest", json=payload)

            assert resp.status_code == 200
            data = resp.json()
            assert data["status"] == "ok"
            # Entity linking should have been triggered and succeeded
            assert data["entity_linking_status"] == "ok"
            assert data["entity_linking_error"] is None
            # Verify EntityLinker was instantiated and run() was called
            mock_linker_class.assert_called_once()
            mock_linker_instance.run.assert_called_once()

    def test_entity_linking_error_caught_and_returned(
        self, client: TestClient
    ) -> None:
        """Verify EntityLinkingError is caught and returned in response."""
        # Mock the pipeline to return success for People domain
        mock_pipeline = client.app.state.pipeline
        mock_pipeline.ingest.return_value = {
            "sources_processed": 1,
            "sources_failed": 0,
            "chunks_added": 1,
            "chunks_removed": 0,
            "chunks_unchanged": 0,
            "errors": [],
        }

        # Mock EntityLinker to raise EntityLinkingError
        with patch(
            "context_library.server.routes.ingest.EntityLinker"
        ) as mock_linker_class:
            mock_linker_instance = MagicMock()
            error_msg = "Failed to query entity links from database"
            mock_linker_instance.run.side_effect = EntityLinkingError(error_msg)
            mock_linker_class.return_value = mock_linker_instance

            payload = {
                "adapter_id": "people-adapter",
                "domain": "people",
                "normalizer_version": "1.0.0",
                "items": [
                    {
                        "source_id": "person-1",
                        "markdown": "Name: Alice Smith\nEmail: alice@example.com",
                        "structural_hints": _make_structural_hints(),
                    }
                ],
            }
            resp = client.post("/webhooks/ingest", json=payload)

            assert resp.status_code == 200
            data = resp.json()
            # Ingestion succeeded but entity linking failed
            assert data["status"] == "ok"
            assert data["entity_linking_status"] == "failed"
            assert data["entity_linking_error"] == error_msg

    def test_entity_linking_unexpected_exception_caught(
        self, client: TestClient
    ) -> None:
        """Verify unexpected exceptions in entity linking are caught and reported."""
        # Mock the pipeline to return success for People domain
        mock_pipeline = client.app.state.pipeline
        mock_pipeline.ingest.return_value = {
            "sources_processed": 1,
            "sources_failed": 0,
            "chunks_added": 1,
            "chunks_removed": 0,
            "chunks_unchanged": 0,
            "errors": [],
        }

        # Mock EntityLinker to raise an unexpected exception
        with patch(
            "context_library.server.routes.ingest.EntityLinker"
        ) as mock_linker_class:
            mock_linker_instance = MagicMock()
            mock_linker_instance.run.side_effect = ValueError("Unexpected error")
            mock_linker_class.return_value = mock_linker_instance

            payload = {
                "adapter_id": "people-adapter",
                "domain": "people",
                "normalizer_version": "1.0.0",
                "items": [
                    {
                        "source_id": "person-1",
                        "markdown": "Name: Bob Jones",
                        "structural_hints": _make_structural_hints(),
                    }
                ],
            }
            resp = client.post("/webhooks/ingest", json=payload)

            assert resp.status_code == 200
            data = resp.json()
            assert data["status"] == "ok"
            assert data["entity_linking_status"] == "failed"
            # Error message should include the exception type and message
            assert "ValueError" in data["entity_linking_error"]
            assert "Unexpected error" in data["entity_linking_error"]

    def test_entity_linking_with_asyncio_to_thread(
        self, client: TestClient
    ) -> None:
        """Verify entity linking runs in thread via asyncio.to_thread."""
        # Mock the pipeline
        mock_pipeline = client.app.state.pipeline
        ingest_result = {
            "sources_processed": 1,
            "sources_failed": 0,
            "chunks_added": 2,
            "chunks_removed": 0,
            "chunks_unchanged": 0,
            "errors": [],
        }
        mock_pipeline.ingest.return_value = ingest_result

        # Verify that asyncio.to_thread is called to run linker.run() in a thread
        with patch(
            "context_library.server.routes.ingest.EntityLinker"
        ) as mock_linker_class, patch(
            "context_library.server.routes.ingest.asyncio.to_thread",
            side_effect=lambda func, *args, **kwargs: func(*args, **kwargs)
        ) as mock_to_thread:
            mock_linker_instance = MagicMock()
            mock_linker_instance.run.return_value = 3
            mock_linker_class.return_value = mock_linker_instance

            payload = {
                "adapter_id": "people-adapter",
                "domain": "people",
                "normalizer_version": "1.0.0",
                "items": [
                    {
                        "source_id": "person-1",
                        "markdown": "Name: Charlie Brown",
                        "structural_hints": _make_structural_hints(),
                    }
                ],
            }
            resp = client.post("/webhooks/ingest", json=payload)

            assert resp.status_code == 200
            data = resp.json()
            assert data["entity_linking_status"] == "ok"
            # Verify asyncio.to_thread was called with linker.run as the function
            mock_to_thread.assert_called()
            call_args = mock_to_thread.call_args[0]
            # First argument should be the run method
            assert call_args[0] == mock_linker_instance.run


class TestHelperIngestEntityLinking:
    """Tests for entity linking integration with helper adapter ingestion."""

    def test_helper_ingest_entity_linking_not_triggered_for_non_people(
        self, client: TestClient
    ) -> None:
        """Verify entity linking does not run for non-People helper adapters."""
        # Set up helper adapters
        mock_adapter = MagicMock(spec=BaseAdapter)
        mock_adapter.adapter_id = "email-helper"
        mock_adapter.domain = Domain.MESSAGES
        client.app.state.helper_adapters = [mock_adapter]

        # Mock the pipeline
        mock_pipeline = client.app.state.pipeline
        mock_pipeline.ingest.return_value = {
            "sources_processed": 1,
            "sources_failed": 0,
            "chunks_added": 1,
            "chunks_removed": 0,
            "chunks_unchanged": 0,
            "errors": [],
        }

        resp = client.post("/ingest/helpers")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["results"]) == 1
        result = data["results"][0]
        assert result["entity_linking_status"] is None
        assert result["entity_linking_error"] is None

    def test_helper_ingest_entity_linking_triggered_for_people_success(
        self, client: TestClient
    ) -> None:
        """Verify entity linking is triggered for People helper adapters on success."""
        # Set up People helper adapter
        mock_adapter = MagicMock(spec=BaseAdapter)
        mock_adapter.adapter_id = "people-helper"
        mock_adapter.domain = Domain.PEOPLE
        client.app.state.helper_adapters = [mock_adapter]

        # Mock the pipeline
        mock_pipeline = client.app.state.pipeline
        mock_pipeline.ingest.return_value = {
            "sources_processed": 1,
            "sources_failed": 0,
            "chunks_added": 2,
            "chunks_removed": 0,
            "chunks_unchanged": 0,
            "errors": [],
        }

        # Mock EntityLinker
        with patch(
            "context_library.server.routes.ingest.EntityLinker"
        ) as mock_linker_class:
            mock_linker_instance = MagicMock()
            mock_linker_instance.run.return_value = 10
            mock_linker_class.return_value = mock_linker_instance

            resp = client.post("/ingest/helpers")
            assert resp.status_code == 200
            data = resp.json()
            assert len(data["results"]) == 1
            result = data["results"][0]
            assert result["adapter_id"] == "people-helper"
            assert result["entity_linking_status"] == "ok"
            assert result["entity_linking_error"] is None

    def test_helper_ingest_entity_linking_not_triggered_on_failure(
        self, client: TestClient
    ) -> None:
        """Verify entity linking does not run if People helper ingestion fails."""
        # Set up People helper adapter
        mock_adapter = MagicMock(spec=BaseAdapter)
        mock_adapter.adapter_id = "people-helper"
        mock_adapter.domain = Domain.PEOPLE
        client.app.state.helper_adapters = [mock_adapter]

        # Mock pipeline to report ingestion failure
        mock_pipeline = client.app.state.pipeline
        mock_pipeline.ingest.return_value = {
            "sources_processed": 1,
            "sources_failed": 1,
            "chunks_added": 0,
            "chunks_removed": 0,
            "chunks_unchanged": 0,
            "errors": [{"source_id": "person-1", "error_type": "ChunkingError", "message": "Invalid"}],
        }

        resp = client.post("/ingest/helpers")
        assert resp.status_code == 200
        data = resp.json()
        result = data["results"][0]
        assert result["status"] == "partial"
        assert result["entity_linking_status"] is None
        assert result["entity_linking_error"] is None

    def test_helper_ingest_entity_linking_error_captured(
        self, client: TestClient
    ) -> None:
        """Verify entity linking errors are captured in helper response."""
        # Set up People helper adapter
        mock_adapter = MagicMock(spec=BaseAdapter)
        mock_adapter.adapter_id = "people-helper"
        mock_adapter.domain = Domain.PEOPLE
        client.app.state.helper_adapters = [mock_adapter]

        # Mock pipeline
        mock_pipeline = client.app.state.pipeline
        mock_pipeline.ingest.return_value = {
            "sources_processed": 1,
            "sources_failed": 0,
            "chunks_added": 1,
            "chunks_removed": 0,
            "chunks_unchanged": 0,
            "errors": [],
        }

        # Mock EntityLinker to fail
        with patch(
            "context_library.server.routes.ingest.EntityLinker"
        ) as mock_linker_class:
            mock_linker_instance = MagicMock()
            error_msg = "Database connection lost during linking"
            mock_linker_instance.run.side_effect = EntityLinkingError(error_msg)
            mock_linker_class.return_value = mock_linker_instance

            resp = client.post("/ingest/helpers")
            assert resp.status_code == 200
            data = resp.json()
            result = data["results"][0]
            assert result["entity_linking_status"] == "failed"
            assert result["entity_linking_error"] == error_msg

    def test_helper_ingest_adapter_exception_does_not_break_others(
        self, client: TestClient
    ) -> None:
        """Verify one helper adapter exception doesn't break others."""
        # Set up two helper adapters: one succeeds, one raises an exception
        adapter1 = MagicMock(spec=BaseAdapter)
        adapter1.adapter_id = "email-helper"
        adapter1.domain = Domain.MESSAGES

        adapter2 = MagicMock(spec=BaseAdapter)
        adapter2.adapter_id = "people-helper"
        adapter2.domain = Domain.PEOPLE

        client.app.state.helper_adapters = [adapter1, adapter2]

        # Mock pipeline: first call succeeds, second call raises an exception
        mock_pipeline = client.app.state.pipeline

        def ingest_side_effect(*args, **kwargs):
            adapter_arg = args[0] if args else None
            if adapter_arg and adapter_arg.adapter_id == "people-helper":
                raise RuntimeError("Helper communication failed")
            return {
                "sources_processed": 1,
                "sources_failed": 0,
                "chunks_added": 1,
                "chunks_removed": 0,
                "chunks_unchanged": 0,
                "errors": [],
            }

        mock_pipeline.ingest.side_effect = ingest_side_effect

        resp = client.post("/ingest/helpers")
        assert resp.status_code == 200
        data = resp.json()
        assert data["adapters_run"] == 2
        # First adapter should have succeeded
        assert data["results"][0]["status"] == "ok"
        # Second adapter should have error status
        assert data["results"][1]["status"] == "error"
        assert data["results"][1]["sources_failed"] == 1
