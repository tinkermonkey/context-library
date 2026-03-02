"""Validation utilities for embeddings and other data structures.

These validators are pure Python and have no external dependencies,
allowing them to be tested and used independently.
"""

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

    # Validate that all elements are numeric
    for i, element in enumerate(embedding):
        if not isinstance(element, (int, float)):
            raise ValueError(
                f"Embedding element at index {i} is {type(element).__name__}, "
                f"expected numeric type (int or float). All embedding elements must be numeric."
            )
