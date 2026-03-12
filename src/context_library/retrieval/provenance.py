"""Traces chunk provenance via SQLite: version diffs, source history, lineage chains."""

from context_library.storage.document_store import DocumentStore
from context_library.storage.models import (
    ChunkProvenance,
    SourceTimeline,
    VersionDiff,
)


def get_version_diff(
    document_store: DocumentStore,
    source_id: str,
    from_version: int,
    to_version: int,
) -> VersionDiff:
    """Retrieve the diff between two versions of a source.

    Delegates to DocumentStore's get_version_diff method which computes hash-set
    differences between source versions. The returned VersionDiff contains the sets
    of added, removed, and unchanged chunk hashes.

    Args:
        document_store: The document store instance.
        source_id: The source identifier.
        from_version: The starting version number.
        to_version: The ending version number.

    Returns:
        A VersionDiff with added_hashes, removed_hashes, and unchanged_hashes.

    Raises:
        ValueError: If the source doesn't exist or version numbers are invalid.
    """
    diff = document_store.get_version_diff(source_id, from_version, to_version)
    return diff


def get_source_timeline(
    document_store: DocumentStore,
    source_id: str,
) -> SourceTimeline:
    """Retrieve the complete version timeline for a source.

    Fetches all versions of a source in chronological order and wraps them in
    a SourceTimeline.

    Args:
        document_store: The document store instance.
        source_id: The source identifier.

    Returns:
        A SourceTimeline with all versions for the source ordered chronologically.

    Raises:
        ValueError: If the source doesn't exist.
    """
    versions = document_store.get_version_history(source_id)
    if not versions:
        raise ValueError(f"Source '{source_id}' does not exist or has no versions")
    return SourceTimeline(source_id=source_id, versions=tuple(versions))


def trace_chunk_provenance(
    document_store: DocumentStore,
    chunk_hash: str,
    source_id: str | None = None,
) -> ChunkProvenance:
    """Trace complete provenance for a chunk.

    Combines chunk metadata, lineage record, source information, and version chain
    to provide full provenance tracing. The version_chain walks up the parent_chunk_hash
    ancestry from the current chunk to its oldest ancestor, ordered oldest-first.

    Args:
        document_store: The document store instance.
        chunk_hash: The SHA-256 hash of the chunk to trace.
        source_id: Optional source_id filter for lineage lookup. If provided, lineage
                   is fetched specifically for this source.

    Returns:
        A ChunkProvenance with complete tracing information.

    Raises:
        ValueError: If the chunk doesn't exist, lineage is missing, or source info
                    cannot be retrieved.
    """
    # Fetch the chunk by hash, scoped by source_id when provided to ensure consistency
    # with lineage and version_chain lookups (avoiding cross-source dedup mixing)
    chunk = document_store.get_chunk_by_hash(chunk_hash, source_id)
    if chunk is None:
        raise ValueError(
            f"Chunk with hash {chunk_hash} not found"
            + (f" in source {source_id}" if source_id else "")
        )

    # Fetch lineage record
    lineage = document_store.get_lineage(chunk_hash, source_id)
    if lineage is None:
        raise ValueError(
            f"Lineage record not found for chunk {chunk_hash}"
            + (f" with source_id {source_id}" if source_id else "")
        )

    # Fetch source information (origin_ref and adapter_type)
    source_info = document_store.get_source_info(lineage.source_id)
    if source_info is None:
        raise ValueError(
            f"Source info not found for source_id {lineage.source_id}"
        )

    # Fetch version chain (returned by DocumentStore in oldest-ancestor-first order)
    # Scope by source_id to correctly handle cross-source chunks with identical hashes
    version_chain_list = document_store.get_chunk_version_chain(chunk_hash, lineage.source_id)
    version_chain = tuple(version_chain_list)

    # Validate that version chain is non-empty (chunk must appear in its own version chain)
    if not version_chain:
        raise ValueError(
            f"Version chain for chunk {chunk_hash} cannot be empty; "
            f"chunk must appear in its own version chain"
        )

    return ChunkProvenance(
        chunk=chunk,
        lineage=lineage,
        source_origin_ref=source_info.origin_ref,
        adapter_type=source_info.adapter_type,
        version_chain=version_chain,
    )
