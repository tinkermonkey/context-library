"""LanceDB-backed vector index; derived and fully rebuildable from the document store."""

from lancedb.pydantic import LanceModel, Vector  # type: ignore[import-untyped]

VECTOR_DIR = "~/.context-library/vectors"
EMBEDDING_DIM = 384  # all-MiniLM-L6-v2; change here when swapping embedding model


class ChunkVector(LanceModel):
    """Schema for the LanceDB chunk_vectors table.

    chunk_hash is the join key to the SQLite chunks table.
    LanceDB is derived and disposable; it can be fully rebuilt from SQLite.
    """

    chunk_hash: str       # join key to SQLite chunks table
    content: str          # denormalized for reranker access without SQLite lookup
    vector: Vector[EMBEDDING_DIM]
    domain: str           # supports filtered vector search by domain
    source_id: str        # supports filtered vector search by source
    source_version: int   # supports filtered vector search by version
    created_at: str       # ISO 8601 timestamp
