"""Abstract base class defining the BaseDomain interface."""

from abc import ABC, abstractmethod

from context_library.storage.models import Chunk, NormalizedContent


class BaseDomain(ABC):
    """Abstract base class defining the domain chunking contract.

    All domain implementations (NOTES, MESSAGES, EVENTS, TASKS) must inherit from this class
    and implement the chunk() method with domain-specific chunking strategies.
    """

    @abstractmethod
    def chunk(self, content: NormalizedContent) -> list[Chunk]:
        """Split normalized content into semantically coherent chunks.

        Args:
            content: The normalized content to chunk

        Returns:
            A list of Chunk instances with sequential chunk_index values
        """
        pass
