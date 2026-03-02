"""Validation utilities for embeddings and other data structures.

These validators are pure Python and have no external dependencies,
allowing them to be tested and used independently.
"""

import math
from datetime import datetime

EMBEDDING_DIM = 384  # all-MiniLM-L6-v2; change here when swapping embedding model


def validate_embedding_dimension(embedding: list[float]) -> None:
    """Validate that an embedding has the expected dimension and element types.

    Args:
        embedding: The embedding vector to validate.

    Raises:
        ValueError: If embedding is None, dimension does not match EMBEDDING_DIM,
                   or elements are not numeric.
        TypeError: If embedding is not a list-like object.
    """
    if embedding is None:
        raise ValueError(
            f"Embedding cannot be None. Expected a list of {EMBEDDING_DIM} floats."
        )

    if not isinstance(embedding, (list, tuple)):
        raise TypeError(
            f"Embedding must be a list or tuple of floats, got {type(embedding).__name__}."
        )

    if len(embedding) != EMBEDDING_DIM:
        raise ValueError(
            f"Embedding dimension mismatch: expected {EMBEDDING_DIM}, "
            f"got {len(embedding)}. Verify the embedding model configuration matches EMBEDDING_DIM."
        )

    # Validate that all elements are numeric and finite
    for i, element in enumerate(embedding):
        if not isinstance(element, (int, float)):
            raise ValueError(
                f"Embedding element at index {i} is {type(element).__name__}, "
                f"expected numeric type (int or float). All embedding elements must be numeric."
            )

        if not math.isfinite(element):
            raise ValueError(
                f"Embedding element at index {i} is {element}, "
                f"expected finite number. NaN and infinity values corrupt vector calculations."
            )


def validate_iso8601_timestamp(timestamp: str) -> None:
    """Validate that a timestamp string is in ISO 8601 format.

    Args:
        timestamp: The timestamp string to validate.

    Raises:
        ValueError: If timestamp is not a valid ISO 8601 string.
        TypeError: If timestamp is not a string.
    """
    if not isinstance(timestamp, str):
        raise TypeError(
            f"Timestamp must be a string, got {type(timestamp).__name__}."
        )

    try:
        datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
    except ValueError:
        raise ValueError(
            f"Timestamp '{timestamp}' is not a valid ISO 8601 format. "
            f"Expected formats like '2025-03-02T10:30:45' or '2025-03-02T10:30:45Z'."
        )
