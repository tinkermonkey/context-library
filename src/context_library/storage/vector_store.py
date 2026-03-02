"""LanceDB-backed vector index; derived and fully rebuildable from the document store."""

from pathlib import Path

from lancedb.pydantic import (  # type: ignore[import-untyped]
    LanceModel,
    Vector,
)
from pydantic import field_validator

from context_library.storage.models import Domain
from context_library.storage.validators import (
    EMBEDDING_DIM,
    validate_embedding_dimension,
    validate_iso8601_timestamp,
)

VECTOR_DIR = Path.home() / ".context-library" / "vectors"


class ChunkVector(LanceModel):
    """Schema for the LanceDB chunk_vectors table.

    chunk_hash is the join key to the SQLite chunks table.
    LanceDB is derived and disposable; it can be fully rebuilt from SQLite.
    """

    chunk_hash: str              # join key to SQLite chunks table
    content: str                 # denormalized for reranker access without SQLite lookup
    vector: Vector(EMBEDDING_DIM)  # type: ignore[valid-type]  # fixed-size embedding vector (float32 optimized storage)
    domain: Domain               # supports filtered vector search by domain
    source_id: str               # supports filtered vector search by source
    source_version: int          # supports filtered vector search by version
    created_at: str              # ISO 8601 timestamp

    @field_validator("vector", mode="before")
    @classmethod
    def validate_vector(cls, value: list[float]) -> list[float]:
        """Validate that vector has correct dimension and no NaN/infinity values.

        NaN and infinity corrupt similarity calculations in LanceDB.
        """
        validate_embedding_dimension(value)
        return value

    @field_validator("created_at")
    @classmethod
    def validate_created_at(cls, value: str) -> str:
        """Validate that created_at is a valid ISO 8601 timestamp."""
        validate_iso8601_timestamp(value)
        return value
