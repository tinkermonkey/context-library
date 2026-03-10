"""Retrieval package: function-level retrieval interfaces composable with retrieve()."""

from context_library.retrieval.provenance import (
    get_source_timeline,
    get_version_diff,
    trace_chunk_provenance,
)
from context_library.retrieval.query import RerankedResult, RetrievalResult, retrieve
from context_library.retrieval.reranker import Reranker

__all__ = [
    "retrieve",
    "RetrievalResult",
    "RerankedResult",
    "get_version_diff",
    "get_source_timeline",
    "trace_chunk_provenance",
    "Reranker",
]
