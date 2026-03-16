"""Tests for /chunks endpoints."""

from fastapi.testclient import TestClient


class TestGetChunk:
    def test_returns_chunk(self, client: TestClient, chunk_hash: str) -> None:
        resp = client.get(f"/chunks/{chunk_hash}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["chunk_hash"] == chunk_hash
        assert data["content"] == "Hello world"
        assert "lineage" in data

    def test_with_source_id_filter(self, client: TestClient, chunk_hash: str) -> None:
        resp = client.get(f"/chunks/{chunk_hash}?source_id=src-1")
        assert resp.status_code == 200
        assert resp.json()["chunk_hash"] == chunk_hash

    def test_404_for_missing_hash(self, client: TestClient) -> None:
        resp = client.get(f"/chunks/{'a' * 64}")
        assert resp.status_code == 404

    def test_422_for_invalid_hash_format(self, client: TestClient) -> None:
        resp = client.get("/chunks/not-a-hash")
        assert resp.status_code == 422

    def test_links_present(self, client: TestClient, chunk_hash: str) -> None:
        data = client.get(f"/chunks/{chunk_hash}").json()
        links = data["_links"]
        assert "self" in links
        assert "provenance" in links
        assert "version_chain" in links


class TestGetChunkProvenance:
    def test_returns_provenance(self, client: TestClient, chunk_hash: str) -> None:
        resp = client.get(f"/chunks/{chunk_hash}/provenance?source_id=src-1")
        assert resp.status_code == 200
        data = resp.json()
        assert data["source_origin_ref"] == "/docs/readme.md"
        assert data["adapter_type"] == "filesystem"
        assert len(data["version_chain"]) >= 1

    def test_404_for_missing_chunk(self, client: TestClient) -> None:
        resp = client.get(f"/chunks/{'b' * 64}/provenance?source_id=src-1")
        assert resp.status_code == 404

    def test_422_for_invalid_hash(self, client: TestClient) -> None:
        resp = client.get("/chunks/badhash/provenance")
        assert resp.status_code == 422


class TestGetChunkVersionChain:
    def test_returns_chain(self, client: TestClient, chunk_hash: str) -> None:
        resp = client.get(f"/chunks/{chunk_hash}/version-chain?source_id=src-1")
        assert resp.status_code == 200
        data = resp.json()
        assert data["chunk_hash"] == chunk_hash
        assert data["source_id"] == "src-1"
        assert len(data["chain"]) == 1

    def test_404_for_missing_chunk_in_source(self, client: TestClient) -> None:
        resp = client.get(f"/chunks/{'c' * 64}/version-chain?source_id=src-1")
        assert resp.status_code == 404

    def test_422_requires_source_id(self, client: TestClient, chunk_hash: str) -> None:
        resp = client.get(f"/chunks/{chunk_hash}/version-chain")
        assert resp.status_code == 422


class TestListChunks:
    def test_returns_200(self, client: TestClient) -> None:
        resp = client.get("/chunks")
        assert resp.status_code == 200

    def test_response_structure(self, client: TestClient) -> None:
        data = client.get("/chunks").json()
        assert "chunks" in data
        assert "total" in data
        assert "limit" in data
        assert "offset" in data
        assert isinstance(data["chunks"], list)
        assert isinstance(data["total"], int)

    def test_returns_chunk_in_list(self, client: TestClient, chunk_hash: str) -> None:
        data = client.get("/chunks").json()
        assert data["total"] == 1
        assert len(data["chunks"]) == 1
        chunk = data["chunks"][0]
        assert chunk["chunk_hash"] == chunk_hash
        assert chunk["content"] == "Hello world"
        assert "_links" in chunk

    def test_pagination_limit(self, client: TestClient, ds, chunk_hash: str) -> None:
        resp = client.get("/chunks?limit=1")
        data = resp.json()
        assert data["limit"] == 1
        assert len(data["chunks"]) <= 1

    def test_pagination_offset(self, client: TestClient) -> None:
        resp = client.get("/chunks?limit=10&offset=5")
        data = resp.json()
        assert data["offset"] == 5

    def test_filters_by_domain(self, client: TestClient, chunk_hash: str) -> None:
        # Test with matching domain
        resp = client.get("/chunks?domain=notes")
        data = resp.json()
        assert data["total"] == 1
        assert len(data["chunks"]) == 1

        # Test with non-matching domain
        resp = client.get("/chunks?domain=messages")
        data = resp.json()
        assert data["total"] == 0
        assert len(data["chunks"]) == 0

    def test_filters_by_adapter_id(self, client: TestClient, chunk_hash: str) -> None:
        # Test with matching adapter_id
        resp = client.get("/chunks?adapter_id=test-adapter")
        data = resp.json()
        assert data["total"] == 1
        assert len(data["chunks"]) == 1

        # Test with non-matching adapter_id
        resp = client.get("/chunks?adapter_id=nonexistent")
        data = resp.json()
        assert data["total"] == 0
        assert len(data["chunks"]) == 0

    def test_filters_by_domain_and_adapter(self, client: TestClient, chunk_hash: str) -> None:
        resp = client.get("/chunks?domain=notes&adapter_id=test-adapter")
        data = resp.json()
        assert data["total"] == 1
        assert len(data["chunks"]) == 1

    def test_filters_by_source_id(self, client: TestClient, chunk_hash: str) -> None:
        # Test with matching source_id
        resp = client.get("/chunks?source_id=src-1")
        data = resp.json()
        assert data["total"] == 1
        assert len(data["chunks"]) == 1
        assert data["chunks"][0]["chunk_hash"] == chunk_hash

        # Test with non-matching source_id
        resp = client.get("/chunks?source_id=nonexistent-source")
        data = resp.json()
        assert data["total"] == 0
        assert len(data["chunks"]) == 0

    def test_invalid_limit_too_large(self, client: TestClient) -> None:
        resp = client.get("/chunks?limit=2000")
        assert resp.status_code == 422

    def test_invalid_limit_zero(self, client: TestClient) -> None:
        resp = client.get("/chunks?limit=0")
        assert resp.status_code == 422

    def test_invalid_offset_negative(self, client: TestClient) -> None:
        resp = client.get("/chunks?offset=-1")
        assert resp.status_code == 422

    def test_list_chunks_with_domain_metadata(
        self, client_with_metadata: TestClient
    ) -> None:
        """Verify chunks with domain_metadata are properly deserialized in list response."""
        resp = client_with_metadata.get("/chunks")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] >= 1
        chunks = data["chunks"]
        # Find the chunk with metadata
        metadata_chunk = None
        for chunk_item in chunks:
            if chunk_item["domain_metadata"] is not None:
                metadata_chunk = chunk_item
                break
        # Verify metadata was properly deserialized from JSON string
        assert metadata_chunk is not None, "Should have chunk with domain_metadata"
        assert isinstance(
            metadata_chunk["domain_metadata"], dict
        ), "domain_metadata should be deserialized as dict"
        assert (
            metadata_chunk["domain_metadata"]["title"] == "Test Section"
        ), "metadata should be accessible"
        # Verify _system_cross_refs was removed from domain_metadata
        assert (
            "_system_cross_refs" not in metadata_chunk["domain_metadata"]
        ), "_system_cross_refs should not leak into response"
        # Verify cross_refs were extracted
        assert (
            len(metadata_chunk["cross_refs"]) > 0
        ), "cross_refs should be populated from _system_cross_refs"

    def test_list_chunks_skips_corrupt_chunks(self, client: TestClient, ds) -> None:
        """Verify that corrupt chunks (malformed JSON) are skipped without crashing the endpoint.

        This tests the fix for issue #282: when one chunk has corrupt domain_metadata JSON,
        the list endpoint should skip it with a warning instead of returning a 500 error.
        """
        from context_library.storage.models import compute_chunk_hash, Chunk, ChunkType, LineageRecord, Domain

        # Create a valid chunk
        valid_content = "Valid chunk content"
        valid_hash = compute_chunk_hash(valid_content)
        valid_chunk = Chunk(
            chunk_hash=valid_hash,
            content=valid_content,
            context_header="## Valid",
            chunk_index=0,
            chunk_type=ChunkType.STANDARD,
        )

        # Create a new version with the valid chunk
        ds.create_source_version(
            source_id="src-1",
            version=3,
            markdown=valid_content,
            chunk_hashes=[valid_hash],
            adapter_id="test-adapter",
            normalizer_version="1.0.0",
            fetch_timestamp="2024-01-03T00:00:00+00:00",
        )
        valid_lineage = LineageRecord(
            chunk_hash=valid_hash,
            source_id="src-1",
            source_version_id=3,
            adapter_id="test-adapter",
            domain=Domain.NOTES,
            normalizer_version="1.0.0",
            embedding_model_id="test-model",
        )
        ds.write_chunks(chunks=[valid_chunk], lineage_records=[valid_lineage])

        # Now insert a corrupt chunk directly into the database with malformed JSON
        cursor = ds.conn.cursor()
        corrupt_hash = "c" * 64
        cursor.execute(
            """
            INSERT INTO chunks (chunk_hash, source_id, source_version, chunk_index, content,
                              context_header, domain, adapter_id, chunk_type, domain_metadata,
                              normalizer_version, embedding_model_id, fetch_timestamp)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            """,
            (corrupt_hash, "src-1", 3, 1, "Corrupt content", "## Corrupt", "notes",
             "test-adapter", "standard", "{ invalid json }", "1.0.0", "test-model"),
        )
        ds.conn.commit()

        # Query the list endpoint - it should NOT crash even though one chunk is corrupt
        resp = client.get("/chunks")
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        data = resp.json()

        # The valid chunk should be returned, corrupt chunk should be skipped
        assert data["total"] >= 1  # Total includes corrupt chunk in DB count
        assert len(data["chunks"]) >= 1  # But only valid chunks in response

        # Verify the valid chunk is in the response
        found_valid = False
        for chunk_item in data["chunks"]:
            if chunk_item["chunk_hash"] == valid_hash:
                found_valid = True
                assert chunk_item["content"] == valid_content
                break

        assert found_valid, "Valid chunk should be returned"
