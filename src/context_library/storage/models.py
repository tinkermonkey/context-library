"""Shared enumeration types and Pydantic data models for pipeline data flow.

This module contains:
- Domain enum for domain classification across adapters, storage, and chunking
- Pydantic models that flow through the pipeline (normalization -> chunking -> embedding)
- All models use frozen=True for immutability and content-addressed identity
"""

import hashlib
import re
from enum import Enum
from typing import Annotated, ClassVar

from pydantic import AfterValidator, BaseModel, ConfigDict, field_validator

from context_library.storage.validators import validate_iso8601_timestamp


class EventType(str, Enum):
    """Fixed set of filesystem event types for watcher operations.

    Represents the type of filesystem change detected by file watchers.
    Enforces valid event type values at the Python level.
    """

    CREATED = "created"
    MODIFIED = "modified"
    DELETED = "deleted"


class Domain(str, Enum):
    """Fixed set of domain types for vector metadata.

    Used across SQLite schema, vector store, and domain modules.
    """

    MESSAGES = "messages"
    NOTES = "notes"
    EVENTS = "events"
    TASKS = "tasks"


class ChunkType(str, Enum):
    """Fixed set of chunk types for content classification.

    Aligns with SQLite schema CHECK constraint on chunks.chunk_type.
    Enforces valid chunk type values at the Python level before database insertion.
    """

    STANDARD = "standard"
    OVERSIZED = "oversized"
    TABLE_PART = "table_part"
    CODE = "code"
    TABLE = "table"


class PollStrategy(str, Enum):
    """Fixed set of polling strategies for source ingestion.

    Aligns with SQLite schema CHECK constraint on sources.poll_strategy.
    Enforces valid poll strategy values at the Python level before database insertion.
    """

    PUSH = "push"
    PULL = "pull"
    WEBHOOK = "webhook"


def _validate_sha256_hex(value: str) -> str:
    """Validate that a string is a valid SHA-256 hex hash (64 lowercase hex chars).

    Args:
        value: The string to validate

    Returns:
        The validated string if valid

    Raises:
        ValueError: If the string is not a valid SHA-256 hex hash
    """
    if not re.match(r"^[a-f0-9]{64}$", value):
        raise ValueError(
            f"chunk_hash must be a valid SHA-256 hex string (64 chars), got: {value}"
        )
    return value


# Type alias for SHA-256 hashes with validation
Sha256Hash = Annotated[str, AfterValidator(_validate_sha256_hex)]


class StructuralHints(BaseModel):
    """Structural metadata extracted from normalized content.

    Captures formatting characteristics (headings, lists, tables) and filesystem metadata
    for content-specific chunking strategies and filtering.

    extra_metadata is a domain-specific contract between adapters and chunkers:
    - Adapters populate it with domain-specific metadata according to their domain
    - Chunkers extract and validate it according to their domain's expectations
    - For EmailMessages domain: extra_metadata must be deserializable to MessageMetadata
    - For Events domain: extra_metadata must be deserializable to EventMetadata
    - For Tasks domain: extra_metadata must be deserializable to TaskMetadata
    - For Notes domain: extra_metadata is propagated as-is to domain_metadata in chunks

    Note: This field uses dict[str, object] to allow flexible domain-specific contracts.
    Type safety for specific domains is achieved through validation in domain chunkers
    (e.g., MessageMetadata(**meta_dict) with ValidationError handling).
    """

    model_config = ConfigDict(frozen=True)

    has_headings: bool
    has_lists: bool
    has_tables: bool
    natural_boundaries: tuple[int, ...]
    file_path: str | None = None
    modified_at: str | None = None
    file_size_bytes: int | None = None
    extra_metadata: dict[str, object] | None = None

    @field_validator("modified_at")
    @classmethod
    def validate_modified_at(cls, value: str | None) -> str | None:
        """Validate that modified_at is a valid ISO 8601 timestamp if provided."""
        if value is not None:
            validate_iso8601_timestamp(value)
        return value


class MessageMetadata(BaseModel):
    """Message metadata for email and messaging domains.

    Captures email headers and thread context for message-based chunking and threading.
    All timestamps must be valid ISO 8601 format.

    Invariants:
    - is_thread_root and in_reply_to are mutually exclusive
    - thread_id, message_id, and sender must be non-empty strings
    """

    model_config = ConfigDict(frozen=True)

    thread_id: str
    message_id: str
    sender: str
    recipients: tuple[str, ...]
    timestamp: str
    in_reply_to: str | None
    subject: str | None
    is_thread_root: bool

    @field_validator("thread_id")
    @classmethod
    def validate_thread_id(cls, value: str) -> str:
        """Validate that thread_id is not empty."""
        if not value:
            raise ValueError("thread_id must be a non-empty string")
        return value

    @field_validator("message_id")
    @classmethod
    def validate_message_id(cls, value: str) -> str:
        """Validate that message_id is not empty."""
        if not value:
            raise ValueError("message_id must be a non-empty string")
        return value

    @field_validator("sender")
    @classmethod
    def validate_sender(cls, value: str) -> str:
        """Validate that sender is not empty."""
        if not value:
            raise ValueError("sender must be a non-empty string")
        return value

    @field_validator("timestamp")
    @classmethod
    def validate_timestamp(cls, value: str) -> str:
        """Validate that timestamp is a valid ISO 8601 timestamp."""
        validate_iso8601_timestamp(value)
        return value

    def model_post_init(self, __context) -> None:
        """Validate MessageMetadata invariants after model construction.

        Enforces:
        - is_thread_root=True and in_reply_to must be mutually exclusive
        """
        if self.is_thread_root and self.in_reply_to is not None:
            raise ValueError(
                "is_thread_root=True and in_reply_to must be mutually exclusive. "
                f"Got is_thread_root={self.is_thread_root}, in_reply_to={self.in_reply_to!r}"
            )


class TaskMetadata(BaseModel):
    """Task metadata extracted by task-source adapters.

    Captures task identification, status, scheduling, and collaboration context
    for task-based chunking and filtering. Conforms to the architecture specification
    for task domain metadata.

    The status field uses an immutable frozenset of allowed values, enforcing
    a fixed set of valid statuses that cannot be mutated at runtime.

    Invariants:
    - task_id, title, and source_type must be non-empty strings
    - status must be a valid string from the allowed task status values (open, completed, cancelled, in-progress)
    - due_date and date_first_observed must be valid ISO 8601 timestamps if provided
    - priority if provided must be in range 1-4
    """

    # Allowed status values - immutable to prevent runtime mutation of validation invariant
    ALLOWED_STATUSES: ClassVar[frozenset[str]] = frozenset({"open", "completed", "cancelled", "in-progress"})

    model_config = ConfigDict(frozen=True)

    task_id: str
    status: str
    title: str
    due_date: str | None = None
    priority: int | None = None
    dependencies: tuple[str, ...] = ()
    collaborators: tuple[str, ...] = ()
    date_first_observed: str
    source_type: str

    @field_validator("task_id")
    @classmethod
    def validate_task_id(cls, value: str) -> str:
        """Validate that task_id is not empty."""
        if not value:
            raise ValueError("task_id must be a non-empty string")
        return value

    @field_validator("status")
    @classmethod
    def validate_status(cls, value: str) -> str:
        """Validate that status is in the allowed task status values."""
        if value not in cls.ALLOWED_STATUSES:
            raise ValueError(
                f"status must be one of {sorted(cls.ALLOWED_STATUSES)}, got: {value!r}"
            )
        return value

    @field_validator("title")
    @classmethod
    def validate_title(cls, value: str) -> str:
        """Validate that title is not empty."""
        if not value:
            raise ValueError("title must be a non-empty string")
        return value

    @field_validator("source_type")
    @classmethod
    def validate_source_type(cls, value: str) -> str:
        """Validate that source_type is not empty."""
        if not value:
            raise ValueError("source_type must be a non-empty string")
        return value

    @field_validator("priority")
    @classmethod
    def validate_priority(cls, value: int | None) -> int | None:
        """Validate that priority is in the range 1-4 if provided."""
        if value is not None and (value < 1 or value > 4):
            raise ValueError(f"priority must be in range 1-4, got: {value}")
        return value

    @field_validator("due_date")
    @classmethod
    def validate_due_date(cls, value: str | None) -> str | None:
        """Validate that due_date is a valid ISO 8601 timestamp if provided."""
        if value is not None:
            validate_iso8601_timestamp(value)
        return value

    @field_validator("date_first_observed")
    @classmethod
    def validate_date_first_observed(cls, value: str) -> str:
        """Validate that date_first_observed is a valid ISO 8601 timestamp."""
        validate_iso8601_timestamp(value)
        return value


class EventMetadata(BaseModel):
    """Event metadata extracted by event-source adapters.

    Captures event identification, scheduling, and participant context
    for event-based chunking and time-aware filtering. Conforms to the architecture
    specification for event domain metadata.

    Invariants:
    - event_id, title, and source_type must be non-empty strings
    - start_date, end_date, and date_first_observed must be valid ISO 8601 timestamps if provided
    - If both start_date and end_date are present, start_date <= end_date
    - duration_minutes if provided must be non-negative

    WARNING: extra="ignore" config silently DISCARDS any fields not explicitly defined in this model.
    Extra fields are not "allowed" or "accepted"—they are silently deleted during validation.
    Domain-specific metadata like health metrics MUST be stored in the chunk's domain_metadata dict
    as those preserve all fields. Passing extra fields to EventMetadata will result in data loss.
    """

    model_config = ConfigDict(frozen=True, extra="ignore")

    event_id: str
    title: str
    start_date: str | None = None
    end_date: str | None = None
    duration_minutes: int | None = None
    host: str | None = None
    invitees: tuple[str, ...] = ()
    date_first_observed: str
    source_type: str

    @field_validator("event_id")
    @classmethod
    def validate_event_id(cls, value: str) -> str:
        """Validate that event_id is not empty."""
        if not value:
            raise ValueError("event_id must be a non-empty string")
        return value

    @field_validator("title")
    @classmethod
    def validate_title(cls, value: str) -> str:
        """Validate that title is not empty."""
        if not value:
            raise ValueError("title must be a non-empty string")
        return value

    @field_validator("source_type")
    @classmethod
    def validate_source_type(cls, value: str) -> str:
        """Validate that source_type is not empty."""
        if not value:
            raise ValueError("source_type must be a non-empty string")
        return value

    @field_validator("start_date")
    @classmethod
    def validate_start_date(cls, value: str | None) -> str | None:
        """Validate that start_date is a valid ISO 8601 timestamp if provided."""
        if value is not None:
            validate_iso8601_timestamp(value)
        return value

    @field_validator("end_date")
    @classmethod
    def validate_end_date(cls, value: str | None) -> str | None:
        """Validate that end_date is a valid ISO 8601 timestamp if provided."""
        if value is not None:
            validate_iso8601_timestamp(value)
        return value

    @field_validator("duration_minutes")
    @classmethod
    def validate_duration_minutes(cls, value: int | None) -> int | None:
        """Validate that duration_minutes is non-negative if provided."""
        if value is not None and value < 0:
            raise ValueError(f"duration_minutes must be non-negative, got: {value}")
        return value

    @field_validator("date_first_observed")
    @classmethod
    def validate_date_first_observed(cls, value: str) -> str:
        """Validate that date_first_observed is a valid ISO 8601 timestamp."""
        validate_iso8601_timestamp(value)
        return value

    def model_post_init(self, __context) -> None:
        """Validate EventMetadata invariants after model construction.

        Enforces:
        - If both start_date and end_date are present, start_date <= end_date

        Note: Uses datetime parsing for accurate ISO 8601 comparison to handle
        different timezone representations (e.g., "Z" vs "+00:00").
        """
        from datetime import datetime

        if self.start_date is not None and self.end_date is not None:
            # Parse ISO 8601 strings to datetime for correct comparison
            # (lexicographic string comparison fails with mixed timezone formats)
            try:
                start_dt = datetime.fromisoformat(self.start_date.replace("Z", "+00:00"))
                end_dt = datetime.fromisoformat(self.end_date.replace("Z", "+00:00"))
            except (ValueError, AttributeError) as e:
                # Should not happen as individual validators already checked ISO 8601 format
                raise ValueError(
                    f"Invalid ISO 8601 format in start_date or end_date: {e}"
                ) from e

            if start_dt > end_dt:
                raise ValueError(
                    f"start_date must be <= end_date when both are present. "
                    f"Got start_date={self.start_date!r}, end_date={self.end_date!r}"
                )


class NormalizedContent(BaseModel):
    """Content after adapter normalization (e.g., markdown extraction, deduplication).

    This is the input to domain chunkers. The structural_hints guide chunking strategy.
    """

    model_config = ConfigDict(frozen=True)

    markdown: str
    source_id: str
    structural_hints: StructuralHints
    normalizer_version: str


class Chunk(BaseModel):
    """A chunk of normalized content with identity, context, and metadata.

    The chunk_hash is deterministically computed from the content (excluding context header)
    using SHA-256 after whitespace normalization. This enables content-addressed deduplication
    and change detection across multiple sources.

    chunk_type is validated against a fixed set of allowed values (standard, oversized,
    table_part, code, table) to ensure consistency with SQLite schema constraints.

    cross_refs contains SHA-256 hashes of other chunks (within the same source) that are
    referenced by this chunk, enabling automatic identification and linking of related content
    within the source. All hashes are validated as SHA-256.
    """

    model_config = ConfigDict(frozen=True)

    chunk_hash: Sha256Hash
    content: str
    context_header: str | None = None
    chunk_index: int
    chunk_type: ChunkType = ChunkType.STANDARD
    domain_metadata: dict[str, object] | None = None
    cross_refs: tuple[Sha256Hash, ...] = ()


class LineageRecord(BaseModel):
    """Provenance metadata linking a chunk to its source and processing pipeline.

    Enables tracing any chunk back to its original source, version, domain, and embedding model.
    """

    model_config = ConfigDict(frozen=True)

    chunk_hash: Sha256Hash
    source_id: str
    source_version_id: int
    adapter_id: str
    domain: Domain
    normalizer_version: str
    embedding_model_id: str


class SourceVersion(BaseModel):
    """A versioned snapshot of a source's content and its chunks.

    Immutable records enable full history tracking for provenance and change detection.
    chunk_hashes is stored as a serialized tuple (in SQLite as JSON string).
    All chunk_hashes are validated as SHA-256 hex strings.
    fetch_timestamp is validated as ISO 8601 format for consistency across the system.
    """

    model_config = ConfigDict(frozen=True)

    source_id: str
    version: int
    markdown: str
    chunk_hashes: tuple[Sha256Hash, ...]
    adapter_id: str
    normalizer_version: str
    fetch_timestamp: str

    @field_validator("fetch_timestamp")
    @classmethod
    def validate_fetch_timestamp(cls, value: str) -> str:
        """Validate that fetch_timestamp is a valid ISO 8601 timestamp."""
        validate_iso8601_timestamp(value)
        return value


class DiffResult(BaseModel):
    """Result of comparing two versions of content by chunk hashes.

    Set-based diffing enables efficient re-embedding: only new/modified chunks need embedding.
    prev_hash and curr_hash are full-document SHA-256 hashes for quick unchanged detection.

    Invariants:
    - added_hashes, removed_hashes, and unchanged_hashes are mutually disjoint sets
    - If changed=False: added_hashes and removed_hashes must be empty
    - All chunk_hashes and document hashes are validated as SHA-256 hex strings
    """

    model_config = ConfigDict(frozen=True)

    changed: bool
    added_hashes: frozenset[Sha256Hash]
    removed_hashes: frozenset[Sha256Hash]
    unchanged_hashes: frozenset[Sha256Hash]
    prev_hash: Sha256Hash | None = None
    curr_hash: Sha256Hash | None = None

    def model_post_init(self, __context) -> None:
        """Validate DiffResult invariants after model construction.

        Enforces:
        - Set disjointness: added_hashes, removed_hashes, and unchanged_hashes have no overlap
        - Flag consistency: changed=False implies no added or removed hashes
        """
        # Check set disjointness using frozenset operations
        added_and_removed = self.added_hashes & self.removed_hashes
        added_and_unchanged = self.added_hashes & self.unchanged_hashes
        removed_and_unchanged = self.removed_hashes & self.unchanged_hashes

        if added_and_removed:
            raise ValueError(
                f"added_hashes and removed_hashes must be disjoint, "
                f"but found overlap: {added_and_removed}"
            )
        if added_and_unchanged:
            raise ValueError(
                f"added_hashes and unchanged_hashes must be disjoint, "
                f"but found overlap: {added_and_unchanged}"
            )
        if removed_and_unchanged:
            raise ValueError(
                f"removed_hashes and unchanged_hashes must be disjoint, "
                f"but found overlap: {removed_and_unchanged}"
            )

        # Check changed flag consistency: if changed=False, must have no added/removed hashes
        if not self.changed:
            if self.added_hashes or self.removed_hashes:
                raise ValueError(
                    f"If changed=False, both added_hashes and removed_hashes must be empty. "
                    f"Got added_hashes={self.added_hashes}, removed_hashes={self.removed_hashes}"
                )


class VersionDiff(BaseModel):
    """Difference between two versions of a source based on chunk hashes.

    Computed by comparing the chunk_hashes sets of two source versions.
    All hash sets are frozen (immutable) for content-addressed integrity.

    Invariants:
    - added_hashes, removed_hashes, and unchanged_hashes are mutually disjoint
    - added_chunks contains the actual Chunk objects for added hashes
    - removed_chunks contains the actual Chunk objects for removed hashes
    """

    model_config = ConfigDict(frozen=True)

    source_id: str
    from_version: int
    to_version: int
    added_hashes: frozenset[Sha256Hash]
    removed_hashes: frozenset[Sha256Hash]
    unchanged_hashes: frozenset[Sha256Hash]
    added_chunks: tuple[Chunk, ...] = ()
    removed_chunks: tuple[Chunk, ...] = ()

    def model_post_init(self, __context) -> None:
        """Validate VersionDiff invariants after model construction.

        Enforces:
        - added_hashes, removed_hashes, and unchanged_hashes are disjoint
        - added_chunks contains hashes that match added_hashes
        - removed_chunks contains hashes that match removed_hashes
        """
        # Check set disjointness using frozenset operations
        added_and_removed = self.added_hashes & self.removed_hashes
        added_and_unchanged = self.added_hashes & self.unchanged_hashes
        removed_and_unchanged = self.removed_hashes & self.unchanged_hashes

        if added_and_removed:
            raise ValueError(
                f"added_hashes and removed_hashes must be disjoint, "
                f"but found overlap: {added_and_removed}"
            )
        if added_and_unchanged:
            raise ValueError(
                f"added_hashes and unchanged_hashes must be disjoint, "
                f"but found overlap: {added_and_unchanged}"
            )
        if removed_and_unchanged:
            raise ValueError(
                f"removed_hashes and unchanged_hashes must be disjoint, "
                f"but found overlap: {removed_and_unchanged}"
            )

        # Validate added_chunks contains only hashes that are in added_hashes
        # Note: added_chunks may be a subset of added_hashes if some chunks aren't yet
        # persisted to the database or due to data integrity issues
        added_chunk_hashes = frozenset(chunk.chunk_hash for chunk in self.added_chunks)
        if not added_chunk_hashes.issubset(self.added_hashes):
            invalid_hashes = added_chunk_hashes - self.added_hashes
            raise ValueError(
                f"added_chunks must be a subset of added_hashes. "
                f"Found invalid hashes not in added_hashes: {invalid_hashes}"
            )

        # Validate removed_chunks contains only hashes that are in removed_hashes
        # Note: removed_chunks may be a subset of removed_hashes if some chunks aren't yet
        # persisted to the database or due to data integrity issues
        removed_chunk_hashes = frozenset(chunk.chunk_hash for chunk in self.removed_chunks)
        if not removed_chunk_hashes.issubset(self.removed_hashes):
            invalid_hashes = removed_chunk_hashes - self.removed_hashes
            raise ValueError(
                f"removed_chunks must be a subset of removed_hashes. "
                f"Found invalid hashes not in removed_hashes: {invalid_hashes}"
            )


class AdapterConfig(BaseModel):
    """Configuration for a registered adapter.

    Immutable snapshot of adapter metadata for provenance and re-ingest auditing.
    """

    model_config = ConfigDict(frozen=True)

    adapter_id: str
    adapter_type: str
    domain: Domain
    normalizer_version: str
    config: dict[str, object] | None = None


class SourceInfo(BaseModel):
    """Source metadata for provenance tracing.

    Captures the origin reference and adapter type information needed to trace
    a chunk back to its source and understand how it was processed.

    Invariants:
    - origin_ref and adapter_type must be non-empty strings
    """

    model_config = ConfigDict(frozen=True)

    origin_ref: str
    adapter_type: str

    @field_validator("origin_ref")
    @classmethod
    def validate_origin_ref(cls, value: str) -> str:
        """Validate that origin_ref is not empty."""
        if not value:
            raise ValueError("origin_ref must be a non-empty string")
        return value

    @field_validator("adapter_type")
    @classmethod
    def validate_adapter_type(cls, value: str) -> str:
        """Validate that adapter_type is not empty."""
        if not value:
            raise ValueError("adapter_type must be a non-empty string")
        return value


class SourceTimeline(BaseModel):
    """Timeline of versions for a source.

    Immutable record of a source's version history for provenance tracking.
    Versions are ordered chronologically from earliest to latest.
    """

    model_config = ConfigDict(frozen=True)

    source_id: str
    versions: tuple[SourceVersion, ...]

    def model_post_init(self, __context) -> None:
        """Validate SourceTimeline invariants after model construction.

        Enforces:
        - versions are ordered by version number (earliest to latest)
        - all versions have matching source_id
        """
        if not self.versions:
            return

        # Check all versions have matching source_id
        for version in self.versions:
            if version.source_id != self.source_id:
                raise ValueError(
                    f"All versions must have source_id={self.source_id!r}, "
                    f"but got source_id={version.source_id!r} in version {version.version}"
                )

        # Check versions are ordered chronologically by version number
        prev_version = self.versions[0].version
        for version in self.versions[1:]:
            if version.version <= prev_version:
                raise ValueError(
                    f"versions must be ordered chronologically by version number, "
                    f"but version {version.version} is not greater than previous version {prev_version}"
                )
            prev_version = version.version


class ChunkProvenance(BaseModel):
    """Complete provenance information for a chunk.

    Traces a chunk back to its source, lineage, and version history.
    All fields are immutable for content-addressed integrity.

    Invariants:
    - version_chain is ordered from oldest ancestor to newest (chunk itself last)
    - All chunks in version_chain share the same chunk_hash or have parent-child relationships
    """

    model_config = ConfigDict(frozen=True)

    chunk: Chunk
    lineage: LineageRecord
    source_origin_ref: str
    adapter_type: str
    version_chain: tuple[Chunk, ...]

    def model_post_init(self, __context) -> None:
        """Validate ChunkProvenance invariants after model construction.

        Enforces:
        - version_chain is ordered from oldest ancestor to newest (chunk itself last)
        - version_chain is non-empty
        - Last chunk in version_chain matches the current chunk
        """
        if not self.version_chain:
            raise ValueError("version_chain cannot be empty")

        # Check that the last chunk in version_chain matches the current chunk
        # (ensuring version_chain is ordered with chunk itself at the end)
        if self.version_chain[-1].chunk_hash != self.chunk.chunk_hash:
            raise ValueError(
                f"version_chain must end with the current chunk. "
                f"Expected chunk_hash {self.chunk.chunk_hash!r}, "
                f"but version_chain[-1].chunk_hash is {self.version_chain[-1].chunk_hash!r}"
            )


def compute_chunk_hash(content: str) -> str:
    """Compute SHA-256 hash of normalized chunk content.

    Whitespace normalization:
    - Collapse runs of spaces/tabs to single space (not newlines)
    - Strip trailing whitespace per line
    - Collapse consecutive blank lines to single blank line
    - Strip leading/trailing whitespace from entire text
    - Normalize line endings to \\n

    Args:
        content: The chunk content to hash (excluding context header)

    Returns:
        SHA-256 hash as lowercase hex string
    """
    # Normalize line endings to \n
    normalized = content.replace("\r\n", "\n").replace("\r", "\n")

    # Collapse runs of spaces and tabs to single space (not newlines)
    normalized = re.sub(r"[ \t]+", " ", normalized)

    # Strip trailing whitespace from each line
    normalized = "\n".join(line.rstrip() for line in normalized.splitlines())

    # Collapse consecutive blank lines (2 or more newlines) to single blank line
    normalized = re.sub(r"\n\n+", "\n\n", normalized)

    # Strip leading/trailing whitespace from entire text
    normalized = normalized.strip()

    # Compute SHA-256
    return hashlib.sha256(normalized.encode()).hexdigest()
