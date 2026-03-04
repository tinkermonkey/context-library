"""Wraps the embedding model; converts chunk text to dense vectors."""

from sentence_transformers import SentenceTransformer


class Embedder:
    """Wraps a sentence-transformers model for batch embedding."""

    def __init__(self, model_name: str = "all-MiniLM-L6-v2") -> None:
        """Initialize the embedder with a sentence-transformers model.

        Args:
            model_name: Name of the sentence-transformers model to load.
                       Defaults to "all-MiniLM-L6-v2".
        """
        self._model_name = model_name
        self._model = SentenceTransformer(model_name)

    @property
    def model_id(self) -> str:
        """Return the model name string.

        Returns:
            The model name passed to the constructor.
        """
        return self._model_name

    @property
    def dimension(self) -> int:
        """Return the model's output dimension.

        Returns:
            The embedding dimension as an integer.
        """
        return self._model.get_sentence_embedding_dimension()

    def embed(self, texts: list[str]) -> list[list[float]]:
        """Embed a batch of texts using the model.

        Args:
            texts: List of text strings to embed.

        Returns:
            List of embedding vectors, each as a list of floats.
        """
        embeddings = self._model.encode(texts, convert_to_numpy=True)
        return embeddings.tolist()

    def embed_query(self, query: str) -> list[float]:
        """Embed a single query string.

        Convenience wrapper for embedding a single string.

        Args:
            query: The query string to embed.

        Returns:
            A single embedding vector as a list of floats.
        """
        embedding = self._model.encode(query, convert_to_numpy=True)
        return embedding.tolist()
