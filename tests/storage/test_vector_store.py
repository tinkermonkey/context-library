"""Tests for the vector store.

NOTE: Full ChunkVector field tests are blocked by issue #10 (Vector type hint syntax).
Once that is resolved, add tests for: chunk_hash, content, vector, domain, source_id,
source_version, and created_at field types and defaults.
"""

import pytest


class TestValidateEmbeddingDimension:
    """Tests for embedding dimension validation."""

    def test_valid_dimension(self) -> None:
        """Valid embedding dimension passes without raising."""
        # Import here to avoid module-level LanceModel import error
        from context_library.storage.vector_store import (
            EMBEDDING_DIM,
            validate_embedding_dimension,
        )

        valid_embedding = [0.1] * EMBEDDING_DIM
        # Should not raise
        validate_embedding_dimension(valid_embedding)

    def test_invalid_dimension_too_short(self) -> None:
        """Embedding shorter than expected dimension raises ValueError."""
        from context_library.storage.vector_store import (
            EMBEDDING_DIM,
            validate_embedding_dimension,
        )

        short_embedding = [0.1] * (EMBEDDING_DIM - 1)
        with pytest.raises(ValueError) as exc_info:
            validate_embedding_dimension(short_embedding)
        assert "Embedding dimension mismatch" in str(exc_info.value)
        assert f"expected {EMBEDDING_DIM}" in str(exc_info.value)

    def test_invalid_dimension_too_long(self) -> None:
        """Embedding longer than expected dimension raises ValueError."""
        from context_library.storage.vector_store import (
            EMBEDDING_DIM,
            validate_embedding_dimension,
        )

        long_embedding = [0.1] * (EMBEDDING_DIM + 1)
        with pytest.raises(ValueError) as exc_info:
            validate_embedding_dimension(long_embedding)
        assert "Embedding dimension mismatch" in str(exc_info.value)
        assert f"expected {EMBEDDING_DIM}" in str(exc_info.value)

    def test_error_message_content(self) -> None:
        """Error message includes helpful guidance."""
        from context_library.storage.vector_store import (
            validate_embedding_dimension,
        )

        wrong_embedding = [0.5] * 100
        with pytest.raises(ValueError) as exc_info:
            validate_embedding_dimension(wrong_embedding)
        error_msg = str(exc_info.value)
        assert "embedding model configuration" in error_msg
        assert "EMBEDDING_DIM" in error_msg


class TestDomain:
    """Tests for the Domain enum."""

    def test_domain_members_exist(self) -> None:
        """All expected domain members are defined."""
        from context_library.storage.vector_store import Domain

        assert hasattr(Domain, "MESSAGES")
        assert hasattr(Domain, "NOTES")
        assert hasattr(Domain, "EVENTS")
        assert hasattr(Domain, "TASKS")

    def test_domain_values(self) -> None:
        """Domain enum values are correct."""
        from context_library.storage.vector_store import Domain

        assert Domain.MESSAGES.value == "messages"
        assert Domain.NOTES.value == "notes"
        assert Domain.EVENTS.value == "events"
        assert Domain.TASKS.value == "tasks"

    def test_domain_is_string_enum(self) -> None:
        """Domain members are string-like for metadata storage."""
        from context_library.storage.vector_store import Domain

        assert isinstance(Domain.MESSAGES, str)
        assert isinstance(Domain.NOTES, str)
