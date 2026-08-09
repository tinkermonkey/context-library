"""ChromaDB implementation of the VectorStore port.

Embedded, local-first vector store with no AVX2 requirement.
Derived and fully rebuildable from the document store (SQLite).
"""

import logging
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import chromadb

from context_library.storage.models import Domain
from context_library.storage.vector_store import VectorSearchResult, VectorStore

logger = logging.getLogger(__name__)

COLLECTION_NAME = "chunk_vectors"


class ChromaDBVectorStore(VectorStore):
    """ChromaDB-backed vector store implementation.

    Uses cosine similarity for search. Stores vectors in a persistent
    local directory using ChromaDB's built-in SQLite + HNSW index.
    """

    def __init__(self, path: str | Path) -> None:
        self._path = Path(path)
        self._client: chromadb.ClientAPI | None = None
        self._collection: chromadb.Collection | None = None
        self._embedding_dimension: int | None = None

    def _get_client(self) -> chromadb.ClientAPI:
        if self._client is None:
            self._path.mkdir(parents=True, exist_ok=True)
            self._client = chromadb.PersistentClient(path=str(self._path))
        return self._client

    def _get_collection(self) -> chromadb.Collection:
        if self._collection is None:
            client = self._get_client()
            self._collection = client.get_or_create_collection(
                name=COLLECTION_NAME,
                metadata={"hnsw:space": "cosine"},
            )
        return self._collection

    def initialize(self, embedding_dimension: int) -> None:
        """Initialize the store, recreating the collection if the embedding dimension changed.

        A ChromaDB collection's HNSW index is fixed to the dimension of the first vector
        inserted; upserting vectors of a different dimension (e.g. after switching to a
        new embedding model) raises an error. The collection metadata records the
        dimension it was created with, so a mismatch on restart is detected up front and
        the collection is dropped and recreated empty. The document store remains the
        source of truth, so dropped vectors are recovered by the re-embedding pipeline.

        The initial `get_or_create_collection` call intentionally omits `embedding_dimension`
        from its metadata — passing the *new* dimension there would let ChromaDB apply it to
        an already-existing collection before the stored dimension has been compared, which
        (depending on ChromaDB version) can either raise or silently overwrite the recorded
        dimension and skip the drop-and-recreate below. The dimension tag is only ever written
        via `Collection.modify()` (once we know it matches what's already stored) or as part of
        `create_collection` for a freshly recreated collection.
        """
        self._embedding_dimension = embedding_dimension
        client = self._get_client()
        existing = client.get_or_create_collection(
            name=COLLECTION_NAME,
            metadata={"hnsw:space": "cosine"},
        )
        stored_dimension = self._resolve_stored_dimension(existing)
        if stored_dimension is not None and stored_dimension != embedding_dimension:
            logger.warning(
                "Vector store embedding dimension changed (%s -> %s); dropping stale "
                "'%s' collection. Vectors will be rebuilt by the re-embedding pipeline.",
                stored_dimension, embedding_dimension, COLLECTION_NAME,
            )
            client.delete_collection(name=COLLECTION_NAME)
            existing = client.create_collection(
                name=COLLECTION_NAME,
                metadata={"hnsw:space": "cosine", "embedding_dimension": embedding_dimension},
            )
        else:
            # "hnsw:space" is fixed at creation time and ChromaDB rejects any modify()
            # call that includes it (even with an unchanged value), so only the
            # dimension tag is updated here.
            existing.modify(metadata={"embedding_dimension": embedding_dimension})
        self._collection = existing

    def _resolve_stored_dimension(self, collection: chromadb.Collection) -> int | None:
        """Determine the dimension of vectors already stored in a collection, if any.

        Prefers the dimension recorded in collection metadata (set by this class since
        the dimension-tagging change). Falls back to sampling one stored vector for
        collections created before that change, so pre-existing data is still protected
        against a dimension mismatch. Returns None when the collection is empty (no
        prior vectors to conflict with) or its dimension can't be determined.
        """
        metadata_dimension = (collection.metadata or {}).get("embedding_dimension")
        if metadata_dimension is not None:
            return int(metadata_dimension)
        if collection.count() == 0:
            return None
        sample = collection.get(limit=1, include=["embeddings"])
        embeddings = sample.get("embeddings")
        if embeddings is not None and len(embeddings) > 0:
            return len(embeddings[0])
        return None

    def add_vectors(self, vectors: list[dict[str, Any]]) -> None:
        if not vectors:
            return

        collection = self._get_collection()

        ids: list[str] = []
        embeddings: list[Any] = []
        documents: list[str] = []
        metadatas: list[Mapping[str, str | int | float | bool | None]] = []

        for v in vectors:
            ids.append(v["chunk_hash"])
            embeddings.append(v["vector"])
            documents.append(v["content"])
            metadatas.append({
                "domain": str(v["domain"]),
                "source_id": str(v["source_id"]),
                "source_version": int(v["source_version"]),
                "created_at": str(v["created_at"]),
            })

        # upsert avoids duplicates if the same chunk_hash is added twice
        collection.upsert(
            ids=ids,
            embeddings=embeddings,
            documents=documents,
            metadatas=metadatas,  # type: ignore[arg-type]
        )

    def delete_vectors(self, chunk_hashes: set[str]) -> None:
        if not chunk_hashes:
            return

        collection = self._get_collection()
        collection.delete(ids=list(chunk_hashes))

    def search(
        self,
        query_vector: list[float],
        top_k: int = 10,
        domain_filter: Domain | None = None,
        source_filter: str | None = None,
    ) -> list[VectorSearchResult]:
        collection = self._get_collection()

        if collection.count() == 0:
            raise RuntimeError("Vector store is empty or uninitialized")

        # Build ChromaDB where filter
        where_filters: list[dict] = []
        if domain_filter is not None:
            where_filters.append({"domain": {"$eq": domain_filter.value}})
        if source_filter is not None:
            where_filters.append({"source_id": {"$eq": source_filter}})

        where: dict | None = None
        if len(where_filters) == 1:
            where = where_filters[0]
        elif len(where_filters) > 1:
            where = {"$and": where_filters}

        query_kwargs: dict = {
            "query_embeddings": [query_vector],
            "n_results": top_k,
        }
        if where is not None:
            query_kwargs["where"] = where

        try:
            raw = collection.query(**query_kwargs)
        except Exception as e:
            raise RuntimeError(f"Vector search failed: {type(e).__name__}: {e}") from e

        results = []
        if raw["ids"] and raw["ids"][0]:
            ids = raw["ids"][0]
            distances = raw["distances"][0] if raw["distances"] else [0.0] * len(ids)

            for chunk_hash, distance in zip(ids, distances):
                # ChromaDB cosine distance [0, 2] → similarity [0, 1]
                similarity = min(1.0, max(0.0, 1.0 - (distance / 2.0)))
                results.append(VectorSearchResult(
                    chunk_hash=chunk_hash,
                    similarity_score=similarity,
                ))

        results.sort(key=lambda r: r.similarity_score, reverse=True)
        return results

    def count(self) -> int:
        try:
            collection = self._get_collection()
            return int(collection.count())
        except Exception as e:
            logger.error(f"Failed to count vectors in store: {type(e).__name__}: {e}")
            raise RuntimeError(f"Vector store count failed: {type(e).__name__}: {e}") from e
