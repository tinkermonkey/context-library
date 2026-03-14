"""Abstract vector store port defining the contract for vector storage backends.

This module defines the hexagonal architecture port for vector storage.
Implementations (LanceDB, ChromaDB, etc.) live in separate modules and
implement this interface. The vector store is derived and fully rebuildable
from the document store (SQLite).
"""

import logging
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Optional

from pydantic import BaseModel, ConfigDict, field_validator

from context_library.storage.models import Domain, Sha256Hash
from context_library.storage.validators import validate_iso8601_timestamp

logger = logging.getLogger(__name__)

VECTOR_DIR = Path.home() / ".context-library" / "vectors"


class ChunkVectorData(BaseModel):
    """Validated data for a chunk vector record.

    Used by the pipeline to validate field formats (SHA-256 hash, ISO 8601 timestamp)
    before passing to any vector store backend. Backend-agnostic: no dependency on
    LanceDB, ChromaDB, or any specific storage library.

    chunk_hash is the join key to the SQLite chunks table.
    """

    model_config = ConfigDict(frozen=True)

    chunk_hash: Sha256Hash
    content: str
    vector: list[float]
    domain: Domain
    source_id: str
    source_version: int
    created_at: str

    @field_validator("created_at")
    @classmethod
    def validate_created_at(cls, value: str) -> str:
        """Validate that created_at is a valid ISO 8601 timestamp."""
        validate_iso8601_timestamp(value)
        return value


class VectorSearchResult(BaseModel):
    """A single result from vector similarity search.

    Backend-agnostic representation of a search hit. Similarity score is
    normalized to [0, 1] where 1.0 = identical and 0.0 = maximally dissimilar.
    """

    model_config = ConfigDict(frozen=True)

    chunk_hash: str
    similarity_score: float

    @field_validator("similarity_score")
    @classmethod
    def validate_similarity_score(cls, value: float) -> float:
        """Validate that similarity_score is in the valid range [0, 1]."""
        if not (0.0 <= value <= 1.0):
            raise ValueError(
                f"similarity_score must be in range [0, 1], got {value}"
            )
        return value


class VectorStore(ABC):
    """Abstract port for vector storage backends.

    Implementations must handle their own table/collection management internally.
    The pipeline and retrieval layers interact only through this interface.

    All implementations share these semantics:
    - add_vectors: idempotent bulk insert (create collection if needed)
    - delete_vectors: remove vectors by chunk hash
    - search: nearest-neighbor search with optional metadata filters
    - count: return total number of stored vectors
    - initialize: set up the store with the embedding dimension (called once)
    """

    @abstractmethod
    def initialize(self, embedding_dimension: int) -> None:
        """Initialize the vector store with the given embedding dimension.

        Called once before first use. Implementations should create
        collections/tables as needed. Must be idempotent.

        Args:
            embedding_dimension: Dimension of the embedding vectors.
        """

    @abstractmethod
    def add_vectors(self, vectors: list[dict]) -> None:
        """Add chunk vectors to the store.

        Each dict must contain: chunk_hash, content, vector, domain (str),
        source_id, source_version (int), created_at (ISO 8601 str).

        Must be idempotent: adding the same chunk_hash twice should not
        create duplicates (or at minimum, not cause errors).

        Args:
            vectors: List of chunk vector dicts to insert.
        """

    @abstractmethod
    def delete_vectors(self, chunk_hashes: set[str]) -> None:
        """Delete vectors by their chunk hashes.

        Should not raise if a hash does not exist in the store.

        Args:
            chunk_hashes: Set of chunk hashes to remove.
        """

    @abstractmethod
    def search(
        self,
        query_vector: list[float],
        top_k: int = 10,
        domain_filter: Optional[Domain] = None,
        source_filter: Optional[str] = None,
    ) -> list[VectorSearchResult]:
        """Search for nearest neighbors to the query vector.

        Args:
            query_vector: The query embedding vector.
            top_k: Maximum number of results to return.
            domain_filter: Optional domain to filter results.
            source_filter: Optional source_id to filter results.

        Returns:
            List of VectorSearchResult ordered by similarity (highest first).

        Raises:
            RuntimeError: If the store is not initialized or search fails.
        """

    @abstractmethod
    def count(self) -> int:
        """Return the total number of vectors in the store.

        Returns:
            Number of stored vectors, or 0 if the store is empty/uninitialized.
        """
