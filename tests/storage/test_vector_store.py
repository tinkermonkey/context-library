"""Tests for the vector store."""

import pytest

# Use importorskip to gracefully handle missing lancedb dependency
pytest.importorskip("lancedb", minversion=None)

from context_library.storage.vector_store import (
    EMBEDDING_DIM,
    validate_embedding_dimension,
)
from context_library.storage.models import Domain


class TestValidateEmbeddingDimension:
    """Tests for embedding dimension validation."""

    def test_valid_dimension(self) -> None:
        """Valid embedding dimension passes without raising."""
        valid_embedding = [0.1] * EMBEDDING_DIM
        # Should not raise
        validate_embedding_dimension(valid_embedding)

    def test_invalid_dimension_too_short(self) -> None:
        """Embedding shorter than expected dimension raises ValueError."""
        short_embedding = [0.1] * (EMBEDDING_DIM - 1)
        with pytest.raises(ValueError) as exc_info:
            validate_embedding_dimension(short_embedding)
        assert "Embedding dimension mismatch" in str(exc_info.value)
        assert f"expected {EMBEDDING_DIM}" in str(exc_info.value)

    def test_invalid_dimension_too_long(self) -> None:
        """Embedding longer than expected dimension raises ValueError."""
        long_embedding = [0.1] * (EMBEDDING_DIM + 1)
        with pytest.raises(ValueError) as exc_info:
            validate_embedding_dimension(long_embedding)
        assert "Embedding dimension mismatch" in str(exc_info.value)
        assert f"expected {EMBEDDING_DIM}" in str(exc_info.value)

    def test_error_message_content(self) -> None:
        """Error message includes helpful guidance."""
        wrong_embedding = [0.5] * 100
        with pytest.raises(ValueError) as exc_info:
            validate_embedding_dimension(wrong_embedding)
        error_msg = str(exc_info.value)
        assert "embedding model configuration" in error_msg
        assert "EMBEDDING_DIM" in error_msg

    def test_none_input_raises_clear_error(self) -> None:
        """None input produces clear ValueError, not TypeError."""
        with pytest.raises(ValueError) as exc_info:
            validate_embedding_dimension(None)  # type: ignore[arg-type]
        error_msg = str(exc_info.value)
        assert "cannot be None" in error_msg
        assert "Expected a list" in error_msg

    def test_non_list_input_raises_type_error(self) -> None:
        """Non-list input raises TypeError with helpful message."""
        with pytest.raises(TypeError) as exc_info:
            validate_embedding_dimension("not a list")  # type: ignore[arg-type]
        error_msg = str(exc_info.value)
        assert "must be a list or tuple" in error_msg
        assert "str" in error_msg

    def test_non_numeric_elements_raise_error(self) -> None:
        """Embedding with non-numeric elements raises ValueError."""
        # List with strings instead of floats
        bad_embedding = ["0.1"] * EMBEDDING_DIM
        with pytest.raises(ValueError) as exc_info:
            validate_embedding_dimension(bad_embedding)  # type: ignore[arg-type]
        error_msg = str(exc_info.value)
        assert "index 0" in error_msg
        assert "str" in error_msg
        assert "numeric type" in error_msg

    def test_mixed_numeric_and_non_numeric_elements_raise_error(self) -> None:
        """Embedding with mixed numeric and non-numeric elements raises ValueError."""
        mixed_embedding = [0.1] * (EMBEDDING_DIM - 1) + ["not_a_number"]
        with pytest.raises(ValueError) as exc_info:
            validate_embedding_dimension(mixed_embedding)  # type: ignore[arg-type]
        error_msg = str(exc_info.value)
        assert f"index {EMBEDDING_DIM - 1}" in error_msg
        assert "str" in error_msg

    def test_tuple_input_is_accepted(self) -> None:
        """Tuple input is accepted as valid (list-like)."""
        tuple_embedding = tuple([0.1] * EMBEDDING_DIM)
        # Should not raise
        validate_embedding_dimension(tuple_embedding)  # type: ignore[arg-type]


class TestDomain:
    """Tests for the Domain enum."""

    def test_domain_members_exist(self) -> None:
        """All expected domain members are defined."""
        assert hasattr(Domain, "MESSAGES")
        assert hasattr(Domain, "NOTES")
        assert hasattr(Domain, "EVENTS")
        assert hasattr(Domain, "TASKS")

    def test_domain_values(self) -> None:
        """Domain enum values are correct."""
        assert Domain.MESSAGES.value == "messages"
        assert Domain.NOTES.value == "notes"
        assert Domain.EVENTS.value == "events"
        assert Domain.TASKS.value == "tasks"

    def test_domain_is_string_enum(self) -> None:
        """Domain members are string-like for metadata storage."""
        assert isinstance(Domain.MESSAGES, str)
        assert isinstance(Domain.NOTES, str)
