"""SQLite-backed document store; source of truth for versions, chunks, and lineage."""

from abc import ABC, abstractmethod

from context_library.storage.models import LineageRecord


class DocumentStore(ABC):
    """Abstract interface for document storage and lineage tracking.

    The document store is the source of truth for all document versions,
    chunks, and their complete provenance. It uses SQLite as the backing
    store and enables full lineage reconstruction.
    """

    @abstractmethod
    def get_lineage(self, chunk_hash: str) -> LineageRecord | None:
        """Retrieve lineage information for a chunk.

        Args:
            chunk_hash: The hash identifier of the chunk to look up

        Returns:
            LineageRecord if the chunk exists in the store, None otherwise
        """
        pass
