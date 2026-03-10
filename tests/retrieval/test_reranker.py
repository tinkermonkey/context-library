"""Tests for the reranker module.

Covers:
- Sigmoid normalization function
- Reranker initialization with default and custom models
- Reranking logic: ordering, score normalization, top_k truncation
- Batch inference (all candidates scored in single predict() call)
- Input validation (query, top_k)
- Error handling (RerankerError on prediction failures)
- RerankedResult model (wrapping RetrievalResult with separate reranker_score)
- Edge cases (empty candidates, empty query, extreme scores)
"""

from unittest.mock import MagicMock, patch

import pytest

from context_library.core.exceptions import RerankerError
from context_library.retrieval.query import RerankedResult, RetrievalResult
from context_library.retrieval.reranker import Reranker, _sigmoid
from context_library.storage.models import Chunk, Domain, LineageRecord


def _make_hash(char: str) -> str:
    """Create a valid SHA-256 hex hash."""
    return char * 64


def _create_test_chunk(hash_char: str, chunk_index: int = 0) -> Chunk:
    """Create a test chunk with given hash character."""
    return Chunk(
        chunk_hash=_make_hash(hash_char),
        content=f"Test chunk {hash_char}",
        context_header=f"Context for {hash_char}",
        chunk_index=chunk_index,
        chunk_type="standard",
        domain_metadata=None,
    )


def _create_test_lineage(hash_char: str, source_id: str = "source_1") -> LineageRecord:
    """Create a test lineage record."""
    return LineageRecord(
        chunk_hash=_make_hash(hash_char),
        source_id=source_id,
        source_version_id=1,
        adapter_id="test-adapter",
        domain=Domain.NOTES,
        normalizer_version="1.0.0",
        embedding_model_id="all-MiniLM-L6-v2",
    )


class TestSigmoid:
    """Tests for the sigmoid normalization function."""

    def test_sigmoid_zero(self) -> None:
        """Test sigmoid(0) = 0.5."""
        assert _sigmoid(0.0) == 0.5

    def test_sigmoid_positive(self) -> None:
        """Test sigmoid of positive value is > 0.5."""
        result = _sigmoid(2.0)
        assert 0.5 < result < 1.0

    def test_sigmoid_negative(self) -> None:
        """Test sigmoid of negative value is < 0.5."""
        result = _sigmoid(-2.0)
        assert 0.0 < result < 0.5

    def test_sigmoid_extreme_negative(self) -> None:
        """Test sigmoid of very negative value clamps to 0.0."""
        assert _sigmoid(-745.0) == 0.0
        assert _sigmoid(-1000.0) == 0.0

    def test_sigmoid_extreme_positive(self) -> None:
        """Test sigmoid of very positive value clamps to 1.0."""
        assert _sigmoid(745.0) == 1.0
        assert _sigmoid(1000.0) == 1.0


class TestRerankerInit:
    """Tests for Reranker initialization."""

    @patch("context_library.retrieval.reranker.CrossEncoder")
    def test_init_default_model(self, mock_ce_class) -> None:
        """Test Reranker init with default model."""
        mock_instance = MagicMock()
        mock_ce_class.return_value = mock_instance

        reranker = Reranker()

        assert reranker._model_name == "cross-encoder/ms-marco-MiniLM-L-6-v2"
        assert reranker._model == mock_instance
        mock_ce_class.assert_called_once_with("cross-encoder/ms-marco-MiniLM-L-6-v2")

    @patch("context_library.retrieval.reranker.CrossEncoder")
    def test_init_custom_model(self, mock_ce_class) -> None:
        """Test Reranker init with custom model."""
        mock_instance = MagicMock()
        mock_ce_class.return_value = mock_instance

        reranker = Reranker(model_name="custom-model")

        assert reranker._model_name == "custom-model"
        assert reranker._model == mock_instance
        mock_ce_class.assert_called_once_with("custom-model")


class TestRerankerRerank:
    """Tests for Reranker.rerank() method."""

    @patch("context_library.retrieval.reranker.CrossEncoder")
    def test_rerank_basic_ordering(self, mock_ce_class) -> None:
        """Test rerank returns candidates ordered by descending cross-encoder score."""
        mock_instance = MagicMock()
        mock_ce_class.return_value = mock_instance
        # Raw scores: [2.0, -1.0, 0.5]
        # After sigmoid: [sigmoid(2.0)≈0.88, sigmoid(-1.0)≈0.27, sigmoid(0.5)≈0.62]
        # Sorted descending: 0.88, 0.62, 0.27
        mock_instance.predict.return_value = [2.0, -1.0, 0.5]

        candidates = [
            RetrievalResult(
                chunk=_create_test_chunk("a"),
                lineage=_create_test_lineage("a"),
                similarity_score=0.9,
            ),
            RetrievalResult(
                chunk=_create_test_chunk("b"),
                lineage=_create_test_lineage("b"),
                similarity_score=0.7,
            ),
            RetrievalResult(
                chunk=_create_test_chunk("c"),
                lineage=_create_test_lineage("c"),
                similarity_score=0.8,
            ),
        ]

        reranker = Reranker()
        results = reranker.rerank("test query", candidates)

        # Verify ordering: chunk a (2.0), chunk c (0.5), chunk b (-1.0)
        assert len(results) == 3
        assert results[0].chunk.chunk_hash == _make_hash("a")
        assert results[1].chunk.chunk_hash == _make_hash("c")
        assert results[2].chunk.chunk_hash == _make_hash("b")

        # Verify reranker scores are in descending order
        assert results[0].reranker_score > results[1].reranker_score
        assert results[1].reranker_score > results[2].reranker_score

    @patch("context_library.retrieval.reranker.CrossEncoder")
    def test_rerank_score_normalization(self, mock_ce_class) -> None:
        """Test rerank normalizes scores to [0, 1] via sigmoid."""
        mock_instance = MagicMock()
        mock_ce_class.return_value = mock_instance
        mock_instance.predict.return_value = [0.0]

        candidates = [
            RetrievalResult(
                chunk=_create_test_chunk("a"),
                lineage=_create_test_lineage("a"),
                similarity_score=0.5,
            ),
        ]

        reranker = Reranker()
        results = reranker.rerank("test query", candidates)

        # sigmoid(0.0) = 0.5
        assert results[0].reranker_score == 0.5

    @patch("context_library.retrieval.reranker.CrossEncoder")
    def test_rerank_top_k_one(self, mock_ce_class) -> None:
        """Test rerank with top_k=1 returns at most 1 result."""
        mock_instance = MagicMock()
        mock_ce_class.return_value = mock_instance
        mock_instance.predict.return_value = [1.0, 2.0, 3.0]

        candidates = [
            RetrievalResult(
                chunk=_create_test_chunk("a"),
                lineage=_create_test_lineage("a"),
                similarity_score=0.5,
            ),
            RetrievalResult(
                chunk=_create_test_chunk("b"),
                lineage=_create_test_lineage("b"),
                similarity_score=0.6,
            ),
            RetrievalResult(
                chunk=_create_test_chunk("c"),
                lineage=_create_test_lineage("c"),
                similarity_score=0.7,
            ),
        ]

        reranker = Reranker()
        results = reranker.rerank("test query", candidates, top_k=1)

        assert len(results) == 1
        # The highest score should be returned (3.0 -> chunk c)
        assert results[0].chunk.chunk_hash == _make_hash("c")

    @patch("context_library.retrieval.reranker.CrossEncoder")
    def test_rerank_top_k_three(self, mock_ce_class) -> None:
        """Test rerank with top_k=3 on 5 candidates returns 3."""
        mock_instance = MagicMock()
        mock_ce_class.return_value = mock_instance
        mock_instance.predict.return_value = [1.0, 2.0, 3.0, 0.5, 1.5]

        candidates = [
            RetrievalResult(
                chunk=_create_test_chunk("a"),
                lineage=_create_test_lineage("a"),
                similarity_score=0.5,
            ),
            RetrievalResult(
                chunk=_create_test_chunk("b"),
                lineage=_create_test_lineage("b"),
                similarity_score=0.6,
            ),
            RetrievalResult(
                chunk=_create_test_chunk("c"),
                lineage=_create_test_lineage("c"),
                similarity_score=0.7,
            ),
            RetrievalResult(
                chunk=_create_test_chunk("d"),
                lineage=_create_test_lineage("d"),
                similarity_score=0.4,
            ),
            RetrievalResult(
                chunk=_create_test_chunk("e"),
                lineage=_create_test_lineage("e"),
                similarity_score=0.65,
            ),
        ]

        reranker = Reranker()
        results = reranker.rerank("test query", candidates, top_k=3)

        assert len(results) == 3

    @patch("context_library.retrieval.reranker.CrossEncoder")
    def test_rerank_top_k_greater_than_candidates(self, mock_ce_class) -> None:
        """Test rerank with top_k > num candidates returns all candidates."""
        mock_instance = MagicMock()
        mock_ce_class.return_value = mock_instance
        mock_instance.predict.return_value = [1.0, 2.0]

        candidates = [
            RetrievalResult(
                chunk=_create_test_chunk("a"),
                lineage=_create_test_lineage("a"),
                similarity_score=0.5,
            ),
            RetrievalResult(
                chunk=_create_test_chunk("b"),
                lineage=_create_test_lineage("b"),
                similarity_score=0.6,
            ),
        ]

        reranker = Reranker()
        results = reranker.rerank("test query", candidates, top_k=100)

        assert len(results) == 2

    @patch("context_library.retrieval.reranker.CrossEncoder")
    def test_rerank_top_k_none_returns_all(self, mock_ce_class) -> None:
        """Test rerank with top_k=None returns all candidates."""
        mock_instance = MagicMock()
        mock_ce_class.return_value = mock_instance
        mock_instance.predict.return_value = [1.0, 2.0, 3.0]

        candidates = [
            RetrievalResult(
                chunk=_create_test_chunk("a"),
                lineage=_create_test_lineage("a"),
                similarity_score=0.5,
            ),
            RetrievalResult(
                chunk=_create_test_chunk("b"),
                lineage=_create_test_lineage("b"),
                similarity_score=0.6,
            ),
            RetrievalResult(
                chunk=_create_test_chunk("c"),
                lineage=_create_test_lineage("c"),
                similarity_score=0.7,
            ),
        ]

        reranker = Reranker()
        results = reranker.rerank("test query", candidates, top_k=None)

        assert len(results) == 3

    @patch("context_library.retrieval.reranker.CrossEncoder")
    def test_rerank_empty_candidates_returns_empty(self, mock_ce_class) -> None:
        """Test rerank with empty candidates returns empty list."""
        mock_instance = MagicMock()
        mock_ce_class.return_value = mock_instance

        reranker = Reranker()
        results = reranker.rerank("test query", [])

        assert results == []
        # Verify predict was not called for empty input
        mock_instance.predict.assert_not_called()

    @patch("context_library.retrieval.reranker.CrossEncoder")
    def test_rerank_empty_query_raises_error(self, mock_ce_class) -> None:
        """Test rerank with empty query raises ValueError."""
        mock_instance = MagicMock()
        mock_ce_class.return_value = mock_instance

        candidates = [
            RetrievalResult(
                chunk=_create_test_chunk("a"),
                lineage=_create_test_lineage("a"),
                similarity_score=0.5,
            ),
        ]

        reranker = Reranker()
        with pytest.raises(ValueError, match="query must be a non-empty string"):
            reranker.rerank("", candidates)

    @patch("context_library.retrieval.reranker.CrossEncoder")
    def test_rerank_whitespace_query_raises_error(self, mock_ce_class) -> None:
        """Test rerank with whitespace-only query raises ValueError."""
        mock_instance = MagicMock()
        mock_ce_class.return_value = mock_instance

        candidates = [
            RetrievalResult(
                chunk=_create_test_chunk("a"),
                lineage=_create_test_lineage("a"),
                similarity_score=0.5,
            ),
        ]

        reranker = Reranker()
        with pytest.raises(ValueError, match="query must be a non-empty string"):
            reranker.rerank("   ", candidates)

    @patch("context_library.retrieval.reranker.CrossEncoder")
    def test_rerank_non_positive_top_k_raises_error(self, mock_ce_class) -> None:
        """Test rerank with top_k <= 0 raises ValueError."""
        mock_instance = MagicMock()
        mock_ce_class.return_value = mock_instance

        candidates = [
            RetrievalResult(
                chunk=_create_test_chunk("a"),
                lineage=_create_test_lineage("a"),
                similarity_score=0.5,
            ),
        ]

        reranker = Reranker()
        with pytest.raises(ValueError, match="top_k must be positive"):
            reranker.rerank("test query", candidates, top_k=0)

    @patch("context_library.retrieval.reranker.CrossEncoder")
    def test_rerank_negative_top_k_raises_error(self, mock_ce_class) -> None:
        """Test rerank with negative top_k raises ValueError."""
        mock_instance = MagicMock()
        mock_ce_class.return_value = mock_instance

        candidates = [
            RetrievalResult(
                chunk=_create_test_chunk("a"),
                lineage=_create_test_lineage("a"),
                similarity_score=0.5,
            ),
        ]

        reranker = Reranker()
        with pytest.raises(ValueError, match="top_k must be positive"):
            reranker.rerank("test query", candidates, top_k=-1)

    @patch("context_library.retrieval.reranker.CrossEncoder")
    def test_rerank_batch_inference(self, mock_ce_class) -> None:
        """Test rerank calls CrossEncoder.predict() once with all candidates."""
        mock_instance = MagicMock()
        mock_ce_class.return_value = mock_instance
        mock_instance.predict.return_value = [1.0, 2.0, 3.0]

        candidates = [
            RetrievalResult(
                chunk=_create_test_chunk("a"),
                lineage=_create_test_lineage("a"),
                similarity_score=0.5,
            ),
            RetrievalResult(
                chunk=_create_test_chunk("b"),
                lineage=_create_test_lineage("b"),
                similarity_score=0.6,
            ),
            RetrievalResult(
                chunk=_create_test_chunk("c"),
                lineage=_create_test_lineage("c"),
                similarity_score=0.7,
            ),
        ]

        reranker = Reranker()
        reranker.rerank("test query", candidates)

        # Verify predict was called exactly once with all pairs
        assert mock_instance.predict.call_count == 1
        call_args = mock_instance.predict.call_args
        pairs = call_args[0][0]
        assert len(pairs) == 3
        assert pairs[0] == ("test query", "Test chunk a")
        assert pairs[1] == ("test query", "Test chunk b")
        assert pairs[2] == ("test query", "Test chunk c")

    @patch("context_library.retrieval.reranker.CrossEncoder")
    def test_rerank_result_fields_preserved(self, mock_ce_class) -> None:
        """Test rerank preserves chunk and lineage fields."""
        mock_instance = MagicMock()
        mock_ce_class.return_value = mock_instance
        mock_instance.predict.return_value = [0.5]

        chunk = _create_test_chunk("a")
        lineage = _create_test_lineage("a")
        candidates = [
            RetrievalResult(chunk=chunk, lineage=lineage, similarity_score=0.5),
        ]

        reranker = Reranker()
        results = reranker.rerank("test query", candidates)

        # Verify chunk and lineage are unchanged
        assert results[0].chunk == chunk
        assert results[0].lineage == lineage

    @patch("context_library.retrieval.reranker.CrossEncoder")
    def test_rerank_immutability(self, mock_ce_class) -> None:
        """Test rerank creates new RerankedResult objects (immutability)."""
        mock_instance = MagicMock()
        mock_ce_class.return_value = mock_instance
        mock_instance.predict.return_value = [0.5]

        original = RetrievalResult(
            chunk=_create_test_chunk("a"),
            lineage=_create_test_lineage("a"),
            similarity_score=0.8,
        )
        candidates = [original]

        reranker = Reranker()
        results = reranker.rerank("test query", candidates)

        # Verify new RerankedResult object was created with different reranker_score
        assert results[0] is not original
        assert results[0].reranker_score != original.similarity_score

    @patch("context_library.retrieval.reranker.CrossEncoder")
    def test_rerank_multiple_calls_independent(self, mock_ce_class) -> None:
        """Test multiple rerank calls are independent."""
        mock_instance = MagicMock()
        mock_ce_class.return_value = mock_instance
        mock_instance.predict.side_effect = [[2.0], [1.0]]

        candidates_1 = [
            RetrievalResult(
                chunk=_create_test_chunk("a"),
                lineage=_create_test_lineage("a"),
                similarity_score=0.5,
            ),
        ]
        candidates_2 = [
            RetrievalResult(
                chunk=_create_test_chunk("b"),
                lineage=_create_test_lineage("b"),
                similarity_score=0.5,
            ),
        ]

        reranker = Reranker()
        results_1 = reranker.rerank("query 1", candidates_1)
        results_2 = reranker.rerank("query 2", candidates_2)

        # Verify both calls succeeded with different reranker scores
        assert results_1[0].reranker_score > results_2[0].reranker_score

    @patch("context_library.retrieval.reranker.CrossEncoder")
    def test_rerank_extreme_scores_normalized(self, mock_ce_class) -> None:
        """Test extreme raw scores are normalized via sigmoid."""
        mock_instance = MagicMock()
        mock_ce_class.return_value = mock_instance
        mock_instance.predict.return_value = [-1000.0, 0.0, 1000.0]

        candidates = [
            RetrievalResult(
                chunk=_create_test_chunk("a"),
                lineage=_create_test_lineage("a"),
                similarity_score=0.5,
            ),
            RetrievalResult(
                chunk=_create_test_chunk("b"),
                lineage=_create_test_lineage("b"),
                similarity_score=0.5,
            ),
            RetrievalResult(
                chunk=_create_test_chunk("c"),
                lineage=_create_test_lineage("c"),
                similarity_score=0.5,
            ),
        ]

        reranker = Reranker()
        results = reranker.rerank("test query", candidates)

        # Verify all reranker_scores are in [0, 1]
        assert all(0.0 <= r.reranker_score <= 1.0 for r in results)
        # Verify extreme values map to 0 and 1
        assert results[0].reranker_score == 1.0  # 1000 -> 1
        assert results[1].reranker_score == 0.5  # 0 -> 0.5
        assert results[2].reranker_score == 0.0  # -1000 -> 0

    @patch("context_library.retrieval.reranker.CrossEncoder")
    def test_rerank_returns_reranked_results(self, mock_ce_class) -> None:
        """Test rerank returns RerankedResult objects, not RetrievalResult."""
        mock_instance = MagicMock()
        mock_ce_class.return_value = mock_instance
        mock_instance.predict.return_value = [0.5]

        candidates = [
            RetrievalResult(
                chunk=_create_test_chunk("a"),
                lineage=_create_test_lineage("a"),
                similarity_score=0.5,
            ),
        ]

        reranker = Reranker()
        results = reranker.rerank("test query", candidates)

        assert len(results) == 1
        assert isinstance(results[0], RerankedResult)

    @patch("context_library.retrieval.reranker.CrossEncoder")
    def test_rerank_preserves_vector_similarity_score(self, mock_ce_class) -> None:
        """Test rerank preserves original vector similarity score in RerankedResult."""
        mock_instance = MagicMock()
        mock_ce_class.return_value = mock_instance
        # Raw score 0.0 normalizes to 0.5
        mock_instance.predict.return_value = [0.0]

        original_similarity_score = 0.7
        candidates = [
            RetrievalResult(
                chunk=_create_test_chunk("a"),
                lineage=_create_test_lineage("a"),
                similarity_score=original_similarity_score,
            ),
        ]

        reranker = Reranker()
        results = reranker.rerank("test query", candidates)

        # Original vector similarity score should be preserved
        assert results[0].similarity_score == original_similarity_score
        # Reranker score should be different (normalized from raw score)
        assert results[0].reranker_score == 0.5
        assert results[0].reranker_score != results[0].similarity_score

    @patch("context_library.retrieval.reranker.CrossEncoder")
    def test_rerank_distinguishes_scores(self, mock_ce_class) -> None:
        """Test that vector similarity and reranker scores are distinct."""
        mock_instance = MagicMock()
        mock_ce_class.return_value = mock_instance
        mock_instance.predict.return_value = [2.0]

        candidates = [
            RetrievalResult(
                chunk=_create_test_chunk("a"),
                lineage=_create_test_lineage("a"),
                similarity_score=0.3,  # Low vector similarity
            ),
        ]

        reranker = Reranker()
        results = reranker.rerank("test query", candidates)

        # Vector similarity: 0.3
        # Reranker score: sigmoid(2.0) ≈ 0.88
        # These should be clearly distinguishable
        assert results[0].similarity_score == 0.3
        assert results[0].reranker_score > 0.87 and results[0].reranker_score < 0.89

    @patch("context_library.retrieval.reranker.CrossEncoder")
    def test_rerank_model_error_raises_reranker_error(self, mock_ce_class) -> None:
        """Test rerank wraps CrossEncoder exceptions as RerankerError."""
        mock_instance = MagicMock()
        mock_ce_class.return_value = mock_instance
        mock_instance.predict.side_effect = RuntimeError("Model load failed")

        candidates = [
            RetrievalResult(
                chunk=_create_test_chunk("a"),
                lineage=_create_test_lineage("a"),
                similarity_score=0.5,
            ),
        ]

        reranker = Reranker()
        with pytest.raises(RerankerError, match="Model load failed"):
            reranker.rerank("test query", candidates)

    @patch("context_library.retrieval.reranker.CrossEncoder")
    def test_reranker_error_includes_candidate_count(self, mock_ce_class) -> None:
        """Test RerankerError includes number of candidates that failed."""
        mock_instance = MagicMock()
        mock_ce_class.return_value = mock_instance
        mock_instance.predict.side_effect = ValueError("Prediction failed")

        candidates = [
            RetrievalResult(
                chunk=_create_test_chunk("a"),
                lineage=_create_test_lineage("a"),
                similarity_score=0.5,
            ),
            RetrievalResult(
                chunk=_create_test_chunk("b"),
                lineage=_create_test_lineage("b"),
                similarity_score=0.6,
            ),
        ]

        reranker = Reranker()
        with pytest.raises(RerankerError) as exc_info:
            reranker.rerank("test query", candidates)

        assert exc_info.value.num_candidates == 2

    @patch("context_library.retrieval.reranker.CrossEncoder")
    def test_reranked_result_to_dict(self, mock_ce_class) -> None:
        """Test RerankedResult.to_dict() includes both scores."""
        mock_instance = MagicMock()
        mock_ce_class.return_value = mock_instance
        mock_instance.predict.return_value = [1.0]

        chunk = _create_test_chunk("a")
        lineage = _create_test_lineage("a")
        candidates = [
            RetrievalResult(chunk=chunk, lineage=lineage, similarity_score=0.6),
        ]

        reranker = Reranker()
        results = reranker.rerank("test query", candidates)

        result_dict = results[0].to_dict()
        assert "similarity_score" in result_dict
        assert "reranker_score" in result_dict
        assert result_dict["similarity_score"] == 0.6
        assert result_dict["reranker_score"] > 0.7  # sigmoid(1.0) ≈ 0.73

    @patch("context_library.retrieval.reranker.CrossEncoder")
    def test_reranked_result_properties(self, mock_ce_class) -> None:
        """Test RerankedResult provides convenient access to underlying data."""
        mock_instance = MagicMock()
        mock_ce_class.return_value = mock_instance
        mock_instance.predict.return_value = [0.0]

        chunk = _create_test_chunk("a")
        lineage = _create_test_lineage("a")
        candidates = [
            RetrievalResult(chunk=chunk, lineage=lineage, similarity_score=0.4),
        ]

        reranker = Reranker()
        results = reranker.rerank("test query", candidates)

        # Test property access
        assert results[0].chunk == chunk
        assert results[0].lineage == lineage
        assert results[0].similarity_score == 0.4
        # Direct access to reranker_score
        assert results[0].reranker_score == 0.5

    @patch("context_library.retrieval.reranker.CrossEncoder")
    def test_rerank_sorts_by_reranker_score(self, mock_ce_class) -> None:
        """Test rerank sorts results by reranker_score, not original similarity_score."""
        mock_instance = MagicMock()
        mock_ce_class.return_value = mock_instance
        # Raw scores in opposite order of original vector similarities
        mock_instance.predict.return_value = [3.0, 0.0, -3.0]

        candidates = [
            RetrievalResult(
                chunk=_create_test_chunk("a"),
                lineage=_create_test_lineage("a"),
                similarity_score=0.2,  # Low vector similarity
            ),
            RetrievalResult(
                chunk=_create_test_chunk("b"),
                lineage=_create_test_lineage("b"),
                similarity_score=0.5,  # Medium vector similarity
            ),
            RetrievalResult(
                chunk=_create_test_chunk("c"),
                lineage=_create_test_lineage("c"),
                similarity_score=0.9,  # High vector similarity
            ),
        ]

        reranker = Reranker()
        results = reranker.rerank("test query", candidates)

        # Results should be sorted by reranker_score (descending): a > b > c
        assert results[0].chunk.chunk_hash == _make_hash("a")
        assert results[1].chunk.chunk_hash == _make_hash("b")
        assert results[2].chunk.chunk_hash == _make_hash("c")
        # Original vector scores are different from sort order
        assert results[0].similarity_score < results[2].similarity_score
