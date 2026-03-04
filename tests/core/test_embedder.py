"""Tests for the embedder module."""

from unittest.mock import patch, MagicMock

import pytest
from context_library.core.embedder import Embedder


class TestEmbedder:
    """Test suite for the Embedder class."""

    @pytest.fixture
    def embedder(self):
        """Create an Embedder instance for testing."""
        return Embedder()

    def test_model_id_property(self, embedder):
        """Test that model_id returns the correct model name."""
        assert embedder.model_id == "all-MiniLM-L6-v2"

    def test_model_id_with_custom_model(self):
        """Test that model_id returns the custom model name."""
        custom_model_name = "custom-model-xyz"
        with patch("context_library.core.embedder.SentenceTransformer"):
            embedder = Embedder(model_name=custom_model_name)
            assert embedder.model_id == custom_model_name

    def test_dimension_property(self, embedder):
        """Test that dimension returns the correct output dimension."""
        # all-MiniLM-L6-v2 has dimension 384
        assert embedder.dimension == 384

    def test_embed_output_shape(self, embedder):
        """Test that embed() returns correct output shape."""
        texts = ["Hello world", "This is a test"]
        embeddings = embedder.embed(texts)

        # Should return 2 vectors
        assert len(embeddings) == 2

        # Each vector should have dimension 384
        assert len(embeddings[0]) == embedder.dimension
        assert len(embeddings[1]) == embedder.dimension

    def test_embed_single_text(self, embedder):
        """Test that embed() works with a single text in a list."""
        texts = ["Single text"]
        embeddings = embedder.embed(texts)

        assert len(embeddings) == 1
        assert len(embeddings[0]) == embedder.dimension

    def test_embed_returns_python_floats(self, embedder):
        """Test that embed() returns Python float types, not numpy types."""
        texts = ["Test text"]
        embeddings = embedder.embed(texts)

        # Check that the values are Python floats
        assert isinstance(embeddings[0][0], float)

    def test_embed_query_output_length(self, embedder):
        """Test that embed_query() returns vector with correct length."""
        query = "What is machine learning?"
        embedding = embedder.embed_query(query)

        # Should return a single vector
        assert len(embedding) == embedder.dimension

    def test_embed_query_returns_python_floats(self, embedder):
        """Test that embed_query() returns Python float types."""
        query = "Test query"
        embedding = embedder.embed_query(query)

        # Check that the values are Python floats
        assert isinstance(embedding[0], float)

    def test_embed_batch_processing(self, embedder):
        """Test that embed() handles batch processing correctly."""
        texts = ["Text one", "Text two", "Text three", "Text four"]
        embeddings = embedder.embed(texts)

        assert len(embeddings) == 4
        for embedding in embeddings:
            assert len(embedding) == embedder.dimension
            assert all(isinstance(val, float) for val in embedding)

    def test_embedder_initialization(self):
        """Test that Embedder initializes without error."""
        embedder = Embedder()
        assert embedder is not None
        assert embedder.model_id == "all-MiniLM-L6-v2"

    def test_embed_query_consistency(self, embedder):
        """Test that embed_query produces consistent results."""
        query = "Consistency test"
        embedding1 = embedder.embed_query(query)
        embedding2 = embedder.embed_query(query)

        # Both embeddings should be identical
        assert embedding1 == embedding2
