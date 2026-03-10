"""Reranks vector search results using cross-encoder model for improved relevance.

Provides the Reranker class that wraps sentence-transformers CrossEncoder
to reorder retrieval candidates by cross-encoder relevance scores.
Complements bi-encoder similarity with cross-encoder fine-tuned ranking.
"""

import math
from typing import Optional

from sentence_transformers import CrossEncoder

from context_library.core.exceptions import RerankerError
from context_library.retrieval.query import RerankedResult, RetrievalResult


def _sigmoid(x: float) -> float:
    """Convert raw cross-encoder logit to normalized probability [0, 1].

    Numerically stable sigmoid implementation that handles extreme values.
    Uses the identity: sigmoid(x) = 1 / (1 + exp(-x)), with underflow protection
    for large negative x (maps to ~0) and overflow protection for large positive x (maps to ~1).

    Args:
        x: Raw cross-encoder score (unbounded logit).

    Returns:
        Probability in range [0, 1].
    """
    # Clamp extreme values to prevent overflow
    # For large negative x, exp(-x) overflows, so sigmoid(x) ≈ 0.0
    # For large positive x, exp(-x) underflows to 0, so sigmoid(x) ≈ 1.0
    if x <= -745:
        return 0.0
    if x >= 745:
        return 1.0
    return 1.0 / (1.0 + math.exp(-x))


class Reranker:
    """Reranks retrieval candidates using a cross-encoder model.

    Wraps sentence-transformers CrossEncoder for relevance scoring.
    Takes query-candidate pairs and produces normalized scores [0, 1].
    All candidates are scored in a single batch inference call.

    The model is loaded once at construction time.
    """

    def __init__(self, model_name: str = "cross-encoder/ms-marco-MiniLM-L-6-v2") -> None:
        """Initialize the reranker with a cross-encoder model.

        Args:
            model_name: Name of the cross-encoder model to load.
                       Defaults to "cross-encoder/ms-marco-MiniLM-L-6-v2".

        Raises:
            OSError: If the model cannot be downloaded or loaded.
        """
        self._model_name = model_name
        self._model = CrossEncoder(model_name)

    def rerank(
        self,
        query: str,
        candidates: list[RetrievalResult],
        top_k: Optional[int] = None,
    ) -> list[RerankedResult]:
        """Rerank candidates by cross-encoder relevance score.

        Scores all candidates in a single batch inference call.
        Returns candidates ordered by descending cross-encoder score.
        Optionally truncates results to top_k.

        Args:
            query: The query string.
            candidates: List of RetrievalResult candidates to rerank.
            top_k: Maximum number of results to return. If None, returns all.
                   Must be positive if provided.

        Returns:
            List of RerankedResult objects reordered by descending normalized
            cross-encoder score, optionally truncated to top_k.
            Reranker scores normalized to [0, 1] via sigmoid.
            Original vector similarity scores preserved in retrieval_result.

        Raises:
            ValueError: If query is empty/whitespace or top_k is not positive.
            RerankerError: If cross-encoder model fails during prediction.
        """
        # Validate inputs
        if not query or not query.strip():
            raise ValueError("query must be a non-empty string")

        if top_k is not None and top_k <= 0:
            raise ValueError(f"top_k must be positive, got {top_k}")

        # Return empty list if no candidates
        if not candidates:
            return []

        # Build query-candidate pairs and score in batch
        pairs = [(query, candidate.chunk.content) for candidate in candidates]

        try:
            raw_scores = self._model.predict(pairs)
        except Exception as e:
            raise RerankerError(
                f"Cross-encoder prediction failed: {type(e).__name__}: {e}",
                num_candidates=len(candidates),
            ) from e

        # Normalize scores via sigmoid and wrap RetrievalResult objects in RerankedResult
        reranked_results: list[RerankedResult] = []
        for candidate, raw_score in zip(candidates, raw_scores):
            normalized_score = _sigmoid(float(raw_score))
            reranked_results.append(
                RerankedResult(
                    retrieval_result=candidate,
                    reranker_score=normalized_score,
                )
            )

        # Sort by descending reranker score
        reranked_results.sort(key=lambda r: r.reranker_score, reverse=True)

        # Truncate to top_k if specified
        if top_k is not None:
            reranked_results = reranked_results[:top_k]

        return reranked_results
