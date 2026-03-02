"""Shared Pydantic data models: Chunk, LineageRecord, SourceVersion, VersionDiff."""

from enum import Enum


class Domain(str, Enum):
    """Fixed set of domain types for vector metadata.

    Used across SQLite schema, vector store, and domain modules.
    """

    MESSAGES = "messages"
    NOTES = "notes"
    EVENTS = "events"
    TASKS = "tasks"
