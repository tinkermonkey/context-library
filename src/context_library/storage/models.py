"""Shared enumeration types and Pydantic data models for pipeline data flow.

This module contains:
- Domain enum for domain classification across adapters, storage, and chunking
- Pydantic models that flow through the pipeline (normalization -> chunking -> embedding)
- All models use frozen=True for immutability and content-addressed identity
"""

import hashlib
import re
from enum import Enum
from typing import Annotated

from pydantic import AfterValidator, BaseModel, ConfigDict


class Domain(str, Enum):
    """Fixed set of domain types for vector metadata.

    Used across SQLite schema, vector store, and domain modules.
    """

    MESSAGES = "messages"
    NOTES = "notes"
    EVENTS = "events"
    TASKS = "tasks"


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
    """

    model_config = ConfigDict(frozen=True)

    has_headings: bool
    has_lists: bool
    has_tables: bool
    natural_boundaries: list[int]
    file_path: str | None = None
    modified_at: str | None = None
    file_size_bytes: int | None = None


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
    """

    model_config = ConfigDict(frozen=True)

    chunk_hash: Sha256Hash
    content: str
    context_header: str | None = None
    chunk_index: int
    chunk_type: str = "standard"
    domain_metadata: dict[str, object] | None = None


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
    chunk_hashes is stored as a serialized list (in SQLite as JSON string).
    """

    model_config = ConfigDict(frozen=True)

    source_id: str
    version: int
    markdown: str
    chunk_hashes: list[str]
    adapter_id: str
    normalizer_version: str
    fetch_timestamp: str


class DiffResult(BaseModel):
    """Result of comparing two versions of content by chunk hashes.

    Set-based diffing enables efficient re-embedding: only new/modified chunks need embedding.
    prev_hash and curr_hash are full-document SHA-256 hashes for quick unchanged detection.
    """

    model_config = ConfigDict(frozen=True)

    changed: bool
    added_hashes: set[str]
    removed_hashes: set[str]
    unchanged_hashes: set[str]
    prev_hash: str | None = None
    curr_hash: str | None = None


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


def compute_chunk_hash(content: str) -> str:
    """Compute SHA-256 hash of normalized chunk content.

    Whitespace normalization:
    - Collapse runs of whitespace to single space
    - Strip trailing whitespace per line
    - Normalize line endings to \\n

    Args:
        content: The chunk content to hash (excluding context header)

    Returns:
        SHA-256 hash as lowercase hex string
    """
    # Normalize line endings to \n
    normalized = content.replace("\r\n", "\n").replace("\r", "\n")

    # Strip trailing whitespace per line and collapse internal whitespace runs
    lines = normalized.split("\n")
    lines = [re.sub(r"\s+", " ", line.rstrip()) for line in lines]
    normalized = "\n".join(lines)

    # Compute SHA-256
    return hashlib.sha256(normalized.encode()).hexdigest()
