"""Tests for source_id_prefix filtering on GET /sources endpoint."""

from fastapi.testclient import TestClient
import pytest
import tempfile
import os
from context_library.storage.document_store import DocumentStore
from context_library.storage.models import (
    AdapterConfig,
    Chunk,
    ChunkType,
    Domain,
    LineageRecord,
    PollStrategy,
    compute_chunk_hash,
)
from typing import Generator

from .conftest import _create_app_with_store


@pytest.fixture()
def ds_with_hierarchical_sources() -> Generator[DocumentStore, None, None]:
    """DocumentStore with hierarchical source_ids for prefix filtering tests."""
    temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=".db")
    temp_path = temp_file.name
    temp_file.close()

    store = DocumentStore(temp_path, check_same_thread=False)

    # Register filesystem adapter
    config = AdapterConfig(
        adapter_id="filesystem:default",
        adapter_type="filesystem",
        domain=Domain.DOCUMENTS,
        normalizer_version="1.0.0",
    )
    store.register_adapter(config)

    # Create sources with hierarchical paths, including ones with GLOB wildcard characters
    test_sources = [
        "projects/alpha/doc1.md",
        "projects/alpha/doc2.md",
        "projects/alpha/subfolder/doc3.md",
        "projects/beta/doc4.md",
        "projects/beta/subfolder/doc5.md",
        "notes/personal/doc6.md",
        "notes/work/doc7.md",
        "projects_test/doc.md",  # Source with underscore (not special in GLOB)
        "reports%archive/doc8.md",  # Source with % character (not special in GLOB)
        "data[0]/file.md",  # Source with brackets for GLOB escape sequence test
        "files*/archive/doc9.md",  # Source with GLOB wildcard * character
        "filesX/archive/doc10.md",  # Control source for * escaping test
        "docs?/report.md",  # Source with GLOB wildcard ? character
        "docsX/report2.md",  # Control source for ? escaping test
    ]

    for source_id in test_sources:
        store.register_source(
            source_id=source_id,
            adapter_id="filesystem:default",
            domain=Domain.DOCUMENTS,
            origin_ref=f"/fs/{source_id}",
            poll_strategy=PollStrategy.PULL,
            poll_interval_sec=3600,
        )

        # Create version 1 with a chunk
        content = f"Content for {source_id}"
        chunk_hash = compute_chunk_hash(content)
        chunk = Chunk(
            chunk_hash=chunk_hash,
            content=content,
            context_header=f"# {source_id}",
            chunk_index=0,
            chunk_type=ChunkType.STANDARD,
        )

        store.create_source_version(
            source_id=source_id,
            version=1,
            markdown=f"# {source_id}\n{content}",
            chunk_hashes=[chunk_hash],
            adapter_id="filesystem:default",
            normalizer_version="1.0.0",
            fetch_timestamp="2024-01-01T00:00:00+00:00",
        )
        lineage = LineageRecord(
            chunk_hash=chunk_hash,
            source_id=source_id,
            source_version_id=1,
            adapter_id="filesystem:default",
            domain=Domain.DOCUMENTS,
            normalizer_version="1.0.0",
            embedding_model_id="all-MiniLM-L6-v2",
        )
        store.write_chunks(
            chunks=[chunk],
            lineage_records=[lineage],
        )

    yield store

    # Cleanup
    store.close()
    try:
        os.unlink(temp_path)
    except OSError:
        pass


@pytest.fixture()
def client_with_hierarchical_sources(
    ds_with_hierarchical_sources: DocumentStore,
) -> Generator[TestClient, None, None]:
    """TestClient with hierarchical sources fixture."""
    yield from _create_app_with_store(ds_with_hierarchical_sources)


class TestSourceIdPrefixFilter:
    """Test source_id_prefix filtering functionality."""

    def test_prefix_filter_returns_matching_sources(
        self, client_with_hierarchical_sources: TestClient
    ) -> None:
        """Test that prefix filter returns only sources starting with prefix."""
        resp = client_with_hierarchical_sources.get("/sources?source_id_prefix=projects/alpha/")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 3
        source_ids = [s["source_id"] for s in data["sources"]]
        assert "projects/alpha/doc1.md" in source_ids
        assert "projects/alpha/doc2.md" in source_ids
        assert "projects/alpha/subfolder/doc3.md" in source_ids
        # Should not include other projects
        assert "projects/beta/doc4.md" not in source_ids

    def test_prefix_filter_with_beta_project(
        self, client_with_hierarchical_sources: TestClient
    ) -> None:
        """Test prefix filter for a different project."""
        resp = client_with_hierarchical_sources.get("/sources?source_id_prefix=projects/beta/")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 2
        source_ids = [s["source_id"] for s in data["sources"]]
        assert "projects/beta/doc4.md" in source_ids
        assert "projects/beta/subfolder/doc5.md" in source_ids

    def test_prefix_filter_for_notes(
        self, client_with_hierarchical_sources: TestClient
    ) -> None:
        """Test prefix filter for notes folder."""
        resp = client_with_hierarchical_sources.get("/sources?source_id_prefix=notes/")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 2
        source_ids = [s["source_id"] for s in data["sources"]]
        assert "notes/personal/doc6.md" in source_ids
        assert "notes/work/doc7.md" in source_ids

    def test_nonexistent_prefix_returns_empty_list(
        self, client_with_hierarchical_sources: TestClient
    ) -> None:
        """Test that nonexistent prefix returns empty list with HTTP 200."""
        resp = client_with_hierarchical_sources.get("/sources?source_id_prefix=nonexistent/")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 0
        assert data["sources"] == []

    def test_no_prefix_param_returns_all(
        self, client_with_hierarchical_sources: TestClient
    ) -> None:
        """Test that omitting prefix param returns all sources."""
        resp = client_with_hierarchical_sources.get("/sources")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 14
        assert len(data["sources"]) == 14

    def test_prefix_filter_with_domain_filter(
        self, client_with_hierarchical_sources: TestClient
    ) -> None:
        """Test that prefix filter composes with domain filter."""
        resp = client_with_hierarchical_sources.get(
            "/sources?source_id_prefix=projects/alpha/&domain=documents"
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 3
        source_ids = [s["source_id"] for s in data["sources"]]
        assert "projects/alpha/doc1.md" in source_ids

    def test_prefix_filter_with_adapter_filter(
        self, client_with_hierarchical_sources: TestClient
    ) -> None:
        """Test that prefix filter composes with adapter_id filter."""
        resp = client_with_hierarchical_sources.get(
            "/sources?source_id_prefix=projects/&adapter_id=filesystem:default"
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 5
        # All projects sources
        source_ids = [s["source_id"] for s in data["sources"]]
        assert all(s.startswith("projects/") for s in source_ids)

    def test_prefix_filter_with_both_domain_and_adapter_filters(
        self, client_with_hierarchical_sources: TestClient
    ) -> None:
        """Test that all three filters compose conjunctively."""
        resp = client_with_hierarchical_sources.get(
            "/sources?source_id_prefix=projects/beta/&domain=documents&adapter_id=filesystem:default"
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 2
        source_ids = [s["source_id"] for s in data["sources"]]
        assert "projects/beta/doc4.md" in source_ids
        assert "projects/beta/subfolder/doc5.md" in source_ids

    def test_prefix_filter_respects_pagination(
        self, client_with_hierarchical_sources: TestClient
    ) -> None:
        """Test that prefix filter respects pagination parameters."""
        resp = client_with_hierarchical_sources.get(
            "/sources?source_id_prefix=projects/&limit=2&offset=0"
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 5  # Total matching count
        assert len(data["sources"]) == 2  # Page size
        assert data["limit"] == 2
        assert data["offset"] == 0

    def test_prefix_filter_pagination_offset(
        self, client_with_hierarchical_sources: TestClient
    ) -> None:
        """Test pagination offset with prefix filter."""
        resp = client_with_hierarchical_sources.get(
            "/sources?source_id_prefix=projects/&limit=2&offset=2"
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 5
        assert len(data["sources"]) == 2
        assert data["offset"] == 2

    def test_empty_prefix_string_matches_all(
        self, client_with_hierarchical_sources: TestClient
    ) -> None:
        """Test that empty prefix string matches all sources."""
        resp = client_with_hierarchical_sources.get("/sources?source_id_prefix=")
        assert resp.status_code == 200
        data = resp.json()
        # Empty string matches everything (all sources start with empty string)
        assert data["total"] == 14

    def test_prefix_case_insensitive(
        self, client_with_hierarchical_sources: TestClient
    ) -> None:
        """Test that prefix matching is case-insensitive (LIKE behavior).

        SQLite LIKE operator is case-insensitive by default, which provides standard SQL
        semantics. A search for "Projects/" will match "projects/" entries.
        """
        resp = client_with_hierarchical_sources.get("/sources?source_id_prefix=Projects/")
        assert resp.status_code == 200
        data = resp.json()
        # LIKE is case-insensitive, so uppercase "Projects/" will match lowercase "projects/"
        assert data["total"] == 5
        source_ids = [s["source_id"] for s in data["sources"]]
        assert all(s.lower().startswith("projects/") for s in source_ids)

    def test_prefix_case_insensitive_mixed_case(
        self, client_with_hierarchical_sources: TestClient
    ) -> None:
        """Test that LIKE provides case-insensitive matching for mixed cases."""
        resp = client_with_hierarchical_sources.get("/sources?source_id_prefix=pRoJeCtS/")
        assert resp.status_code == 200
        data = resp.json()
        # LIKE is case-insensitive, so mixed case prefix will match lowercase sources
        assert data["total"] == 5
        source_ids = [s["source_id"] for s in data["sources"]]
        assert all(s.lower().startswith("projects/") for s in source_ids)

    def test_partial_path_prefix(
        self, client_with_hierarchical_sources: TestClient
    ) -> None:
        """Test prefix matching on partial folder names."""
        resp = client_with_hierarchical_sources.get("/sources?source_id_prefix=projects/alpha/sub")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 1
        assert data["sources"][0]["source_id"] == "projects/alpha/subfolder/doc3.md"

    def test_result_ordering(
        self, client_with_hierarchical_sources: TestClient
    ) -> None:
        """Test that results are ordered by source_id."""
        resp = client_with_hierarchical_sources.get("/sources?source_id_prefix=projects/")
        assert resp.status_code == 200
        data = resp.json()
        source_ids = [s["source_id"] for s in data["sources"]]
        # Verify ordering
        assert source_ids == sorted(source_ids)

    def test_prefix_with_underscore_escaped(
        self, client_with_hierarchical_sources: TestClient
    ) -> None:
        """Test that underscore in prefix is properly escaped for LIKE.

        In LIKE, underscore (_) is a wildcard matching any single character. This test ensures
        that sources with literal underscore characters are found correctly by escaping the
        underscore in the prefix.
        """
        # Search for exact prefix with underscore - should only match the specific source
        resp = client_with_hierarchical_sources.get("/sources?source_id_prefix=projects_test/")
        assert resp.status_code == 200
        data = resp.json()
        # Should only match "projects_test/" not other "projects*/" sources
        # Underscore is escaped to match the literal character
        assert data["total"] == 1
        assert data["sources"][0]["source_id"] == "projects_test/doc.md"

    def test_prefix_underscore_not_wildcard(
        self, client_with_hierarchical_sources: TestClient
    ) -> None:
        """Test that escaped underscore in prefix matches only literal underscores.

        In LIKE, underscore (_) is a wildcard matching any single character. However, when
        properly escaped, it will match only literal underscores. This test verifies the
        escaping works correctly.
        """
        # Search for exact prefix with underscore - properly escaped
        resp = client_with_hierarchical_sources.get("/sources?source_id_prefix=projects_test/")
        assert resp.status_code == 200
        data = resp.json()
        # Should only match the source with actual underscore
        assert data["total"] == 1
        assert data["sources"][0]["source_id"] == "projects_test/doc.md"

        # Verify that "projects/" prefix still matches multiple sources
        resp2 = client_with_hierarchical_sources.get("/sources?source_id_prefix=projects/")
        assert resp2.status_code == 200
        data2 = resp2.json()
        # Should match projects/alpha and projects/beta sources (5 total)
        assert data2["total"] == 5
        project_sources = [s["source_id"] for s in data2["sources"]]
        assert "projects_test/doc.md" not in project_sources  # Underscore source not included

    def test_prefix_with_percent_escaped(
        self, client_with_hierarchical_sources: TestClient
    ) -> None:
        """Test that % character in prefix is properly escaped for LIKE.

        In LIKE, percent (%) is a wildcard matching any sequence of characters. This test
        verifies that sources with literal % characters are found correctly when the percent
        is properly escaped in the prefix.
        """
        # Search for prefix with % character, using params kwarg for proper URL encoding
        resp = client_with_hierarchical_sources.get("/sources", params={"source_id_prefix": "reports%archive/"})
        assert resp.status_code == 200
        data = resp.json()
        # Should only match the source with actual % character (properly escaped)
        assert data["total"] == 1
        assert data["sources"][0]["source_id"] == "reports%archive/doc8.md"

    def test_prefix_partial_match_with_percent_in_source(
        self, client_with_hierarchical_sources: TestClient
    ) -> None:
        """Test partial prefix matching on sources with % characters in their names.

        Verify that prefix matching works correctly even when the source name contains
        special characters like %.
        """
        # Search for prefix "reports" which is before the % character
        resp = client_with_hierarchical_sources.get("/sources", params={"source_id_prefix": "reports"})
        assert resp.status_code == 200
        data = resp.json()
        # Should match the source with % in its name
        assert data["total"] == 1
        assert data["sources"][0]["source_id"] == "reports%archive/doc8.md"

    def test_prefix_with_bracket_characters(
        self, client_with_hierarchical_sources: TestClient
    ) -> None:
        """Test that bracket characters in prefix are handled correctly for LIKE.

        In LIKE, brackets do not have special meaning (they are literal characters). This test
        verifies that sources with literal bracket characters can be found by exact prefix matching.
        """
        # Search for prefix with bracket character
        resp = client_with_hierarchical_sources.get("/sources", params={"source_id_prefix": "data[0]/"})
        assert resp.status_code == 200
        data = resp.json()
        # Should only match the source with actual bracket characters
        assert data["total"] == 1
        assert data["sources"][0]["source_id"] == "data[0]/file.md"

    def test_prefix_with_asterisk_character(
        self, client_with_hierarchical_sources: TestClient
    ) -> None:
        """Test that * (asterisk) character in prefix is handled correctly for LIKE.

        In LIKE, asterisk (*) does not have special meaning (it is a literal character).
        This test verifies that sources with literal * characters can be found by exact
        prefix matching.
        """
        # Search for prefix with * character, using params kwarg for proper URL encoding
        resp = client_with_hierarchical_sources.get("/sources", params={"source_id_prefix": "files*/"})
        assert resp.status_code == 200
        data = resp.json()
        # Should only match the source with actual * character
        assert data["total"] == 1
        assert data["sources"][0]["source_id"] == "files*/archive/doc9.md"

    def test_prefix_with_question_mark_character(
        self, client_with_hierarchical_sources: TestClient
    ) -> None:
        """Test that ? (question mark) character in prefix is handled correctly for LIKE.

        In LIKE, question mark (?) does not have special meaning (it is a literal character).
        This test verifies that sources with literal ? characters can be found by exact
        prefix matching.
        """
        # Search for prefix with ? character, using params kwarg for proper URL encoding
        resp = client_with_hierarchical_sources.get("/sources", params={"source_id_prefix": "docs?/"})
        assert resp.status_code == 200
        data = resp.json()
        # Should only match the source with actual ? character
        assert data["total"] == 1
        assert data["sources"][0]["source_id"] == "docs?/report.md"

    def test_prefix_asterisk_not_wildcard_in_like(
        self, client_with_hierarchical_sources: TestClient
    ) -> None:
        """Test that * character does not act as a LIKE wildcard.

        In LIKE, asterisk (*) is not a wildcard character. This test verifies that sources
        can have literal * characters and they are matched correctly.
        """
        # Search for prefix with * character
        resp = client_with_hierarchical_sources.get("/sources", params={"source_id_prefix": "files*/"})
        assert resp.status_code == 200
        data = resp.json()
        # Should match only the source with literal * character
        assert data["total"] == 1
        source_id = data["sources"][0]["source_id"]
        assert source_id == "files*/archive/doc9.md"

        # Verify the control source "filesX/" is still accessible
        resp2 = client_with_hierarchical_sources.get("/sources", params={"source_id_prefix": "filesX/"})
        assert resp2.status_code == 200
        data2 = resp2.json()
        assert data2["total"] == 1
        assert data2["sources"][0]["source_id"] == "filesX/archive/doc10.md"

    def test_prefix_question_not_wildcard_in_like(
        self, client_with_hierarchical_sources: TestClient
    ) -> None:
        """Test that ? character does not act as a LIKE wildcard.

        In LIKE, question mark (?) is not a wildcard character. This test verifies that
        sources can have literal ? characters and they are matched correctly.
        """
        # Search for prefix with ? character
        resp = client_with_hierarchical_sources.get("/sources", params={"source_id_prefix": "docs?/"})
        assert resp.status_code == 200
        data = resp.json()
        # Should match only the source with literal ? character
        assert data["total"] == 1
        source_id = data["sources"][0]["source_id"]
        assert source_id == "docs?/report.md"

        # Verify the control source "docsX/" is still accessible
        resp2 = client_with_hierarchical_sources.get("/sources", params={"source_id_prefix": "docsX/"})
        assert resp2.status_code == 200
        data2 = resp2.json()
        assert data2["total"] == 1
        assert data2["sources"][0]["source_id"] == "docsX/report2.md"
