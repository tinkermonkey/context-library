"""Retrieval package: function-level retrieval interfaces composable with retrieve()."""

from context_library.retrieval.provenance import (
    get_source_timeline,
    get_version_diff,
    trace_chunk_provenance,
)
from context_library.retrieval.query import RetrievalResult, retrieve
from context_library.retrieval.reranker import Reranker

__all__ = [
    "Reranker",
    "RetrievalResult",
    "get_source_timeline",
    "get_version_diff",
    "retrieve",
    "trace_chunk_provenance",
]
