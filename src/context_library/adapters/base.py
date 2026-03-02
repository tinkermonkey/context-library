"""Abstract BaseAdapter defining the adapter contract."""

from abc import ABC, abstractmethod
from typing import Iterator

from context_library.storage.models import AdapterConfig, Domain, NormalizedContent
from context_library.storage.document_store import DocumentStore


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
