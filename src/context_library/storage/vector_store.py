"""LanceDB-backed vector index; derived and fully rebuildable from the document store."""

from pathlib import Path
from typing import Type  # noqa: F401 - required for Vector type annotation

import pyarrow as pa  # noqa: F401 - required for Vector type annotation
from lancedb.pydantic import (  # type: ignore[import-untyped]
    FixedSizeListMixin,  # noqa: F401 - required for Vector type annotation
    LanceModel,
    Vector,
)

from context_library.storage.models import Domain

VECTOR_DIR = Path.home() / ".context-library" / "vectors"
EMBEDDING_DIM = 384  # all-MiniLM-L6-v2; change here when swapping embedding model


def validate_embedding_dimension(embedding: list[float]) -> None:
    """Validate that an embedding has the expected dimension.

    Args:
        embedding: The embedding vector to validate.

    Raises:
        ValueError: If embedding dimension does not match EMBEDDING_DIM.
    """
    if len(embedding) != EMBEDDING_DIM:
        raise ValueError(
            f"Embedding dimension mismatch: expected {EMBEDDING_DIM}, "
            f"got {len(embedding)}. Verify the embedding model configuration matches EMBEDDING_DIM."
        )


class ChunkVector(LanceModel):
    """Schema for the LanceDB chunk_vectors table.

    chunk_hash is the join key to the SQLite chunks table.
    LanceDB is derived and disposable; it can be fully rebuilt from SQLite.
    """

    chunk_hash: str       # join key to SQLite chunks table
    content: str          # denormalized for reranker access without SQLite lookup
    vector: Vector[EMBEDDING_DIM]
    domain: Domain        # supports filtered vector search by domain
    source_id: str        # supports filtered vector search by source
    source_version: int   # supports filtered vector search by version
    created_at: str       # ISO 8601 timestamp
