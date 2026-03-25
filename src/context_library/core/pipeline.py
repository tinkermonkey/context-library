"""Orchestrates the full ingestion pipeline: fetch → normalize → diff → chunk → embed → store."""

import logging
import threading
from datetime import datetime, timezone

from context_library.core.differ import Differ
from context_library.core.embedder import Embedder
from context_library.core.exceptions import (
    ChunkingError,
    EmbeddingError,
    StorageError,
    AllSourcesFailedError,
)
from context_library.adapters.base import BaseAdapter, PartialFetchError, AllEndpointsFailedError
from context_library.adapters.vcard import ContactIDCollisionError
from context_library.domains.base import BaseDomain
from context_library.domains.registry import get_domain_chunker as _get_domain_chunker
from context_library.storage.document_store import DocumentStore
from context_library.storage.models import LineageRecord, PollStrategy
from context_library.storage.validators import validate_embedding_dimension
from context_library.storage.vector_store import ChunkVectorData, VectorStore

logger = logging.getLogger(__name__)


class IngestionPipeline:
    """Orchestrates the full ingestion pipeline from adapter through storage.

    Coordinates fetching, normalizing, chunking, embedding, and storing of content
    across both SQLite (DocumentStore) and the vector store.

    Key responsibilities:
    - Register adapters with the document store (idempotent)
    - Fetch and normalize content via adapters
    - Detect changes via the Differ
    - Chunk content via domain-specific chunkers
    - Embed new/modified chunks
    - Write to SQLite and vector store sequentially with per-source error isolation
    - Retire deleted chunks from both stores

    Error handling:
    - Per-source failures are caught and logged; pipeline continues with next source
    - If a source's write to SQLite succeeds but vector store fails, stores
      may be left inconsistent. The vector store can be rebuilt from SQLite.
    """

    def __init__(
        self,
        document_store: DocumentStore,
        embedder: Embedder,
        differ: Differ,
        vector_store: VectorStore,
    ) -> None:
        """Initialize the ingestion pipeline.

        Args:
            document_store: DocumentStore instance for SQLite operations
            embedder: Embedder instance for computing vectors
            differ: Differ instance for change detection
            vector_store: VectorStore instance for vector operations
        """
        self.document_store = document_store
        self.embedder = embedder
        self.differ = differ
        self.vector_store = vector_store
        self.vector_store.initialize(self.embedder.dimension)

        # Per-source locks prevent two concurrent ingest() calls from processing
        # the same source_id simultaneously. Without this, both callers can pass
        # the get_latest_version/diff check before either commits, resulting in
        # duplicate versions with identical content being written.
        # Use a bounded LRU cache to prevent unbounded memory growth in long-running servers.
        # The cache size of 128 is conservative; typical workloads will have far fewer
        # concurrent unique sources. When a source falls out of the LRU cache, its lock
        # is garbage collected. The next ingest() for that source will create a new lock.
        self._source_locks_cache: dict[str, threading.Lock] = {}
        self._source_locks_mutex = threading.Lock()
        self._source_locks_max_size = 128

    def _get_source_lock(self, source_id: str) -> threading.Lock:
        """Return the per-source lock for source_id, creating it if needed.

        Uses an LRU eviction policy to prevent unbounded dictionary growth.
        When the cache reaches max_size and a new source is requested, the least
        recently used lock is discarded. This is safe because:
        - Locks are only needed to protect concurrent ingest() calls for the same source
        - If a source's lock is evicted and then immediately re-ingested, a new lock
          is created, which is acceptable (slight race window, but no data loss)
        - In typical usage, the same sources are re-ingested regularly
        """
        with self._source_locks_mutex:
            if source_id in self._source_locks_cache:
                lock = self._source_locks_cache[source_id]
                # Move to end (mark as most recently used) by deleting and re-adding
                del self._source_locks_cache[source_id]
                self._source_locks_cache[source_id] = lock
                return lock

            # Create new lock
            lock = threading.Lock()

            # Evict least recently used if cache is full
            if len(self._source_locks_cache) >= self._source_locks_max_size:
                # Pop the first item (least recently used in insertion order)
                # In Python 3.10+, regular dicts maintain insertion order
                first_key = next(iter(self._source_locks_cache))
                del self._source_locks_cache[first_key]

            self._source_locks_cache[source_id] = lock
            return lock

    def ingest(
        self, adapter: BaseAdapter, domain_chunker: BaseDomain, source_ref: str = ""
    ) -> dict:
        """Ingest content from an adapter, orchestrating the full pipeline.

        Algorithm:
        1. Register adapter (idempotent)
        2. For each NormalizedContent item from adapter.fetch(source_ref):
           a. Look up latest version
           b. Chunk content
           c. Compute chunk hashes
           d. Diff against previous version
           e. If unchanged: update last_fetched_at only
           f. If changed: process added/removed/unchanged chunks
        3. Return summary dict with error tracking

        Consistency model:
        - Each source is processed independently with per-source error isolation
        - Writes to SQLite and LanceDB are sequential, not transactional
        - If a source fails after SQLite writes but before vector store writes, the stores
          may be inconsistent for that source. This is tracked in store_consistency.
          The vector store can be fully rebuilt from SQLite via external sync tooling.
        - Failed sources are logged and skipped; pipeline continues with next source

        Args:
            adapter: BaseAdapter instance providing content
            domain_chunker: BaseDomain instance for chunking
            source_ref: Source-specific reference (e.g., directory path, email address).
                       Passed to adapter.fetch() to enable incremental ingestion and
                       source-specific filtering. Defaults to empty string for adapters
                       that fetch all sources.

        Returns:
            Dict with keys:
            - sources_processed: Number of sources successfully processed
            - sources_failed: Number of sources that failed processing
            - chunks_added: Total chunks added across all sources
            - chunks_removed: Total chunks removed across all sources
            - chunks_unchanged: Total chunks that remained unchanged
            - errors: List of error dicts with keys:
                - source_id: Source that failed
                - error_type: Type of error (EmbeddingError, StorageError, etc.)
                - message: Error message
                - chunk_hash: (Optional) Hash of affected chunk (for EmbeddingError)
                - chunk_index: (Optional) Index of affected chunk (for EmbeddingError)
                - store_type: (Optional) Type of store that failed (for StorageError)
                - inconsistent: (Optional) Whether inconsistency was detected (for StorageError)
            - store_consistency: Dict mapping source_id to status:
                - "inconsistent": SQLite write succeeded but vector store failed
                - "error": Storage operation failed
                - "success": All writes succeeded
        """
        # Register adapter (idempotent)
        adapter.register(self.document_store)

        # Statistics
        sources_processed = 0
        sources_failed = 0
        chunks_added_total = 0
        chunks_removed_total = 0
        chunks_unchanged_total = 0
        errors: list[dict] = []
        store_consistency: dict[str, str] = {}

        # Iterate over normalized content from adapter, passing source_ref for incremental ingestion
        try:
            for content in adapter.fetch(source_ref):
                try:
                    sources_processed += 1

                    # Acquire the per-source lock before reading the latest version.
                    # This prevents two concurrent ingest() calls from both passing the
                    # diff check for the same source and creating duplicate versions.
                    with self._get_source_lock(content.source_id):
                        # Resolve domain: per-content override takes precedence over adapter domain.
                        # This allows adapters to yield content destined for multiple domains
                        # (e.g. AppleMusicLibraryAdapter produces both DOCUMENTS and EVENTS).
                        effective_domain = content.domain if content.domain is not None else adapter.domain

                        # Resolve domain chunker: reuse the caller-supplied chunker when the
                        # content's domain matches the adapter's primary domain (avoids a
                        # registry lookup on the common path); resolve from registry otherwise.
                        if effective_domain == adapter.domain:
                            effective_chunker = domain_chunker
                        else:
                            effective_chunker = _get_domain_chunker(effective_domain)

                        # Look up latest version for this source
                        prev_version = self.document_store.get_latest_version(content.source_id)

                        # Chunk the current content
                        chunks = effective_chunker.chunk(content)

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
                            poll_strategy = getattr(adapter, 'poll_strategy', PollStrategy.PULL)

                            self.document_store.register_source(
                                source_id=content.source_id,
                                adapter_id=adapter.adapter_id,
                                domain=effective_domain,
                                origin_ref=content.structural_hints.file_path or content.source_id,
                                poll_strategy=poll_strategy,
                            )

                        # Create source version with atomically assigned version number.
                        # create_next_source_version computes MAX(version)+1 inside the
                        # write lock, preventing UNIQUE constraint violations when
                        # concurrent requests race to create the next version.
                        fetch_timestamp = datetime.now(timezone.utc).isoformat()
                        _rowid, new_version = self.document_store.create_next_source_version(
                            source_id=content.source_id,
                            markdown=content.markdown,
                            chunk_hashes=[chunk.chunk_hash for chunk in chunks],
                            adapter_id=adapter.adapter_id,
                            normalizer_version=content.normalizer_version,
                            fetch_timestamp=fetch_timestamp,
                        )

                        # Separate added and unchanged chunks
                        added_chunks = [
                            c for c in chunks if c.chunk_hash in diff_result.added_hashes
                        ]
                        unchanged_chunks = [
                            c for c in chunks if c.chunk_hash in diff_result.unchanged_hashes
                        ]

                        # Embed added chunks with context headers for semantic enrichment
                        # Context header is prepended only for embedding, not stored in content field
                        chunk_contents_for_embedding = []
                        for c in added_chunks:
                            text = c.content
                            if c.context_header:
                                text = f"{c.context_header}\n\n{text}"
                            chunk_contents_for_embedding.append(text)

                        vectors = self.embedder.embed(chunk_contents_for_embedding) if chunk_contents_for_embedding else []

                        # Validate all embeddings for correct dimension and finite values
                        expected_dim = self.embedder.dimension
                        for i, vector in enumerate(vectors):
                            try:
                                validate_embedding_dimension(vector, expected_dim)
                            except ValueError as e:
                                raise EmbeddingError(
                                    f"Embedding validation failed for chunk {i} (hash: {added_chunks[i].chunk_hash}): {e}",
                                    chunk_hash=added_chunks[i].chunk_hash,
                                    chunk_index=i,
                                ) from e

                        # Build LineageRecord for each added chunk
                        added_lineage_records: list[LineageRecord] = []
                        for added_chunk in added_chunks:
                            lineage = LineageRecord(
                                chunk_hash=added_chunk.chunk_hash,
                                source_id=content.source_id,
                                source_version_id=new_version,  # Use version number (not rowid), for FK to source_versions.version
                                adapter_id=adapter.adapter_id,
                                domain=effective_domain,
                                normalizer_version=content.normalizer_version,
                                embedding_model_id=self.embedder.model_id,
                            )
                            added_lineage_records.append(lineage)

                        # Build LineageRecord for each unchanged chunk
                        # Unchanged chunks are re-written to the new version to be queryable via get_chunks_by_source()
                        unchanged_lineage_records: list[LineageRecord] = []
                        for unchanged_chunk in unchanged_chunks:
                            # Fetch original lineage to preserve the embedding model that created the vectors
                            # (not the current embedder's model, which may have changed since the chunk was created)
                            # Pass source_id to scope lookup correctly in case of cross-source dedup
                            original_lineage = self.document_store.get_lineage(
                                unchanged_chunk.chunk_hash, source_id=content.source_id
                            )
                            original_embedding_model = (
                                original_lineage.embedding_model_id
                                if original_lineage
                                else self.embedder.model_id
                            )

                            lineage = LineageRecord(
                                chunk_hash=unchanged_chunk.chunk_hash,
                                source_id=content.source_id,
                                source_version_id=new_version,  # Same version as added chunks
                                adapter_id=adapter.adapter_id,
                                domain=effective_domain,
                                normalizer_version=content.normalizer_version,
                                embedding_model_id=original_embedding_model,  # Use original embedding model
                            )
                            unchanged_lineage_records.append(lineage)

                        # Write all chunks (both added and unchanged) + lineage to SQLite
                        all_chunks_to_write = added_chunks + unchanged_chunks
                        all_lineage_records = added_lineage_records + unchanged_lineage_records

                        sqlite_write_succeeded = False
                        if all_chunks_to_write:
                            try:
                                self.document_store.write_chunks(all_chunks_to_write, all_lineage_records)
                                sqlite_write_succeeded = True
                                # Record pending sync operations before attempting LanceDB writes
                                # Only for added chunks (unchanged ones already have vectors)
                                added_hashes = [c.chunk_hash for c in added_chunks]
                                if added_hashes:
                                    self.document_store.write_sync_log(added_hashes)
                            except Exception as e:
                                raise StorageError(
                                    f"Failed to write chunks to SQLite for source '{content.source_id}': {e}",
                                    store_type="sqlite",
                                    inconsistent=False,
                                ) from e

                        # Retire removed chunks from SQLite first
                        # Note: retire chunks from the old version (prev_version), not the new one
                        if diff_result.removed_hashes:
                            old_version = prev_version.version if prev_version else 1
                            self.document_store.retire_chunks(set(diff_result.removed_hashes), content.source_id, old_version)
                            removed_list = list(diff_result.removed_hashes)
                            # Record pending delete operations before attempting LanceDB deletes
                            self.document_store.delete_sync_log(removed_list)

                        # Write vectors to vector store
                        # If this fails and SQLite write succeeded, mark as inconsistent
                        if vectors:
                            try:
                                # Build chunk vector data as dicts (enum -> string)
                                chunk_vector_dicts = []
                                for added_chunk, vector in zip(added_chunks, vectors):
                                    # Validate using ChunkVectorData schema to ensure field validators run
                                    chunk_vector = ChunkVectorData(
                                        chunk_hash=added_chunk.chunk_hash,
                                        content=added_chunk.content,
                                        vector=vector,
                                        domain=effective_domain,
                                        source_id=content.source_id,
                                        source_version=new_version,
                                        created_at=fetch_timestamp,
                                    )
                                    chunk_vector_dicts.append({
                                        "chunk_hash": chunk_vector.chunk_hash,
                                        "content": chunk_vector.content,
                                        "vector": chunk_vector.vector,
                                        "domain": chunk_vector.domain.value,
                                        "source_id": chunk_vector.source_id,
                                        "source_version": chunk_vector.source_version,
                                        "created_at": chunk_vector.created_at,
                                    })

                                self.vector_store.add_vectors(chunk_vector_dicts)
                            except Exception as e:
                                inconsistency_detected = bool(sqlite_write_succeeded and all_chunks_to_write)
                                if inconsistency_detected:
                                    logger.warning(
                                        f"CRITICAL: SQLite write succeeded but vector store write failed for source "
                                        f"'{content.source_id}'. Stores may be inconsistent. "
                                        f"Recovery: Use sync logs to rebuild vector store. Error: {e}"
                                    )
                                raise StorageError(
                                    f"Failed to write vectors for source '{content.source_id}': {e}",
                                    store_type="vector_store",
                                    inconsistent=inconsistency_detected,
                                ) from e

                        # Remove vectors for deleted chunks
                        if diff_result.removed_hashes:
                            try:
                                self.vector_store.delete_vectors(set(diff_result.removed_hashes))
                            except Exception as e:
                                logger.warning(
                                    f"Failed to delete chunks from vector store for source '{content.source_id}': {e}"
                                )
                                # Don't raise here, as the sync log already has the delete operation recorded

                        # Update statistics
                        chunks_added_total += len(added_chunks)
                        chunks_removed_total += len(diff_result.removed_hashes)
                        chunks_unchanged_total += len(diff_result.unchanged_hashes)

                        # Mark store consistency as successful for this source
                        store_consistency[content.source_id] = "success"

                except ChunkingError as e:
                    # Handle chunking errors (domain-specific parser/processing failures)
                    logger.error(f"Chunking error for source '{content.source_id}': {e}", exc_info=True)
                    sources_processed -= 1
                    sources_failed += 1
                    errors.append({
                        "source_id": content.source_id,
                        "error_type": "ChunkingError",
                        "message": str(e),
                        "source_id_attr": e.source_id,
                    })
                    store_consistency[content.source_id] = "error"
                    continue
                except EmbeddingError as e:
                    # Handle embedding-specific errors
                    logger.error(f"Embedding error for source '{content.source_id}': {e}", exc_info=True)
                    sources_processed -= 1
                    sources_failed += 1
                    errors.append({
                        "source_id": content.source_id,
                        "error_type": "EmbeddingError",
                        "message": str(e),
                        "chunk_hash": e.chunk_hash,
                        "chunk_index": e.chunk_index,
                    })
                    store_consistency[content.source_id] = "error"
                    continue
                except StorageError as e:
                    # Handle storage-specific errors
                    logger.error(f"Storage error for source '{content.source_id}': {e}", exc_info=True)
                    sources_processed -= 1
                    sources_failed += 1
                    consistency_status = "inconsistent" if e.inconsistent else "error"
                    store_consistency[content.source_id] = consistency_status
                    errors.append({
                        "source_id": content.source_id,
                        "error_type": "StorageError",
                        "message": str(e),
                        "store_type": e.store_type,
                        "inconsistent": e.inconsistent,
                    })
                    continue
                except Exception as e:
                    # Handle any other unexpected errors
                    logger.error(f"Unexpected error processing source '{content.source_id}': {e}", exc_info=True)
                    sources_processed -= 1
                    sources_failed += 1
                    errors.append({
                        "source_id": content.source_id,
                        "error_type": type(e).__name__,
                        "message": str(e),
                    })
                    store_consistency[content.source_id] = "error"
                    continue
        except PartialFetchError as e:
            # Some endpoints failed, others succeeded. Log the failure and record it in errors.
            # This allows the pipeline to continue with other adapters while still notifying
            # callers that the data is incomplete.
            logger.warning(
                f"Partial fetch failure from adapter {adapter.adapter_id}: "
                f"{len(e.failed_endpoints)}/{e.total_endpoints} endpoint(s) failed. "
                f"Affected endpoints: {', '.join(e.failed_endpoints)}. "
                f"Continuing with data from successful endpoints."
            )
            errors.append({
                "source_id": None,  # Adapter-level failure, not source-level
                "error_type": "PartialFetchError",
                "message": str(e),
                "failed_endpoints": e.failed_endpoints,
            })
            # Don't raise; successfully-yielded data has been processed
        except AllEndpointsFailedError as e:
            # All endpoints failed; adapter yielded no data
            logger.error(
                f"All endpoints failed for adapter {adapter.adapter_id}: {e}"
            )
            errors.append({
                "source_id": None,  # Adapter-level failure, not source-level
                "error_type": "AllEndpointsFailedError",
                "message": str(e),
            })
            sources_failed += 1
            # Continue to next adapter; this adapter yielded no data
        except ContactIDCollisionError as e:
            # Contact ID collision: two distinct contacts have identical contact_id
            # Log the collision with detailed context for debugging
            logger.error(
                f"Contact ID collision in adapter {adapter.adapter_id}: {e}"
            )
            errors.append({
                "source_id": None,  # Adapter-level failure, not source-level
                "error_type": "ContactIDCollisionError",
                "message": str(e),
                "collision_contact_id": e.contact_id,
                "first_contact_name": e.first_contact_name,
                "first_contact_file": str(e.first_contact_file),
                "second_contact_name": e.second_contact_name,
                "second_contact_file": str(e.second_contact_file),
            })
            sources_failed += 1
            # Continue to next adapter; collision prevents further processing


        # Raise if all sources failed
        if sources_failed > 0 and sources_processed == 0:
            raise AllSourcesFailedError(
                f"All sources failed to process. {sources_failed} sources had errors. "
                f"Check errors list for details."
            )

        return {
            "sources_processed": sources_processed,
            "sources_failed": sources_failed,
            "chunks_added": chunks_added_total,
            "chunks_removed": chunks_removed_total,
            "chunks_unchanged": chunks_unchanged_total,
            "errors": errors,
            "store_consistency": store_consistency,
        }
