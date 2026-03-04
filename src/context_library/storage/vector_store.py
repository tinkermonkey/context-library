"""LanceDB-backed vector index; derived and fully rebuildable from the document store."""

from collections.abc import Sequence
from pathlib import Path

from lancedb.pydantic import (  # type: ignore[import-untyped]
    LanceModel,
    Vector,
)
from pydantic import ConfigDict, field_validator

from context_library.storage.models import Domain
from context_library.storage.validators import (
    validate_iso8601_timestamp,
)

VECTOR_DIR = Path.home() / ".context-library" / "vectors"


class ChunkVector(LanceModel):
    """Schema for the LanceDB chunk_vectors table.

    chunk_hash is the join key to the SQLite chunks table.
    LanceDB is derived and disposable; it can be fully rebuilt from SQLite.
    Immutable by design: frozen=True enforces that validators cannot be bypassed by assignment.

    Note: This schema is for documentation and potential future use. The pipeline writes
    plain dicts to LanceDB and uses an explicit pyarrow schema for table creation.
    Runtime validation occurs in the pipeline via validate_embedding_dimension() calls.
    """

    model_config = ConfigDict(frozen=True)

    chunk_hash: str              # join key to SQLite chunks table
    content: str                 # denormalized for reranker access without SQLite lookup
    vector: Vector(384)          # type: ignore[valid-type]  # embedding vector; dimension enforced at write time via schema
    domain: Domain               # supports filtered vector search by domain
    source_id: str               # supports filtered vector search by source
    source_version: int          # supports filtered vector search by version
    created_at: str              # ISO 8601 timestamp

    @field_validator("created_at")
    @classmethod
    def validate_created_at(cls, value: str) -> str:
        """Validate that created_at is a valid ISO 8601 timestamp."""
        validate_iso8601_timestamp(value)
        return value
