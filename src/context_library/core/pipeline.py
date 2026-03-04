"""Orchestrates the full ingestion pipeline: fetch → normalize → diff → chunk → embed → store."""

from datetime import datetime, timezone
from pathlib import Path

import lancedb
import pyarrow as pa

from context_library.core.differ import Differ
from context_library.core.embedder import Embedder
from context_library.adapters.base import BaseAdapter
from context_library.domains.base import BaseDomain
from context_library.storage.document_store import DocumentStore
from context_library.storage.models import LineageRecord
from context_library.storage.validators import validate_embedding_dimension
from context_library.storage.vector_store import ChunkVector


class IngestionPipeline:
    """Orchestrates the full ingestion pipeline from adapter through storage.

    Coordinates fetching, normalizing, chunking, embedding, and storing of content
    across both SQLite (DocumentStore) and LanceDB (vector storage).

    Key responsibilities:
    - Register adapters with the document store (idempotent)
    - Fetch and normalize content via adapters
    - Detect changes via the Differ
    - Chunk content via domain-specific chunkers
    - Embed new/modified chunks
    - Write to both SQLite and LanceDB atomically
    - Retire deleted chunks from both stores
    """

    def __init__(
        self,
        document_store: DocumentStore,
        embedder: Embedder,
        differ: Differ,
        vector_store_path: str | Path,
    ) -> None:
        """Initialize the ingestion pipeline.

        Args:
            document_store: DocumentStore instance for SQLite operations
            embedder: Embedder instance for computing vectors
            differ: Differ instance for change detection
            vector_store_path: Path to LanceDB directory
        """
        self.document_store = document_store
        self.embedder = embedder
        self.differ = differ
        self.vector_store_path = Path(vector_store_path)

    def ingest(
        self, adapter: BaseAdapter, domain_chunker: BaseDomain
    ) -> dict[str, int]:
        """Ingest content from an adapter, orchestrating the full pipeline.

        Algorithm:
        1. Register adapter (idempotent)
        2. For each NormalizedContent item from adapter.fetch():
           a. Look up latest version
           b. Chunk content
           c. Compute chunk hashes
           d. Diff against previous version
           e. If unchanged: update last_fetched_at only
           f. If changed: process added/removed/unchanged chunks
        3. Return summary dict

        Args:
            adapter: BaseAdapter instance providing content
            domain_chunker: BaseDomain instance for chunking

        Returns:
            Dict with keys:
            - sources_processed: Number of sources processed
            - chunks_added: Total chunks added across all sources
            - chunks_removed: Total chunks removed across all sources
            - chunks_unchanged: Total chunks that remained unchanged
        """
        # Register adapter (idempotent)
        adapter.register(self.document_store)

        # Open LanceDB connection
        db = lancedb.connect(str(self.vector_store_path))

        # Statistics
        sources_processed = 0
        chunks_added_total = 0
        chunks_removed_total = 0
        chunks_unchanged_total = 0

        # Iterate over normalized content from adapter
        for content in adapter.fetch(""):
            sources_processed += 1

            # Look up latest version for this source
            prev_version = self.document_store.get_latest_version(content.source_id)

            # Chunk the current content
            chunks = domain_chunker.chunk(content)

            # Compute current chunk hashes
            curr_chunk_hashes = {chunk.chunk_hash for chunk in chunks}

            # Get previous version data (if exists)
            prev_markdown = prev_version.markdown if prev_version else None
            prev_chunk_hashes = set(prev_version.chunk_hashes) if prev_version else None

            # Run the differ
            diff_result = self.differ.diff(
                prev_markdown, content.markdown, prev_chunk_hashes, curr_chunk_hashes
            )

            # Case 1: Content unchanged - just update last_fetched_at, skip writes
            if not diff_result.changed:
                # Update last_fetched_at to track when we last checked this source
                self.document_store.update_last_fetched_at(content.source_id)
                chunks_unchanged_total += len(chunks)
                continue

            # Case 2: Content changed - process added/removed/unchanged chunks
            # Register source if new
            if prev_version is None:
                self.document_store.register_source(
                    source_id=content.source_id,
                    adapter_id=adapter.adapter_id,
                    domain=adapter.domain,
                    origin_ref=content.structural_hints.file_path or content.source_id,
                )

            # Determine version number
            new_version = (prev_version.version + 1) if prev_version else 1

            # Create source version
            fetch_timestamp = datetime.now(timezone.utc).isoformat()
            self.document_store.create_source_version(
                source_id=content.source_id,
                version=new_version,
                markdown=content.markdown,
                chunk_hashes=[chunk.chunk_hash for chunk in chunks],
                adapter_id=adapter.adapter_id,
                normalizer_version=content.normalizer_version,
                fetch_timestamp=fetch_timestamp,
            )

            # Filter to added chunks only (need re-embedding)
            added_chunks = [
                c for c in chunks if c.chunk_hash in diff_result.added_hashes
            ]

            # Embed added chunks
            chunk_contents = [c.content for c in added_chunks]
            vectors = self.embedder.embed(chunk_contents) if chunk_contents else []

            # Validate all embeddings for correct dimension and finite values
            expected_dim = self.embedder.dimension
            for i, vector in enumerate(vectors):
                try:
                    validate_embedding_dimension(vector, expected_dim)
                except ValueError as e:
                    raise ValueError(
                        f"Embedding validation failed for chunk {i} (hash: {added_chunks[i].chunk_hash}): {e}"
                    ) from e

            # Build LineageRecord for each added chunk
            lineage_records: list[LineageRecord] = []
            for added_chunk in added_chunks:
                lineage = LineageRecord(
                    chunk_hash=added_chunk.chunk_hash,
                    source_id=content.source_id,
                    source_version_id=new_version,  # Use version number, not rowid
                    adapter_id=adapter.adapter_id,
                    domain=adapter.domain,
                    normalizer_version=content.normalizer_version,
                    embedding_model_id=self.embedder.model_id,
                )
                lineage_records.append(lineage)

            # Write chunks + lineage to SQLite
            if added_chunks:
                self.document_store.write_chunks(added_chunks, lineage_records)

            # Write vectors to LanceDB (get or create table)
            if vectors:
                # Build chunk vector data as dicts for LanceDB (enum -> string)
                chunk_vector_dicts = []
                for added_chunk, vector in zip(added_chunks, vectors):
                    # Validate using ChunkVector schema to ensure field validators run
                    chunk_vector = ChunkVector(
                        chunk_hash=added_chunk.chunk_hash,
                        content=added_chunk.content,
                        vector=vector,
                        domain=adapter.domain,  # Pass enum directly
                        source_id=content.source_id,
                        source_version=new_version,
                        created_at=fetch_timestamp,
                    )
                    # Convert to dict with enum values serialized
                    chunk_vector_dicts.append({
                        "chunk_hash": chunk_vector.chunk_hash,
                        "content": chunk_vector.content,
                        "vector": chunk_vector.vector,
                        "domain": chunk_vector.domain.value,  # Convert enum to string
                        "source_id": chunk_vector.source_id,
                        "source_version": chunk_vector.source_version,
                        "created_at": chunk_vector.created_at,
                    })

                # Create or append to table
                # Check if table exists to avoid broad exception handling
                existing_tables = db.list_tables().tables
                if "chunk_vectors" in existing_tables:
                    table = db.open_table("chunk_vectors")
                    table.add(chunk_vector_dicts)
                else:
                    # Build schema with embedder's actual dimension
                    schema = pa.schema([
                        ("chunk_hash", pa.string()),
                        ("content", pa.string()),
                        ("vector", pa.list_(pa.float32(), self.embedder.dimension)),
                        ("domain", pa.string()),
                        ("source_id", pa.string()),
                        ("source_version", pa.int32()),
                        ("created_at", pa.string()),
                    ])
                    db.create_table("chunk_vectors", data=chunk_vector_dicts, schema=schema)

            # Retire removed chunks
            if diff_result.removed_hashes:
                self.document_store.retire_chunks(diff_result.removed_hashes)

                # Remove from LanceDB (if table exists)
                existing_tables = db.list_tables().tables
                if "chunk_vectors" in existing_tables:
                    table = db.open_table("chunk_vectors")
                    # Build proper SQL IN clause with quoted hash values
                    quoted_hashes = ", ".join(f"'{h}'" for h in diff_result.removed_hashes)
                    table.delete(f"chunk_hash IN ({quoted_hashes})")

            # Write sync log
            if added_chunks:
                added_hashes = [c.chunk_hash for c in added_chunks]
                self.document_store.write_sync_log(added_hashes)

            if diff_result.removed_hashes:
                removed_list = list(diff_result.removed_hashes)
                self.document_store.delete_sync_log(removed_list)

            # Update statistics
            chunks_added_total += len(added_chunks)
            chunks_removed_total += len(diff_result.removed_hashes)
            chunks_unchanged_total += len(diff_result.unchanged_hashes)

        return {
            "sources_processed": sources_processed,
            "chunks_added": chunks_added_total,
            "chunks_removed": chunks_removed_total,
            "chunks_unchanged": chunks_unchanged_total,
        }
