"""Tests for the vector store."""

import pytest
from pydantic import ValidationError

from context_library.storage.validators import (
    EMBEDDING_DIM,
    validate_embedding_dimension,
    validate_iso8601_timestamp,
)
from context_library.storage.models import Domain
from context_library.storage.vector_store import ChunkVector


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

    def test_nan_value_raises_error(self) -> None:
        """Embedding with NaN values raises ValueError."""
        nan_embedding = [0.1] * (EMBEDDING_DIM - 1) + [float("nan")]
        with pytest.raises(ValueError) as exc_info:
            validate_embedding_dimension(nan_embedding)
        error_msg = str(exc_info.value)
        assert f"index {EMBEDDING_DIM - 1}" in error_msg
        assert "finite number" in error_msg
        assert "corrupt vector calculations" in error_msg

    def test_inf_value_raises_error(self) -> None:
        """Embedding with infinity values raises ValueError."""
        inf_embedding = [0.1] * (EMBEDDING_DIM - 1) + [float("inf")]
        with pytest.raises(ValueError) as exc_info:
            validate_embedding_dimension(inf_embedding)
        error_msg = str(exc_info.value)
        assert f"index {EMBEDDING_DIM - 1}" in error_msg
        assert "finite number" in error_msg

    def test_negative_inf_value_raises_error(self) -> None:
        """Embedding with negative infinity values raises ValueError."""
        neg_inf_embedding = [0.1] * (EMBEDDING_DIM - 1) + [float("-inf")]
        with pytest.raises(ValueError) as exc_info:
            validate_embedding_dimension(neg_inf_embedding)
        error_msg = str(exc_info.value)
        assert f"index {EMBEDDING_DIM - 1}" in error_msg
        assert "finite number" in error_msg


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


class TestValidateISO8601Timestamp:
    """Tests for ISO 8601 timestamp validation."""

    def test_valid_iso8601_datetime(self) -> None:
        """Valid ISO 8601 datetime strings pass without raising."""
        valid_timestamps = [
            "2025-03-02T10:30:45",
            "2025-03-02T10:30:45.123456",
            "2025-03-02T10:30:45Z",
            "2025-03-02T10:30:45+00:00",
            "2025-03-02T10:30:45-05:00",
            "2025-03-02T10:30:45.123456Z",
            "2025-03-02T10:30:45.123456+00:00",
        ]
        for timestamp in valid_timestamps:
            # Should not raise
            validate_iso8601_timestamp(timestamp)

    def test_valid_iso8601_date_only(self) -> None:
        """Valid ISO 8601 date-only strings pass without raising."""
        # fromisoformat accepts date-only format
        validate_iso8601_timestamp("2025-03-02")

    def test_valid_iso8601_with_space_separator(self) -> None:
        """Valid ISO 8601 datetime with space separator passes without raising."""
        # fromisoformat accepts space as separator (alternative format)
        validate_iso8601_timestamp("2025-03-02 10:30:45")

    def test_invalid_timestamp_format_raises_error(self) -> None:
        """Invalid timestamp format raises ValueError with helpful message."""
        invalid_timestamps = [
            "03/02/2025",
            "2025-3-2",
            "not a timestamp",
            "03-02-2025T10:30:45",
        ]
        for timestamp in invalid_timestamps:
            with pytest.raises(ValueError) as exc_info:
                validate_iso8601_timestamp(timestamp)
            error_msg = str(exc_info.value)
            assert "not a valid ISO 8601 format" in error_msg
            assert timestamp in error_msg

    def test_non_string_timestamp_raises_type_error(self) -> None:
        """Non-string timestamp raises TypeError."""
        with pytest.raises(TypeError) as exc_info:
            validate_iso8601_timestamp(123456789)  # type: ignore[arg-type]
        error_msg = str(exc_info.value)
        assert "must be a string" in error_msg
        assert "int" in error_msg

    def test_none_timestamp_raises_type_error(self) -> None:
        """None timestamp raises TypeError."""
        with pytest.raises(TypeError) as exc_info:
            validate_iso8601_timestamp(None)  # type: ignore[arg-type]
        error_msg = str(exc_info.value)
        assert "must be a string" in error_msg
        assert "NoneType" in error_msg


class TestChunkVectorConstruction:
    """Tests for ChunkVector model instantiation and field validation."""

    def test_valid_chunk_vector_construction(self) -> None:
        """ChunkVector with all valid fields constructs successfully."""
        chunk_vector = ChunkVector(
            chunk_hash="abc123def456",
            content="Sample chunk content",
            vector=[0.1] * EMBEDDING_DIM,
            domain=Domain.NOTES,
            source_id="source_1",
            source_version=1,
            created_at="2025-03-02T10:30:45Z",
        )
        assert chunk_vector.chunk_hash == "abc123def456"
        assert chunk_vector.content == "Sample chunk content"
        assert len(chunk_vector.vector) == EMBEDDING_DIM
        assert chunk_vector.domain == Domain.NOTES
        assert chunk_vector.source_id == "source_1"
        assert chunk_vector.source_version == 1
        assert chunk_vector.created_at == "2025-03-02T10:30:45Z"

    def test_chunk_vector_with_all_domains(self) -> None:
        """ChunkVector accepts all Domain enum values."""
        for domain in Domain:
            chunk_vector = ChunkVector(
                chunk_hash=f"hash_{domain.value}",
                content="test content",
                vector=[0.1] * EMBEDDING_DIM,
                domain=domain,
                source_id="source_1",
                source_version=1,
                created_at="2025-03-02T10:30:45Z",
            )
            assert chunk_vector.domain == domain

    def test_chunk_vector_domain_string_coercion(self) -> None:
        """ChunkVector accepts Domain enum string values and coerces them."""
        chunk_vector = ChunkVector(
            chunk_hash="abc123",
            content="test content",
            vector=[0.1] * EMBEDDING_DIM,
            domain="notes",  # type: ignore[arg-type]  # string value
            source_id="source_1",
            source_version=1,
            created_at="2025-03-02T10:30:45Z",
        )
        assert chunk_vector.domain == Domain.NOTES

    def test_chunk_vector_rejects_invalid_domain(self) -> None:
        """ChunkVector rejects invalid domain values."""
        with pytest.raises(ValidationError):
            ChunkVector(
                chunk_hash="abc123",
                content="test content",
                vector=[0.1] * EMBEDDING_DIM,
                domain="invalid_domain",  # type: ignore[arg-type]
                source_id="source_1",
                source_version=1,
                created_at="2025-03-02T10:30:45Z",
            )

    def test_chunk_vector_vector_dimension_validation(self) -> None:
        """ChunkVector rejects vectors with incorrect dimension."""
        with pytest.raises(ValidationError) as exc_info:
            ChunkVector(
                chunk_hash="abc123",
                content="test content",
                vector=[0.1] * (EMBEDDING_DIM - 1),  # too short
                domain=Domain.NOTES,
                source_id="source_1",
                source_version=1,
                created_at="2025-03-02T10:30:45Z",
            )
        assert "Embedding dimension mismatch" in str(exc_info.value)

    def test_chunk_vector_rejects_nan_values_in_vector(self) -> None:
        """ChunkVector rejects vectors containing NaN values."""
        nan_vector = [0.1] * (EMBEDDING_DIM - 1) + [float("nan")]
        with pytest.raises(ValidationError) as exc_info:
            ChunkVector(
                chunk_hash="abc123",
                content="test content",
                vector=nan_vector,
                domain=Domain.NOTES,
                source_id="source_1",
                source_version=1,
                created_at="2025-03-02T10:30:45Z",
            )
        error_msg = str(exc_info.value)
        assert "finite number" in error_msg
        assert "corrupt vector calculations" in error_msg

    def test_chunk_vector_rejects_positive_infinity_in_vector(self) -> None:
        """ChunkVector rejects vectors containing positive infinity values."""
        inf_vector = [0.1] * (EMBEDDING_DIM - 1) + [float("inf")]
        with pytest.raises(ValidationError) as exc_info:
            ChunkVector(
                chunk_hash="abc123",
                content="test content",
                vector=inf_vector,
                domain=Domain.NOTES,
                source_id="source_1",
                source_version=1,
                created_at="2025-03-02T10:30:45Z",
            )
        assert "finite number" in str(exc_info.value)

    def test_chunk_vector_rejects_negative_infinity_in_vector(self) -> None:
        """ChunkVector rejects vectors containing negative infinity values."""
        neg_inf_vector = [0.1] * (EMBEDDING_DIM - 1) + [float("-inf")]
        with pytest.raises(ValidationError) as exc_info:
            ChunkVector(
                chunk_hash="abc123",
                content="test content",
                vector=neg_inf_vector,
                domain=Domain.NOTES,
                source_id="source_1",
                source_version=1,
                created_at="2025-03-02T10:30:45Z",
            )
        assert "finite number" in str(exc_info.value)

    def test_chunk_vector_created_at_field_validation(self) -> None:
        """ChunkVector validates created_at field with ISO 8601 format."""
        with pytest.raises(ValidationError) as exc_info:
            ChunkVector(
                chunk_hash="abc123",
                content="test content",
                vector=[0.1] * EMBEDDING_DIM,
                domain=Domain.NOTES,
                source_id="source_1",
                source_version=1,
                created_at="03/02/2025",  # invalid format
            )
        assert "not a valid ISO 8601 format" in str(exc_info.value)

    def test_chunk_vector_accepts_various_iso8601_formats(self) -> None:
        """ChunkVector accepts various valid ISO 8601 timestamp formats."""
        valid_timestamps = [
            "2025-03-02T10:30:45",
            "2025-03-02T10:30:45.123456",
            "2025-03-02T10:30:45Z",
            "2025-03-02T10:30:45+00:00",
            "2025-03-02T10:30:45-05:00",
        ]
        for timestamp in valid_timestamps:
            chunk_vector = ChunkVector(
                chunk_hash="abc123",
                content="test content",
                vector=[0.1] * EMBEDDING_DIM,
                domain=Domain.NOTES,
                source_id="source_1",
                source_version=1,
                created_at=timestamp,
            )
            assert chunk_vector.created_at == timestamp

    def test_chunk_vector_requires_all_fields(self) -> None:
        """ChunkVector requires all fields to be provided."""
        with pytest.raises(ValidationError):
            ChunkVector(  # type: ignore[call-arg]
                chunk_hash="abc123",
                content="test content",
                vector=[0.1] * EMBEDDING_DIM,
                domain=Domain.NOTES,
                source_id="source_1",
                # missing source_version
                created_at="2025-03-02T10:30:45Z",
            )

    def test_chunk_vector_accepts_integer_source_version(self) -> None:
        """ChunkVector accepts integer source_version."""
        chunk_vector = ChunkVector(
            chunk_hash="abc123",
            content="test content",
            vector=[0.1] * EMBEDDING_DIM,
            domain=Domain.NOTES,
            source_id="source_1",
            source_version=5,
            created_at="2025-03-02T10:30:45Z",
        )
        assert chunk_vector.source_version == 5

    def test_chunk_vector_all_fields_accessible(self) -> None:
        """All ChunkVector fields are accessible after construction."""
        chunk_vector = ChunkVector(
            chunk_hash="test_hash",
            content="test content",
            vector=[0.2] * EMBEDDING_DIM,
            domain=Domain.EVENTS,
            source_id="test_source",
            source_version=3,
            created_at="2025-03-02T15:45:00Z",
        )
        assert chunk_vector.chunk_hash == "test_hash"
        assert chunk_vector.content == "test content"
        assert chunk_vector.domain == Domain.EVENTS
        assert chunk_vector.source_id == "test_source"
        assert chunk_vector.source_version == 3
        assert chunk_vector.created_at == "2025-03-02T15:45:00Z"
