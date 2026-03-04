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
        store_type: Type of store ("sqlite" or "lancedb")
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


class ValidationError(PipelineError):
    """Error during data validation."""

    pass


class PartialIngestionError(PipelineError):
    """Error indicating that all sources failed to ingest.

    This is raised when the pipeline completes but no sources were successfully processed.
    """

    pass
