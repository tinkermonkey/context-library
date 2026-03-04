"""Wraps the embedding model; converts chunk text to dense vectors."""

from abc import ABC, abstractmethod


class Embedder(ABC):
    """Abstract interface for embedding text to dense vectors.

    Wraps an embedding model and provides methods to embed text chunks
    and queries into fixed-size dense vectors suitable for vector search.
    """

    @property
    @abstractmethod
    def model_id(self) -> str:
        """Get the identifier of the underlying embedding model.

        Returns:
            The model identifier (e.g., 'all-MiniLM-L6-v2')
        """
        pass

    @abstractmethod
    def embed(self, texts: list[str]) -> list[list[float]]:
        """Embed multiple texts into vectors.

        Args:
            texts: List of text strings to embed

        Returns:
            List of embedding vectors (each vector is a list of floats)
        """
        pass

    @abstractmethod
    def embed_query(self, query: str) -> list[float]:
        """Embed a single query string into a vector.

        Args:
            query: The query text to embed

        Returns:
            Embedding vector as a list of floats
        """
        pass
