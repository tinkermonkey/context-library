"""LanceDB-backed vector index; derived and fully rebuildable from the document store."""

from pathlib import Path

from lancedb.pydantic import (  # type: ignore[import-untyped]
    LanceModel,
    Vector,
)

from context_library.storage.models import Domain

VECTOR_DIR = Path.home() / ".context-library" / "vectors"
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


class ChunkVector(LanceModel):
    """Schema for the LanceDB chunk_vectors table.

    chunk_hash is the join key to the SQLite chunks table.
    LanceDB is derived and disposable; it can be fully rebuilt from SQLite.
    """

    chunk_hash: str              # join key to SQLite chunks table
    content: str                 # denormalized for reranker access without SQLite lookup
    vector: Vector(EMBEDDING_DIM)  # fixed-size embedding vector (float32 optimized storage)
    domain: Domain               # supports filtered vector search by domain
    source_id: str               # supports filtered vector search by source
    source_version: int          # supports filtered vector search by version
    created_at: str              # ISO 8601 timestamp
