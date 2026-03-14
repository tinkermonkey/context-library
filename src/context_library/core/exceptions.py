"""Custom exceptions for the context library pipeline."""


class PipelineError(Exception):
    """Base exception for pipeline errors."""

    pass


class EmbeddingError(PipelineError):
    """Error during embedding computation or validation.

    Attributes:
        chunk_hash: The hash of the chunk that failed embedding
        chunk_index: The index of the chunk in the batch
    """

    def __init__(self, message: str, chunk_hash: str | None = None, chunk_index: int | None = None):
        """Initialize EmbeddingError.

        Args:
            message: Error message
            chunk_hash: Hash of the failed chunk
            chunk_index: Index of the failed chunk in batch
        """
        super().__init__(message)
        self.chunk_hash = chunk_hash
        self.chunk_index = chunk_index


class StorageError(PipelineError):
    """Error during storage write operations.

    Attributes:
        store_type: Type of store ("sqlite" or "vector_store")
        inconsistent: Whether this error caused store inconsistency
    """

    def __init__(self, message: str, store_type: str | None = None, inconsistent: bool = False):
        """Initialize StorageError.

        Args:
            message: Error message
            store_type: Type of store that failed
            inconsistent: Whether inconsistency was detected
        """
        super().__init__(message)
        self.store_type = store_type
        self.inconsistent = inconsistent


class ChunkingError(PipelineError):
    """Error during content chunking (domain-specific processing).

    Raised when a domain chunker fails to process content, including parser
    failures, invalid structure, or other domain-specific errors.

    Attributes:
        source_id: The source identifier of the content that failed
    """

    def __init__(self, message: str, source_id: str | None = None):
        """Initialize ChunkingError.

        Args:
            message: Error message
            source_id: The source_id of the content that failed to chunk
        """
        super().__init__(message)
        self.source_id = source_id


class RerankerError(PipelineError):
    """Error during reranking with cross-encoder model.

    Raised when the cross-encoder model fails to score candidates,
    such as model initialization failures, prediction failures, or invalid input.

    Attributes:
        num_candidates: Number of candidates that failed to rerank
    """

    def __init__(self, message: str, num_candidates: int | None = None):
        """Initialize RerankerError.

        Args:
            message: Error message
            num_candidates: Number of candidates that failed to rerank
        """
        super().__init__(message)
        self.num_candidates = num_candidates


class AllSourcesFailedError(PipelineError):
    """Error raised when all sources fail during ingestion.

    This exception is raised when the pipeline completes but every single source
    failed to process successfully (sources_failed > 0 AND sources_processed == 0).
    """

    pass
