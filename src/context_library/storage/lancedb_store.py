"""LanceDB implementation of the VectorStore port.

Derived and fully rebuildable from the document store (SQLite).
"""

import logging
import math
from pathlib import Path
from typing import Optional

import lancedb
import pyarrow as pa

from context_library.storage.models import Domain
from context_library.storage.vector_store import VectorSearchResult, VectorStore

logger = logging.getLogger(__name__)

TABLE_NAME = "chunk_vectors"


def _create_chunk_vector_schema(embedding_dimension: int) -> pa.Schema:
    """Create a PyArrow schema for the chunk_vectors LanceDB table."""
    return pa.schema([
        ("chunk_hash", pa.string()),
        ("content", pa.string()),
        ("vector", pa.list_(pa.float32(), embedding_dimension)),
        ("domain", pa.string()),
        ("source_id", pa.string()),
        ("source_version", pa.int32()),
        ("created_at", pa.string()),
    ])


class LanceDBVectorStore(VectorStore):
    """LanceDB-backed vector store implementation.

    Uses cosine distance for similarity search. Supports IVF-PQ indexing
    for large collections (>10K vectors).
    """

    def __init__(self, path: str | Path) -> None:
        self._path = Path(path)
        self._db: lancedb.DBConnection | None = None
        self._embedding_dimension: int | None = None

    def _connect(self) -> lancedb.DBConnection:
        if self._db is None:
            self._db = lancedb.connect(str(self._path))
        return self._db

    def _table_exists(self) -> bool:
        db = self._connect()
        return TABLE_NAME in db.list_tables().tables

    def initialize(self, embedding_dimension: int) -> None:
        self._embedding_dimension = embedding_dimension
        self._connect()

    def add_vectors(self, vectors: list[dict]) -> None:
        if not vectors:
            return

        db = self._connect()

        if self._table_exists():
            table = db.open_table(TABLE_NAME)
            table.add(vectors)
        else:
            if self._embedding_dimension is None:
                self._embedding_dimension = len(vectors[0]["vector"])
            schema = _create_chunk_vector_schema(self._embedding_dimension)
            db.create_table(TABLE_NAME, data=vectors, schema=schema)

    def delete_vectors(self, chunk_hashes: set[str]) -> None:
        if not chunk_hashes or not self._table_exists():
            return

        db = self._connect()
        table = db.open_table(TABLE_NAME)
        quoted_hashes = ", ".join(f"'{h}'" for h in chunk_hashes)
        table.delete(f"chunk_hash IN ({quoted_hashes})")

    def search(
        self,
        query_vector: list[float],
        top_k: int = 10,
        domain_filter: Optional[Domain] = None,
        source_filter: Optional[str] = None,
    ) -> list[VectorSearchResult]:
        if not self._table_exists():
            raise RuntimeError(
                f"chunk_vectors table does not exist at {self._path}"
            )

        db = self._connect()
        table = db.open_table(TABLE_NAME)
        search_query = table.search(query_vector)

        filters = []
        if domain_filter is not None:
            filters.append(f'domain = "{domain_filter.value}"')
        if source_filter is not None:
            filters.append(f'source_id = "{source_filter}"')

        if filters:
            filter_expr = " AND ".join(filters)
            search_query = search_query.where(filter_expr)

        try:
            raw_results = search_query.limit(top_k).to_list()
        except (ValueError, RuntimeError, TypeError) as e:
            raise RuntimeError(f"Vector search failed: {type(e).__name__}: {e}") from e

        results = []
        for row in raw_results:
            distance = row.get("_distance")
            if distance is None:
                raise RuntimeError(
                    f"Missing _distance field in search result for chunk {row['chunk_hash']}."
                )
            if not isinstance(distance, (int, float)):
                raise RuntimeError(
                    f"Invalid _distance type {type(distance)} for chunk {row['chunk_hash']}."
                )
            # LanceDB cosine distance [0, 2] → similarity [0, 1]
            similarity = min(1.0, max(0.0, 1.0 - (distance / 2.0)))
            results.append(VectorSearchResult(
                chunk_hash=row["chunk_hash"],
                similarity_score=similarity,
            ))

        results.sort(key=lambda r: r.similarity_score, reverse=True)
        return results

    def count(self) -> int:
        if not self._table_exists():
            return 0
        db = self._connect()
        table = db.open_table(TABLE_NAME)
        return int(table.count_rows())

    def should_create_index(self, threshold: int = 10_000) -> bool:
        """Return True if chunk count exceeds threshold for IVF-PQ indexing."""
        try:
            return self.count() >= threshold
        except FileNotFoundError:
            return False
        except PermissionError:
            logger.error(f"Permission denied accessing vector store at {self._path}")
            raise
        except MemoryError:
            logger.error(f"Out of memory while checking index threshold for {self._path}")
            raise
        except (OSError, ValueError, RuntimeError) as e:
            logger.warning(f"Could not check index threshold at {self._path}: {e}")
            return False

    def create_ivf_pq_index(
        self,
        num_partitions: int | None = None,
        num_sub_vectors: int | None = None,
    ) -> None:
        """Create an IVF-PQ ANN index on chunk_vectors. Idempotent via replace=True."""
        db = self._connect()

        try:
            table = db.open_table(TABLE_NAME)
        except FileNotFoundError as e:
            raise ValueError(f"chunk_vectors table does not exist at {self._path}") from e

        row_count = table.count_rows()

        if num_partitions is None:
            num_partitions = max(1, int(math.sqrt(row_count)))

        if num_sub_vectors is None:
            schema = table.schema
            vec_field = schema.field("vector")
            dimension = vec_field.type.list_size
            num_sub_vectors = max(1, dimension // 8)

        table.create_index(
            metric="cosine",
            num_partitions=num_partitions,
            num_sub_vectors=num_sub_vectors,
            replace=True,
        )
