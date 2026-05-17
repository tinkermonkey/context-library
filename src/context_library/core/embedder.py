"""Wraps the embedding model; converts chunk text to dense vectors."""

from typing import cast

from context_library.telemetry.tracer import get_tracer, get_status_code
from sentence_transformers import SentenceTransformer

tracer = get_tracer(__name__)
StatusCode = get_status_code()


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

        Raises:
            ValueError: If the model does not report an embedding dimension.
        """
        dim = self._model.get_embedding_dimension()
        if dim is None:
            raise ValueError(f"Model {self._model_name} did not report an embedding dimension")
        return cast(int, dim)

    def embed(self, texts: list[str]) -> list[list[float]]:
        """Embed a batch of texts using the model.

        Args:
            texts: List of text strings to embed.

        Returns:
            List of embedding vectors, each as a list of floats.

        Raises:
            ValueError: If texts is empty or contains only empty strings.
        """
        with tracer.start_as_current_span("embedder.embed") as span:
            try:
                if not texts:
                    raise ValueError("Cannot embed empty list of texts")
                if all(not text or not text.strip() for text in texts):
                    raise ValueError("Cannot embed list containing only empty or whitespace-only strings")
                span.set_attribute("chunk_count", len(texts))
                span.set_attribute("model_id", self.model_id)
                embeddings = self._model.encode(texts, convert_to_numpy=True)
                return cast(list[list[float]], embeddings.tolist())
            except Exception as e:
                span.set_status(StatusCode.ERROR)
                span.record_exception(e)
                raise

    def embed_query(self, query: str) -> list[float]:
        """Embed a single query string.

        Convenience wrapper for embedding a single string.

        Args:
            query: The query string to embed.

        Returns:
            A single embedding vector as a list of floats.

        Raises:
            ValueError: If query is empty or contains only whitespace.
        """
        with tracer.start_as_current_span("embedder.embed_query") as span:
            try:
                if not query or not query.strip():
                    raise ValueError("Cannot embed empty or whitespace-only query")
                span.set_attribute("model_id", self.model_id)
                embedding = self._model.encode(query, convert_to_numpy=True)
                return cast(list[float], embedding.tolist())
            except Exception as e:
                span.set_status(StatusCode.ERROR)
                span.record_exception(e)
                raise
