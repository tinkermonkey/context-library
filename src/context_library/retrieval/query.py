"""Semantic query interface combining vector search with optional metadata filters.

Enables retrieval of relevant chunks from the vector store via nearest-neighbor search.
Integrates vector similarity with lineage lookup for full provenance tracing.
"""

import logging
import re
from typing import Optional

from pydantic import BaseModel, ConfigDict, field_validator

from context_library.core.embedder import Embedder
from context_library.storage.document_store import DocumentStore
from context_library.storage.models import Chunk, Domain, LineageRecord
from context_library.storage.validators import validate_embedding_dimension
from context_library.storage.vector_store import VectorStore

_logger = logging.getLogger(__name__)

# Allowlist pattern for source_filter: alphanumeric, underscore, hyphen, dot, forward slash
_SAFE_SOURCE_FILTER_PATTERN = re.compile(r"^[a-zA-Z0-9_\-./]+$")


class RetrievalResult(BaseModel):
    """A single result from semantic query with relevance score and lineage.

    Immutable data class capturing a chunk, its provenance lineage, and relevance score.
    Enforces invariants: similarity_score is in [0, 1], chunk and lineage refer to the same content.
    """

    model_config = ConfigDict(frozen=True)

    chunk: Chunk
    lineage: LineageRecord
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

    def model_post_init(self, __context) -> None:
        """Validate RetrievalResult invariants after model construction.

        Enforces:
        - chunk.chunk_hash == lineage.chunk_hash: chunk and lineage refer to the same content
        """
        if self.chunk.chunk_hash != self.lineage.chunk_hash:
            raise ValueError(
                f"chunk-lineage hash mismatch: chunk.chunk_hash={self.chunk.chunk_hash} "
                f"!= lineage.chunk_hash={self.lineage.chunk_hash}. "
                "Chunk and lineage must refer to the same content."
            )

    def to_dict(self) -> dict[str, object]:
        """Convert result to dictionary format.

        Returns:
            Dictionary with chunk content, source metadata, and similarity score.
        """
        return {
            "chunk_text": self.chunk.content,
            "chunk_hash": self.chunk.chunk_hash,
            "context_header": self.chunk.context_header,
            "chunk_index": self.chunk.chunk_index,
            "chunk_type": self.chunk.chunk_type,
            "source_id": self.lineage.source_id,
            "source_version_id": self.lineage.source_version_id,
            "domain": self.lineage.domain.value,
            "adapter_id": self.lineage.adapter_id,
            "embedding_model": self.lineage.embedding_model_id,
            "similarity_score": self.similarity_score,
        }


def retrieve(
    query: str,
    embedder: Embedder,
    document_store: DocumentStore,
    vector_store: VectorStore,
    top_k: int = 10,
    domain_filter: Optional[Domain] = None,
    source_filter: Optional[str] = None,
) -> list[RetrievalResult]:
    """Retrieve relevant chunks via semantic similarity search.

    Performs the complete retrieval flow:
    1. Embeds the query string
    2. Searches vector store for nearest neighbors
    3. Retrieves full chunk content and lineage from SQLite
    4. Returns ranked results with relevance scores

    Args:
        query: The query string to search for.
        embedder: Embedder instance for query embedding.
        document_store: DocumentStore instance for lineage lookup.
        vector_store: VectorStore instance for vector search.
        top_k: Number of results to return. Defaults to 10.
        domain_filter: Optional domain to filter results (NOTES, MESSAGES, EVENTS, TASKS).
        source_filter: Optional source_id to filter results to a specific source.

    Returns:
        List of RetrievalResult objects ranked by similarity score (highest first).

    Raises:
        ValueError: If top_k <= 0, if query is empty/whitespace, or if vector store is empty/uninitialized.
        RuntimeError: If vector store connection fails or vector table is missing.
    """
    if not query or not query.strip():
        raise ValueError("query must be a non-empty string")

    if top_k <= 0:
        raise ValueError(f"top_k must be positive, got {top_k}")

    # Validate source_filter early, before expensive operations
    if source_filter is not None:
        if not _SAFE_SOURCE_FILTER_PATTERN.match(source_filter):
            raise ValueError(
                f'source_filter contains invalid characters: {source_filter!r}'
            )

    # Step 1: Embed the query
    query_vector = embedder.embed_query(query)

    # Validate query embedding
    expected_dim = embedder.dimension
    try:
        validate_embedding_dimension(query_vector, expected_dim)
    except ValueError as e:
        raise ValueError(f"Query embedding validation failed: {e}") from e

    # Step 2: Search vector store
    search_results = vector_store.search(
        query_vector=query_vector,
        top_k=top_k,
        domain_filter=domain_filter,
        source_filter=source_filter,
    )

    if not search_results:
        return []

    # Step 3: Enrich results with full chunk content and lineage
    results: list[RetrievalResult] = []

    for hit in search_results:
        chunk_hash = hit.chunk_hash
        similarity_score = hit.similarity_score

        # Retrieve full chunk from SQLite
        chunk = document_store.get_chunk_by_hash(chunk_hash)
        if chunk is None:
            if document_store.is_chunk_retired(chunk_hash):
                _logger.debug(
                    "Skipping retired chunk (chunk_hash=%s) during retrieval. "
                    "Chunk exists in vector store but is marked retired in document store. "
                    "This is normal pipeline behavior (lazy cleanup).",
                    chunk_hash,
                )
                continue
            else:
                _logger.warning(
                    "Store inconsistency: chunk_hash=%s exists in vector store but not in SQLite. "
                    "This indicates desynchronization between vector store and document store.",
                    chunk_hash,
                )
                continue

        # Retrieve lineage from SQLite
        lineage = document_store.get_lineage(chunk_hash)
        if lineage is None:
            _logger.warning(
                "Store inconsistency: chunk_hash=%s has no lineage record in SQLite. "
                "Chunk exists but provenance information is missing.",
                chunk_hash,
            )
            continue

        results.append(RetrievalResult(chunk=chunk, lineage=lineage, similarity_score=similarity_score))

    # Sort by similarity score (highest first)
    results.sort(key=lambda r: r.similarity_score, reverse=True)

    return results
