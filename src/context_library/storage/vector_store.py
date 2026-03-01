"""LanceDB-backed vector index; derived and fully rebuildable from the document store."""

from lancedb.pydantic import LanceModel, Vector

VECTOR_DIR = "~/.context-library/vectors"
EMBEDDING_DIM = 384  # all-MiniLM-L6-v2 default; configurable


class ChunkVector(LanceModel):
    """LanceDB vector model for chunk embeddings and metadata."""

    chunk_hash: str
    content: str
    vector: Vector(EMBEDDING_DIM)
    domain: str
    source_id: str
    source_version: int
    created_at: str
