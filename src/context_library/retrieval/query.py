"""Semantic query interface combining vector search with optional metadata filters.

Enables retrieval of relevant chunks from the vector store via nearest-neighbor search.
Integrates vector similarity with lineage lookup for full provenance tracing.
"""

import logging
import re
from pathlib import Path
from typing import Optional

import lancedb
from pydantic import BaseModel, ConfigDict, field_validator

from context_library.core.embedder import Embedder
from context_library.storage.document_store import DocumentStore
from context_library.storage.models import Chunk, Domain, LineageRecord
from context_library.storage.validators import validate_embedding_dimension
from context_library.storage.vector_store import VECTOR_DIR

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


class RerankedResult(BaseModel):
    """A reranked retrieval result with distinct vector and cross-encoder scores.

    Wraps a RetrievalResult with a separate reranker_score field to distinguish
    the original vector-similarity score from the cross-encoder relevance score.
    Enables callers to access both scoring signals for diagnostics or hybrid ranking.

    Immutable data class following the same pattern as RetrievalResult.
    """

    model_config = ConfigDict(frozen=True)

    retrieval_result: RetrievalResult
    reranker_score: float

    @field_validator("reranker_score")
    @classmethod
    def validate_reranker_score(cls, value: float) -> float:
        """Validate that reranker_score is in the valid range [0, 1]."""
        if not (0.0 <= value <= 1.0):
            raise ValueError(
                f"reranker_score must be in range [0, 1], got {value}"
            )
        return value

    @property
    def chunk(self) -> Chunk:
        """Access the underlying chunk."""
        return self.retrieval_result.chunk

    @property
    def lineage(self) -> LineageRecord:
        """Access the underlying lineage."""
        return self.retrieval_result.lineage

    @property
    def similarity_score(self) -> float:
        """Access the original vector similarity score."""
        return self.retrieval_result.similarity_score

    def to_dict(self) -> dict[str, object]:
        """Convert result to dictionary format.

        Returns:
            Dictionary with chunk content, source metadata, vector similarity score,
            and reranker score.
        """
        result_dict = self.retrieval_result.to_dict()
        result_dict["reranker_score"] = self.reranker_score
        return result_dict


def retrieve(
    query: str,
    embedder: Embedder,
    document_store: DocumentStore,
    vector_store_path: Path = VECTOR_DIR,
    top_k: int = 10,
    domain_filter: Optional[Domain] = None,
    source_filter: Optional[str] = None,
) -> list[RetrievalResult]:
    """Retrieve relevant chunks via semantic similarity search.

    Performs the complete retrieval flow:
    1. Embeds the query string
    2. Searches LanceDB vector store for nearest neighbors
    3. Retrieves full chunk content and lineage from SQLite
    4. Returns ranked results with relevance scores

    Args:
        query: The query string to search for.
        embedder: Embedder instance for query embedding.
        document_store: DocumentStore instance for lineage lookup.
        vector_store_path: Path to LanceDB vector directory. Defaults to ~/.context-library/vectors.
        top_k: Number of results to return. Defaults to 10.
        domain_filter: Optional domain to filter results (NOTES, MESSAGES, EVENTS, TASKS).
        source_filter: Optional source_id to filter results to a specific source.

    Returns:
        List of RetrievalResult objects ranked by similarity score (highest first).

    Raises:
        ValueError: If top_k <= 0, if query is empty/whitespace, or if vector store is empty/uninitialized.
        RuntimeError: If LanceDB connection fails or vector table is missing.
    """
    if not query or not query.strip():
        raise ValueError("query must be a non-empty string")

    if top_k <= 0:
        raise ValueError(f"top_k must be positive, got {top_k}")

    # Validate source_filter early, before expensive operations
    if source_filter is not None:
        # Validate source_filter using allowlist pattern to prevent SQL injection.
        # Only allow alphanumeric, underscore, hyphen, dot, and forward slash.
        if not _SAFE_SOURCE_FILTER_PATTERN.match(source_filter):
            raise ValueError(
                f'source_filter contains invalid characters: {source_filter!r}'
            )

    # Step 1: Embed the query
    query_vector = embedder.embed_query(query)

    # Validate query embedding for correct dimension and finite values
    expected_dim = embedder.dimension
    try:
        validate_embedding_dimension(query_vector, expected_dim)
    except ValueError as e:
        raise ValueError(f"Query embedding validation failed: {e}") from e

    # Step 2: Connect to LanceDB and search
    db = lancedb.connect(str(vector_store_path))

    try:
        table = db.open_table("chunk_vectors")
    except (FileNotFoundError, ValueError, RuntimeError, OSError) as e:
        # FileNotFoundError: vector store path doesn't exist
        # ValueError: table doesn't exist in LanceDB
        # RuntimeError: LanceDB internal errors
        # OSError: permission or I/O errors
        raise RuntimeError(
            f"Failed to open chunk_vectors table in LanceDB at {vector_store_path}: {type(e).__name__}: {e}"
        ) from e

    # Build the search query with optional filters
    search_query = table.search(query_vector)

    # Build filter conditions; multiple filters are combined with AND logic
    # Both filters are sanitized before inclusion in the query string
    filters = []
    if domain_filter is not None:
        # Domain filter is safe because domain_filter is an enum with fixed values
        filters.append(f'domain = "{domain_filter.value}"')

    if source_filter is not None:
        # source_filter already validated above
        filters.append(f'source_id = "{source_filter}"')

    # Apply combined filter if any conditions exist
    if filters:
        filter_expr = " AND ".join(filters)
        search_query = search_query.where(filter_expr)

    # Execute search and get top_k results
    try:
        search_results = search_query.limit(top_k).to_list()
    except (ValueError, RuntimeError, TypeError) as e:
        # ValueError: invalid filter expression or top_k value
        # RuntimeError: LanceDB query execution errors
        # TypeError: type mismatch in filter conditions
        raise RuntimeError(f"Vector search failed: {type(e).__name__}: {e}") from e

    if not search_results:
        return []

    # Step 3: Enrich results with full chunk content and lineage
    results: list[RetrievalResult] = []

    for row in search_results:
        chunk_hash = row["chunk_hash"]
        distance = row.get("_distance")

        # LanceDB returns Euclidean distance; convert to similarity score [0, 1]
        # For normalized embeddings, distance ranges [0, 4], so similarity = 1 - (distance / 2)
        # This maps distance 0 (identical) to similarity 1.0, and clamps high distances to 0.
        # max(0.0, ...) handles any floating-point drift that could produce negative scores.
        if distance is None:
            # LanceDB should always return _distance; raise error if missing to avoid false positives
            raise RuntimeError(
                f"Missing _distance field in search result for chunk {chunk_hash}. "
                "This indicates an issue with the LanceDB table schema or search output."
            )

        if isinstance(distance, (int, float)):
            # Clamp similarity score to [0, 1] range to match RetrievalResult validator.
            # The lower bound is inherently protected by max(0.0, ...). The upper bound
            # is explicitly clamped with min(1.0, ...) to handle edge cases where LanceDB
            # returns negative distances (anomalous but possible with certain metrics or
            # floating-point drift), which would otherwise produce scores > 1.0.
            similarity_score = min(1.0, max(0.0, 1.0 - (distance / 2.0)))
        else:
            # Defensive fallback: non-numeric distance (shouldn't happen with standard LanceDB output)
            raise RuntimeError(
                f"Invalid _distance type {type(distance)} for chunk {chunk_hash}. "
                "Expected numeric value."
            )

        # Retrieve full chunk from SQLite
        chunk = document_store.get_chunk_by_hash(chunk_hash)
        if chunk is None:
            # Chunk not found in active records. Determine the reason: retired or truly missing.
            if document_store.is_chunk_retired(chunk_hash):
                # Chunk is retired in SQLite but still searchable in LanceDB.
                # This is normal behavior: LanceDB deletion is lazy, and post-retrieval filtering
                # catches stale results. Log at debug level so operators can diagnose why fewer
                # results are returned than requested. (See issue #72 for higher-level caller feedback.)
                _logger.debug(
                    "Skipping retired chunk (chunk_hash=%s) during retrieval. "
                    "Chunk exists in vector store but is marked retired in document store. "
                    "This is normal pipeline behavior (lazy cleanup).",
                    chunk_hash,
                )
                continue
            else:
                # Chunk exists in LanceDB but doesn't exist in SQLite at all.
                # This indicates true store desynchronization (e.g., SQLite delete succeeded
                # but LanceDB cleanup failed, or data corruption).
                _logger.warning(
                    "Store inconsistency: chunk_hash=%s exists in LanceDB but not in SQLite. "
                    "This indicates desynchronization between vector store and document store.",
                    chunk_hash,
                )
                continue

        # Retrieve lineage from SQLite
        lineage = document_store.get_lineage(chunk_hash)
        if lineage is None:
            # Lineage missing despite chunk existing - indicates store desynchronization
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
