"""Semantic query interface combining vector search with optional metadata filters."""

from pathlib import Path

import lancedb

from context_library.core.embedder import Embedder
from context_library.storage.document_store import DocumentStore
from context_library.storage.models import LineageRecord


def retrieve(
    query: str,
    embedder: Embedder,
    lance_db_path: Path,
    document_store: DocumentStore,
    top_k: int = 10,
) -> list[dict]:
    """Retrieve chunks from LanceDB via semantic vector search.

    Embeds the query, performs nearest-neighbor search on the chunk_vectors table,
    and returns the top_k results ordered by relevance score (highest first).

    Args:
        query: The search query text to embed and search for
        embedder: Embedder instance for converting query to vector
        lance_db_path: Path to the LanceDB database directory
        document_store: DocumentStore for potential future metadata lookups
        top_k: Maximum number of results to return (default: 10)

    Returns:
        List of dicts with keys: chunk_text, chunk_hash, source_id, score
        Ordered by descending relevance score (highest first).
        Returns fewer results if fewer than top_k chunks exist in the index.
    """
    # Embed the query
    query_vector = embedder.embed_query(query)

    # Open LanceDB and access the chunk vectors table
    db = lancedb.connect(str(lance_db_path))
    table = db.open_table("chunk_vectors")

    # Perform nearest-neighbor search
    results = table.search(query_vector).limit(top_k).to_list()

    # Map results to output format
    output = []
    for result in results:
        # LanceDB returns _distance where lower values = closer matches
        # Convert to relevance score: 1.0 - distance
        score = 1.0 - result["_distance"]

        output.append(
            {
                "chunk_text": result["content"],
                "chunk_hash": result["chunk_hash"],
                "source_id": result["source_id"],
                "score": score,
            }
        )

    # Results from LanceDB search are already ordered by distance (ascending)
    # which means by score (descending), so no additional sorting needed
    return output


def get_lineage(chunk_hash: str, document_store: DocumentStore) -> LineageRecord | None:
    """Retrieve lineage information for a chunk from the document store.

    Args:
        chunk_hash: The hash identifier of the chunk
        document_store: DocumentStore instance for lineage lookup

    Returns:
        LineageRecord if the chunk exists, None otherwise
    """
    return document_store.get_lineage(chunk_hash)
