"""Shared enumeration types for domain classification across adapters, storage, and chunking."""

from datetime import datetime
from enum import Enum

from pydantic import BaseModel


class Domain(str, Enum):
    """Fixed set of domain types for vector metadata.

    Used across SQLite schema, vector store, and domain modules.
    """

    MESSAGES = "messages"
    NOTES = "notes"
    EVENTS = "events"
    TASKS = "tasks"


class LineageRecord(BaseModel):
    """Full provenance record for a chunk.

    Tracks the complete lineage of a chunk from source ingestion through
    normalization, chunking, and vector indexing. Enables reconstruction of
    the chunk's origin and version history.
    """

    adapter_id: str
    source_id: str
    source_version: int
    fetch_timestamp: datetime
    normalizer_version: str
    domain: Domain
    chunk_hash: str
    chunk_index: int
    parent_chunk_hash: str | None = None
