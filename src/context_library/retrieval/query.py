"""Semantic query interface combining vector search with optional metadata filters.

Enables retrieval of relevant chunks from the vector store via nearest-neighbor search.
Integrates vector similarity with lineage lookup for full provenance tracing.
"""

import re
from pathlib import Path
from typing import Optional

import lancedb
from pydantic import BaseModel, ConfigDict

from context_library.core.embedder import Embedder
from context_library.storage.document_store import DocumentStore
from context_library.storage.models import Chunk, Domain, LineageRecord
from context_library.storage.vector_store import VECTOR_DIR

# Allowlist pattern for source_filter: alphanumeric, underscore, hyphen, dot, forward slash
_SAFE_SOURCE_FILTER_PATTERN = re.compile(r"^[a-zA-Z0-9_\-./]+$")


class RetrievalResult(BaseModel):
    """A single result from semantic query with relevance score and lineage.

    Immutable data class capturing a chunk, its provenance lineage, and relevance score.
    """

    model_config = ConfigDict(frozen=True)

    chunk: Chunk
    lineage: LineageRecord
    similarity_score: float

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
        ValueError: If top_k <= 0 or if vector store is empty/uninitialized.
        RuntimeError: If LanceDB connection fails or vector table is missing.
    """
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

    # Step 2: Connect to LanceDB and search
    db = lancedb.connect(str(vector_store_path))

    try:
        table = db.open_table("chunk_vectors")
    except Exception as e:
        raise RuntimeError(
            f"Failed to open chunk_vectors table in LanceDB at {vector_store_path}: {e}"
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
    except Exception as e:
        raise RuntimeError(f"Vector search failed: {e}") from e

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
            similarity_score = max(0.0, 1.0 - (distance / 2.0))
        else:
            # Defensive fallback: non-numeric distance (shouldn't happen with standard LanceDB output)
            raise RuntimeError(
                f"Invalid _distance type {type(distance)} for chunk {chunk_hash}. "
                "Expected numeric value."
            )

        # Retrieve full chunk from SQLite
        chunk = document_store.get_chunk_by_hash(chunk_hash)
        if chunk is None:
            # Skip chunks that don't exist in SQLite (shouldn't happen)
            continue

        # Retrieve lineage from SQLite
        lineage = document_store.get_lineage(chunk_hash)
        if lineage is None:
            # Skip chunks without lineage (shouldn't happen)
            continue

        results.append(RetrievalResult(chunk=chunk, lineage=lineage, similarity_score=similarity_score))

    # Sort by similarity score (highest first)
    results.sort(key=lambda r: r.similarity_score, reverse=True)

    return results
