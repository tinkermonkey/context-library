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
    EMBEDDING_DIM,
    validate_embedding_dimension,
    validate_iso8601_timestamp,
)

VECTOR_DIR = Path.home() / ".context-library" / "vectors"


class ChunkVector(LanceModel):
    """Schema for the LanceDB chunk_vectors table.

    chunk_hash is the join key to the SQLite chunks table.
    LanceDB is derived and disposable; it can be fully rebuilt from SQLite.
    Immutable by design: frozen=True enforces that validators cannot be bypassed by assignment.

    Note: domain is stored as str to enable LanceDB serialization. The field is validated
    to ensure it contains only valid Domain enum values (messages|notes|events|tasks).
    This preserves type safety at the application boundary while accommodating LanceDB's
    serialization constraints.
    """

    model_config = ConfigDict(frozen=True)

    chunk_hash: str              # join key to SQLite chunks table
    content: str                 # denormalized for reranker access without SQLite lookup
    vector: Vector(EMBEDDING_DIM)  # type: ignore[valid-type]  # fixed-size embedding vector (float32 optimized storage)
    domain: str                  # domain type (messages|notes|events|tasks) — validated to be valid Domain enum value
    source_id: str               # supports filtered vector search by source
    source_version: int          # supports filtered vector search by version
    created_at: str              # ISO 8601 timestamp

    @field_validator("vector", mode="before")
    @classmethod
    def validate_vector(cls, value: Sequence[float]) -> Sequence[float]:
        """Validate that vector has correct dimension and no NaN/infinity values.

        NaN and infinity corrupt similarity calculations in LanceDB.
        """
        validate_embedding_dimension(value)
        return value

    @field_validator("domain", mode="before")
    @classmethod
    def validate_domain(cls, value: Domain | str) -> str:
        """Validate that domain is a valid Domain enum value.

        Accepts both Domain enum instances and string values.
        Always returns the string value for LanceDB serialization.
        """
        if isinstance(value, Domain):
            return value.value
        if isinstance(value, str):
            try:
                # Validate that the string is a valid Domain value
                Domain(value)
                return value
            except ValueError:
                valid_values = ", ".join(d.value for d in Domain)
                raise ValueError(
                    f"Invalid domain '{value}'. Must be one of: {valid_values}"
                )
        raise ValueError(f"domain must be Domain enum or string, got {type(value)}")

    @field_validator("created_at")
    @classmethod
    def validate_created_at(cls, value: str) -> str:
        """Validate that created_at is a valid ISO 8601 timestamp."""
        validate_iso8601_timestamp(value)
        return value
