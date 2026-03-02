"""Validation functions and constants for vector store models."""

import re
from collections.abc import Sequence
from math import isfinite

# Standard embedding dimension for sentence-transformers models
# Using 384 as default (common for lightweight models like all-MiniLM-L6-v2)
EMBEDDING_DIM = 384


def validate_embedding_dimension(
    value: Sequence[float], expected_dim: int = EMBEDDING_DIM
) -> None:
    """Validate that embedding vector has correct dimension and no NaN/infinity values.

    Supports runtime flexibility for different embedding models by accepting an optional
    expected_dim parameter. Defaults to EMBEDDING_DIM (384) for the standard model.

    Args:
        value: The embedding vector to validate
        expected_dim: Expected embedding dimension (defaults to EMBEDDING_DIM = 384)

    Raises:
        ValueError: If dimension is incorrect or contains NaN/infinity values
    """
    if len(value) != expected_dim:
        raise ValueError(
            f"Embedding dimension mismatch: expected {expected_dim}, got {len(value)}"
        )

    for i, val in enumerate(value):
        if not isfinite(val):
            raise ValueError(
                f"Embedding contains non-finite value at index {i}: {val}"
            )


def validate_iso8601_timestamp(value: str) -> None:
    """Validate that timestamp is in ISO 8601 format.

    Args:
        value: The timestamp string to validate

    Raises:
        ValueError: If timestamp is not in valid ISO 8601 format
    """
    # ISO 8601 pattern: YYYY-MM-DDTHH:MM:SS[.ffffff][Z|±HH:MM]
    iso8601_pattern = r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?(?:Z|[+-]\d{2}:\d{2})$"

    if not re.match(iso8601_pattern, value):
        raise ValueError(
            f"Timestamp '{value}' is not in valid ISO 8601 format. "
            "Expected format: YYYY-MM-DDTHH:MM:SS[.ffffff][Z|±HH:MM]"
        )
