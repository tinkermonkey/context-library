"""LanceDB-backed vector index; derived and fully rebuildable from the document store."""

import logging
import math
from pathlib import Path

import lancedb
import pyarrow as pa
from lancedb.pydantic import LanceModel  # type: ignore[import-untyped]
from pydantic import ConfigDict, field_validator

from context_library.storage.models import Domain, Sha256Hash
from context_library.storage.validators import (
    validate_iso8601_timestamp,
)

logger = logging.getLogger(__name__)

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


def create_chunk_vector_schema(embedding_dimension: int) -> pa.Schema:
    """Create a PyArrow schema for the chunk_vectors LanceDB table.

    The schema defines fields for storing embeddings with vector dimension
    determined by the configured embedder model.

    Args:
        embedding_dimension: The dimension of the embedding vectors.

    Returns:
        A PyArrow schema matching the ChunkVector LanceModel structure.
    """
    return pa.schema([
        ("chunk_hash", pa.string()),
        ("content", pa.string()),
        ("vector", pa.list_(pa.float32(), embedding_dimension)),
        ("domain", pa.string()),
        ("source_id", pa.string()),
        ("source_version", pa.int32()),
        ("created_at", pa.string()),
    ])


def should_create_index(
    vector_store_path: Path,
    threshold: int = 10_000,
) -> bool:
    """Return True if chunk count in LanceDB exceeds threshold.

    This utility determines whether to create an IVF-PQ index based on the
    current chunk count. Below ~10K chunks, brute-force search is fast enough.
    Above that, IVF-PQ provides meaningful latency improvement.

    Args:
        vector_store_path: Path to the LanceDB directory.
        threshold: Row count threshold (default 10,000).

    Returns:
        True if the chunk_vectors table exists and has >= threshold rows,
        False otherwise (including when the table does not exist).
    """
    try:
        db = lancedb.connect(str(vector_store_path))
        table = db.open_table("chunk_vectors")
        return bool(table.count_rows() >= threshold)
    except FileNotFoundError:
        # Vector store path doesn't exist; index creation not needed yet
        return False
    except OSError as e:
        # Disk errors, permission errors, file system issues
        logger.warning(
            f"Could not access vector store at {vector_store_path}: {e}"
        )
        return False
    except MemoryError:
        # Out of memory during database operations; non-recoverable system condition
        logger.error(
            f"Out of memory while checking index threshold for {vector_store_path}"
        )
        raise
    except (ValueError, RuntimeError):
        # LanceDB-specific errors: table not found, database corruption, etc.
        # These are expected conditions that indicate index creation is not needed
        return False


def create_ivf_pq_index(
    vector_store_path: Path,
    num_partitions: int | None = None,
    num_sub_vectors: int | None = None,
) -> None:
    """Create an IVF-PQ ANN index on chunk_vectors.

    IVF-PQ indexing is an offline/maintenance operation that does not block
    ingestion. After indexing, table.search(vector) continues to work identically
    as LanceDB uses the index transparently.

    Index creation is idempotent: calling it on a table that already has an
    IVF-PQ index will not raise an error (via replace=True).

    Args:
        vector_store_path: Path to the LanceDB directory.
        num_partitions: Number of IVF partitions (default: int(sqrt(row_count))).
        num_sub_vectors: Number of sub-vectors for PQ (default: embedding_dimension // 8).

    Raises:
        FileNotFoundError: If the vector store path does not exist.
        ValueError: If the chunk_vectors table does not exist or schema is invalid.
        OSError: If disk I/O or permissions prevent table access.
        MemoryError: If indexing exhausts available memory.
        RuntimeError: If the indexing operation fails.
    """
    try:
        db = lancedb.connect(str(vector_store_path))
    except FileNotFoundError as e:
        logger.error(f"Vector store path does not exist: {vector_store_path}")
        raise FileNotFoundError(
            f"Vector store path does not exist: {vector_store_path}"
        ) from e

    try:
        table = db.open_table("chunk_vectors")
    except FileNotFoundError as e:
        logger.error(
            f"chunk_vectors table does not exist at {vector_store_path}"
        )
        raise ValueError(
            f"chunk_vectors table does not exist at {vector_store_path}"
        ) from e

    try:
        row_count = table.count_rows()
    except OSError as e:
        logger.error(
            f"Could not read row count from {vector_store_path}: {e}"
        )
        raise OSError(
            f"Could not read row count from {vector_store_path}"
        ) from e
    except MemoryError as e:
        logger.error(
            f"Out of memory while reading row count from {vector_store_path}"
        )
        raise

    # Default num_partitions to sqrt(row_count) if not provided
    if num_partitions is None:
        num_partitions = max(1, int(math.sqrt(row_count)))

    # Default num_sub_vectors to dimension // 8 if not provided
    if num_sub_vectors is None:
        try:
            schema = table.schema
            vec_field = schema.field("vector")
            dimension = vec_field.type.list_size
            num_sub_vectors = max(1, dimension // 8)
        except (KeyError, AttributeError) as e:
            logger.error(
                f"Invalid schema for chunk_vectors at {vector_store_path}: "
                "vector field not found or has invalid type"
            )
            raise ValueError(
                f"Invalid schema for chunk_vectors: vector field missing or invalid type"
            ) from e

    # Create index with replace=True for idempotency
    try:
        table.create_index(
            metric="cosine",
            num_partitions=num_partitions,
            num_sub_vectors=num_sub_vectors,
            replace=True,
        )
    except OSError as e:
        logger.error(
            f"Disk I/O error during index creation for {vector_store_path}: {e}"
        )
        raise OSError(
            f"Disk I/O error during index creation for {vector_store_path}"
        ) from e
    except MemoryError as e:
        logger.error(
            f"Out of memory during index creation for {vector_store_path}"
        )
        raise
    except (ValueError, RuntimeError) as e:
        logger.error(
            f"Index creation failed for {vector_store_path}: {type(e).__name__}: {e}"
        )
        raise RuntimeError(
            f"Index creation failed for {vector_store_path}"
        ) from e
