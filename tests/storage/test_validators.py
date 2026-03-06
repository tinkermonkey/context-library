"""Tests for validation functions in the storage module.

Covers:
- Embedding dimension validation (correct dimension, NaN, infinity checks)
- ISO 8601 timestamp validation (format compliance)
"""


import pytest

from context_library.storage.validators import (
    EMBEDDING_DIM,
    validate_embedding_dimension,
    validate_iso8601_timestamp,
)


class TestValidateEmbeddingDimension:
    """Tests for validate_embedding_dimension()."""

    def test_valid_embedding_dimension(self) -> None:
        """Test that valid embedding passes validation."""
        valid_embedding = [0.1] * EMBEDDING_DIM
        # Should not raise
        validate_embedding_dimension(valid_embedding)

    def test_valid_embedding_with_custom_dimension(self) -> None:
        """Test validation with custom expected dimension."""
        custom_dim = 768
        valid_embedding = [0.5] * custom_dim
        # Should not raise
        validate_embedding_dimension(valid_embedding, expected_dim=custom_dim)

    def test_embedding_dimension_too_small(self) -> None:
        """Test that embedding with incorrect (too small) dimension raises ValueError."""
        small_embedding = [0.1] * (EMBEDDING_DIM - 1)
        with pytest.raises(ValueError, match="Embedding dimension mismatch"):
            validate_embedding_dimension(small_embedding)

    def test_embedding_dimension_too_large(self) -> None:
        """Test that embedding with incorrect (too large) dimension raises ValueError."""
        large_embedding = [0.1] * (EMBEDDING_DIM + 1)
        with pytest.raises(ValueError, match="Embedding dimension mismatch"):
            validate_embedding_dimension(large_embedding)

    def test_embedding_dimension_mismatch_message(self) -> None:
        """Test that dimension mismatch error includes expected and actual values."""
        small_embedding = [0.1] * 100
        with pytest.raises(ValueError) as exc_info:
            validate_embedding_dimension(small_embedding)
        error_msg = str(exc_info.value)
        assert "expected" in error_msg.lower()
        assert "100" in error_msg

    def test_embedding_with_nan_value(self) -> None:
        """Test that embedding containing NaN raises ValueError."""
        embedding_with_nan = [0.1] * EMBEDDING_DIM
        embedding_with_nan[EMBEDDING_DIM // 2] = float("nan")
        with pytest.raises(ValueError, match="non-finite value"):
            validate_embedding_dimension(embedding_with_nan)

    def test_embedding_with_nan_at_start(self) -> None:
        """Test that embedding with NaN at beginning raises ValueError."""
        embedding_with_nan = [float("nan")] + [0.1] * (EMBEDDING_DIM - 1)
        with pytest.raises(ValueError) as exc_info:
            validate_embedding_dimension(embedding_with_nan)
        error_msg = str(exc_info.value)
        assert "index 0" in error_msg

    def test_embedding_with_nan_at_end(self) -> None:
        """Test that embedding with NaN at end raises ValueError."""
        embedding_with_nan = [0.1] * (EMBEDDING_DIM - 1) + [float("nan")]
        with pytest.raises(ValueError) as exc_info:
            validate_embedding_dimension(embedding_with_nan)
        error_msg = str(exc_info.value)
        assert f"index {EMBEDDING_DIM - 1}" in error_msg

    def test_embedding_with_positive_infinity(self) -> None:
        """Test that embedding containing positive infinity raises ValueError."""
        embedding_with_inf = [0.1] * EMBEDDING_DIM
        embedding_with_inf[10] = float("inf")
        with pytest.raises(ValueError, match="non-finite value"):
            validate_embedding_dimension(embedding_with_inf)

    def test_embedding_with_negative_infinity(self) -> None:
        """Test that embedding containing negative infinity raises ValueError."""
        embedding_with_ninf = [0.1] * EMBEDDING_DIM
        embedding_with_ninf[20] = float("-inf")
        with pytest.raises(ValueError, match="non-finite value"):
            validate_embedding_dimension(embedding_with_ninf)

    def test_embedding_with_all_zeros(self) -> None:
        """Test that all-zero embedding (valid values) passes validation."""
        zero_embedding = [0.0] * EMBEDDING_DIM
        # Should not raise
        validate_embedding_dimension(zero_embedding)

    def test_embedding_with_large_finite_values(self) -> None:
        """Test that large but finite values pass validation."""
        large_embedding = [1e10] * EMBEDDING_DIM
        # Should not raise
        validate_embedding_dimension(large_embedding)

    def test_embedding_with_small_finite_values(self) -> None:
        """Test that very small but finite values pass validation."""
        small_embedding = [1e-10] * EMBEDDING_DIM
        # Should not raise
        validate_embedding_dimension(small_embedding)

    def test_embedding_with_mixed_finite_values(self) -> None:
        """Test that embedding with mixed finite values passes validation."""
        embedding = [0.5 * i for i in range(EMBEDDING_DIM)]
        # Should not raise
        validate_embedding_dimension(embedding)

    def test_empty_embedding_raises_error(self) -> None:
        """Test that empty embedding raises dimension mismatch error."""
        empty_embedding = []
        with pytest.raises(ValueError, match="Embedding dimension mismatch"):
            validate_embedding_dimension(empty_embedding)

    def test_nan_error_message_includes_index(self) -> None:
        """Test that NaN error message includes the problematic index."""
        embedding_with_nan = [0.1] * (EMBEDDING_DIM // 2) + [float("nan")] + [0.1] * (EMBEDDING_DIM // 2 - 1)
        with pytest.raises(ValueError) as exc_info:
            validate_embedding_dimension(embedding_with_nan)
        error_msg = str(exc_info.value)
        assert "index" in error_msg
        assert "nan" in error_msg.lower()


class TestValidateISO8601Timestamp:
    """Tests for validate_iso8601_timestamp()."""

    def test_valid_iso8601_with_z_timezone(self) -> None:
        """Test valid ISO 8601 timestamp with Z (UTC) timezone."""
        # Should not raise
        validate_iso8601_timestamp("2025-03-02T10:30:45Z")

    def test_valid_iso8601_with_positive_offset(self) -> None:
        """Test valid ISO 8601 timestamp with positive timezone offset."""
        # Should not raise
        validate_iso8601_timestamp("2025-03-02T10:30:45+02:00")

    def test_valid_iso8601_with_negative_offset(self) -> None:
        """Test valid ISO 8601 timestamp with negative timezone offset."""
        # Should not raise
        validate_iso8601_timestamp("2025-03-02T10:30:45-05:00")

    def test_valid_iso8601_with_microseconds_and_z(self) -> None:
        """Test valid ISO 8601 timestamp with microseconds and Z timezone."""
        # Should not raise
        validate_iso8601_timestamp("2025-03-02T10:30:45.123456Z")

    def test_valid_iso8601_with_microseconds_and_offset(self) -> None:
        """Test valid ISO 8601 timestamp with microseconds and offset."""
        # Should not raise
        validate_iso8601_timestamp("2025-03-02T10:30:45.999999+00:00")

    def test_valid_iso8601_with_single_digit_microseconds(self) -> None:
        """Test valid ISO 8601 with single-digit microseconds."""
        # Should not raise
        validate_iso8601_timestamp("2025-03-02T10:30:45.1Z")

    def test_valid_iso8601_with_two_digit_microseconds(self) -> None:
        """Test valid ISO 8601 with two-digit microseconds."""
        # Should not raise
        validate_iso8601_timestamp("2025-03-02T10:30:45.12Z")

    def test_valid_iso8601_with_three_digit_microseconds(self) -> None:
        """Test valid ISO 8601 with three-digit microseconds (milliseconds)."""
        # Should not raise
        validate_iso8601_timestamp("2025-03-02T10:30:45.123Z")

    def test_invalid_iso8601_missing_date(self) -> None:
        """Test that timestamp missing date raises ValueError."""
        with pytest.raises(ValueError, match="not in valid ISO 8601 format"):
            validate_iso8601_timestamp("10:30:45Z")

    def test_invalid_iso8601_missing_time(self) -> None:
        """Test that timestamp missing time raises ValueError."""
        with pytest.raises(ValueError, match="not in valid ISO 8601 format"):
            validate_iso8601_timestamp("2025-03-02")

    def test_invalid_iso8601_wrong_separator(self) -> None:
        """Test that timestamp with wrong date-time separator raises ValueError."""
        # Using space instead of T
        with pytest.raises(ValueError, match="not in valid ISO 8601 format"):
            validate_iso8601_timestamp("2025-03-02 10:30:45Z")

    def test_invalid_iso8601_missing_timezone(self) -> None:
        """Test that timestamp missing timezone raises ValueError."""
        with pytest.raises(ValueError, match="not in valid ISO 8601 format"):
            validate_iso8601_timestamp("2025-03-02T10:30:45")

    def test_invalid_iso8601_missing_seconds(self) -> None:
        """Test that timestamp missing seconds raises ValueError."""
        with pytest.raises(ValueError, match="not in valid ISO 8601 format"):
            validate_iso8601_timestamp("2025-03-02T10:30Z")

    def test_invalid_iso8601_invalid_offset_format(self) -> None:
        """Test that invalid offset format raises ValueError."""
        # Missing colon in offset
        with pytest.raises(ValueError, match="not in valid ISO 8601 format"):
            validate_iso8601_timestamp("2025-03-02T10:30:45+0200")

    def test_invalid_iso8601_single_digit_month(self) -> None:
        """Test that single-digit month raises ValueError."""
        with pytest.raises(ValueError, match="not in valid ISO 8601 format"):
            validate_iso8601_timestamp("2025-3-02T10:30:45Z")

    def test_invalid_iso8601_single_digit_day(self) -> None:
        """Test that single-digit day raises ValueError."""
        with pytest.raises(ValueError, match="not in valid ISO 8601 format"):
            validate_iso8601_timestamp("2025-03-2T10:30:45Z")

    def test_invalid_iso8601_single_digit_hour(self) -> None:
        """Test that single-digit hour raises ValueError."""
        with pytest.raises(ValueError, match="not in valid ISO 8601 format"):
            validate_iso8601_timestamp("2025-03-02T9:30:45Z")

    def test_invalid_iso8601_single_digit_minute(self) -> None:
        """Test that single-digit minute raises ValueError."""
        with pytest.raises(ValueError, match="not in valid ISO 8601 format"):
            validate_iso8601_timestamp("2025-03-02T10:3:45Z")

    def test_invalid_iso8601_single_digit_second(self) -> None:
        """Test that single-digit second raises ValueError."""
        with pytest.raises(ValueError, match="not in valid ISO 8601 format"):
            validate_iso8601_timestamp("2025-03-02T10:30:5Z")

    def test_iso8601_error_message_format(self) -> None:
        """Test that error message includes format hint."""
        with pytest.raises(ValueError) as exc_info:
            validate_iso8601_timestamp("invalid-timestamp")
        error_msg = str(exc_info.value)
        assert "ISO 8601" in error_msg
        assert "invalid-timestamp" in error_msg

    def test_valid_midnight_timestamp(self) -> None:
        """Test valid timestamp for midnight."""
        # Should not raise
        validate_iso8601_timestamp("2025-03-02T00:00:00Z")

    def test_valid_end_of_day_timestamp(self) -> None:
        """Test valid timestamp for 23:59:59."""
        # Should not raise
        validate_iso8601_timestamp("2025-03-02T23:59:59Z")

    def test_valid_leap_year_timestamp(self) -> None:
        """Test valid timestamp for leap year date."""
        # Should not raise
        validate_iso8601_timestamp("2024-02-29T12:00:00Z")
