"""LanceDB-backed vector index; derived and fully rebuildable from the document store."""

from pathlib import Path

from lancedb.pydantic import LanceModel  # type: ignore[import-untyped]
from pydantic import ConfigDict, field_validator

from context_library.storage.models import Domain, Sha256Hash
from context_library.storage.validators import (
    validate_iso8601_timestamp,
)

VECTOR_DIR = Path.home() / ".context-library" / "vectors"


class ChunkVector(LanceModel):
    """Schema for the LanceDB chunk_vectors table.

    chunk_hash is the join key to the SQLite chunks table, validated as a proper SHA-256 hash
    to prevent orphaned vector records from malformed hashes. This validation ensures consistency
    between the vector store and document store at the join point.

    LanceDB is derived and disposable; it can be fully rebuilt from SQLite.
    Immutable by design: frozen=True enforces that validators cannot be bypassed by assignment.

    IMPORTANT: This schema IS used by the pipeline for field validation (e.g., created_at
    ISO 8601 format). See IngestionPipeline.ingest() pipeline.py:191-199 where each chunk
    vector is instantiated as ChunkVector for validation before being converted to a dict
    for LanceDB. The vector field dimension is still enforced by the pyarrow schema during
    table creation, not by Pydantic (since vector length cannot be parameterized in v2).
    """

    model_config = ConfigDict(frozen=True)

    chunk_hash: Sha256Hash       # join key to SQLite chunks table (validated as SHA-256 hash)
    content: str                 # denormalized for reranker access without SQLite lookup
    vector: list[float]          # embedding vector; type hint only (dimension enforced by pyarrow schema)
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
