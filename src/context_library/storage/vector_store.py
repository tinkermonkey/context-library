"""LanceDB-backed vector index; derived and fully rebuildable from the document store."""

from collections.abc import Sequence
from pathlib import Path

from lancedb.pydantic import (  # type: ignore[import-untyped]
    LanceModel,
    Vector,
)
from pydantic import ConfigDict, field_validator

from context_library.core.embedder import Embedder
from context_library.storage.models import Domain
from context_library.storage.validators import (
    validate_embedding_dimension,
    validate_iso8601_timestamp,
)

VECTOR_DIR = Path.home() / ".context-library" / "vectors"


def get_embedding_dimension(embedder: Embedder) -> int:
    """Get the embedding dimension from the embedder.

    Args:
        embedder: Embedder instance to query for dimension.

    Returns:
        The embedding dimension as an integer.
    """
    return embedder.dimension


def make_chunk_vector_schema(embedding_dim: int) -> type[LanceModel]:
    """Factory function to create a ChunkVector schema with the specified embedding dimension.

    This factory allows the vector dimension to be driven by the configured embedding model,
    not hardcoded as a compile-time constant. Each configured embedder dimension gets its own
    schema class.

    Args:
        embedding_dim: The embedding dimension to use for the Vector field.

    Returns:
        A LanceModel class with the specified vector dimension.
    """
    class ChunkVector(LanceModel):
        """Schema for the LanceDB chunk_vectors table.

        chunk_hash is the join key to the SQLite chunks table.
        LanceDB is derived and disposable; it can be fully rebuilt from SQLite.
        Immutable by design: frozen=True enforces that validators cannot be bypassed by assignment.
        """

        model_config = ConfigDict(frozen=True)

        chunk_hash: str              # join key to SQLite chunks table
        content: str                 # denormalized for reranker access without SQLite lookup
        vector: Vector(embedding_dim)  # type: ignore[valid-type]  # embedding vector with model-driven dimension
        domain: Domain               # supports filtered vector search by domain
        source_id: str               # supports filtered vector search by source
        source_version: int          # supports filtered vector search by version
        created_at: str              # ISO 8601 timestamp

        @field_validator("vector", mode="before")
        @classmethod
        def validate_vector(cls, value: Sequence[float]) -> Sequence[float]:
            """Validate that vector has correct dimension and no NaN/infinity values.

            NaN and infinity corrupt similarity calculations in LanceDB.
            """
            validate_embedding_dimension(value, embedding_dim)
            return value

        @field_validator("created_at")
        @classmethod
        def validate_created_at(cls, value: str) -> str:
            """Validate that created_at is a valid ISO 8601 timestamp."""
            validate_iso8601_timestamp(value)
            return value

    return ChunkVector
