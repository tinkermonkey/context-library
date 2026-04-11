"""Abstract BaseAdapter defining the adapter contract."""

from abc import ABC, abstractmethod
from typing import Iterator

from pydantic import BaseModel

from context_library.storage.models import AdapterConfig, Domain, NormalizedContent
from context_library.storage.document_store import DocumentStore


class ResetResult(BaseModel):
    """Result of a reset operation on an adapter's helper service.

    Attributes:
        ok: Whether the reset operation succeeded (True) or had errors (False).
        cleared: List of state items that were cleared (e.g., "push_cursor:obsidian", "in_memory_push_state").
        errors: List of error messages if reset failed or encountered issues.
    """

    ok: bool
    cleared: list[str]
    errors: list[str]


class EndpointFetchError(Exception):
    """Raised when an endpoint fails to fetch (non-auth error).

    This exception is shared across adapters that fetch from multiple endpoints
    (e.g., AppleHealthAdapter, OuraAdapter). It is used to signal that a specific
    endpoint failed, allowing callers to distinguish between partial failures
    (some endpoints succeeded, others failed) and total failures (all endpoints failed).

    Auth errors (HTTPStatusError with 401/403) should be raised directly without
    being caught and converted to this exception, as they indicate configuration
    problems that should terminate the entire fetch operation.
    """

    pass


class PartialFetchError(Exception):
    """Raised when some (but not all) endpoints fail to fetch.

    This exception signals that partial data was successfully retrieved from some
    endpoints, but other endpoints failed. Callers can inspect the failed_endpoints
    list to understand which data sources failed and implement recovery or logging
    strategies.

    Attributes:
        failed_endpoints: List of endpoint paths that failed (e.g., ['/sleep', '/activity'])
        total_endpoints: Total number of endpoints configured
        message: Descriptive message about which endpoints failed
    """

    def __init__(self, failed_endpoints: list[str], total_endpoints: int, message: str = ""):
        """Initialize PartialFetchError.

        Args:
            failed_endpoints: List of endpoint identifiers that failed
            total_endpoints: Total number of endpoints being fetched
            message: Optional custom message; if empty, a default is generated
        """
        self.failed_endpoints = failed_endpoints
        self.total_endpoints = total_endpoints
        if not message:
            endpoints_str = ", ".join(failed_endpoints)
            message = f"Partial fetch failure: {len(failed_endpoints)}/{total_endpoints} endpoint(s) failed: {endpoints_str}"
        super().__init__(message)


class AllEndpointsFailedError(Exception):
    """Raised when all endpoints fail to fetch.

    This exception signals a critical failure where every configured endpoint
    was unable to retrieve data. This typically indicates configuration errors,
    authentication issues, or service outages.

    Attributes:
        total_endpoints: Total number of endpoints that failed
        message: Descriptive message about the failure
    """

    def __init__(self, total_endpoints: int, message: str = ""):
        """Initialize AllEndpointsFailedError.

        Args:
            total_endpoints: Number of endpoints that failed
            message: Optional custom message; if empty, a default is generated
        """
        self.total_endpoints = total_endpoints
        if not message:
            message = f"All {total_endpoints} endpoints failed to fetch. Check API connectivity, credentials, and service status."
        super().__init__(message)


class BaseAdapter(ABC):
    """Abstract base class for content adapters.

    Adapters are responsible for:
    - Fetching raw content from sources
    - Normalizing content into markdown format
    - Extracting structural hints for domain-specific chunking
    - Providing stable identifiers and domain classification
    """

    @abstractmethod
    def fetch(self, source_ref: str) -> Iterator[NormalizedContent]:
        """Fetch and normalize content from a source.

        Args:
            source_ref: Source-specific reference (e.g., directory path, email address).
                Some adapters that receive their source at construction time may ignore
                this parameter.

        Yields:
            NormalizedContent: Normalized markdown content with structural hints
        """
        pass

    @property
    @abstractmethod
    def adapter_id(self) -> str:
        """Return a deterministic, unique identifier for this adapter instance.

        The same adapter type and configuration must always produce the same ID.
        """
        pass

    @property
    @abstractmethod
    def domain(self) -> Domain:
        """Return the semantic domain this adapter serves.

        All content from this adapter belongs to this domain.
        """
        pass

    @property
    @abstractmethod
    def normalizer_version(self) -> str:
        """Return the version of the normalizer implementation.

        Used to track when normalization behavior changes.
        """
        pass

    def register(self, document_store: DocumentStore) -> str:
        """Register this adapter with the document store.

        Args:
            document_store: DocumentStore instance to register with

        Returns:
            The adapter_id returned by document_store.register_adapter()
        """
        config = AdapterConfig(
            adapter_id=self.adapter_id,
            adapter_type=type(self).__name__,
            domain=self.domain,
            normalizer_version=self.normalizer_version,
            config=None,
        )
        return document_store.register_adapter(config)

    def reset(self) -> ResetResult:
        """Reset the adapter's helper-side delivery state.

        Default implementation returns a no-op success result. Adapters that
        communicate with stateful helper services (e.g., RemoteAdapter subclasses)
        should override this method to call the helper's reset endpoint.

        Returns:
            ResetResult with ok=True, empty cleared list, and no errors.
        """
        return ResetResult(ok=True, cleared=[], errors=[])
