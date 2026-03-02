"""Tests for the base adapter module."""

import pytest
from unittest.mock import MagicMock, patch

from context_library.adapters.base import BaseAdapter
from context_library.storage.models import (
    AdapterConfig,
    Domain,
    NormalizedContent,
    StructuralHints,
)


class ConcreteAdapter(BaseAdapter):
    """Concrete implementation of BaseAdapter for testing."""

    def __init__(
        self,
        adapter_id: str = "test:adapter",
        domain: Domain = Domain.NOTES,
        normalizer_version: str = "1.0.0",
    ):
        self._adapter_id = adapter_id
        self._domain = domain
        self._normalizer_version = normalizer_version

    @property
    def adapter_id(self) -> str:
        return self._adapter_id

    @property
    def domain(self) -> Domain:
        return self._domain

    @property
    def normalizer_version(self) -> str:
        return self._normalizer_version

    def fetch(self, source_ref: str):
        """Simple fetch implementation for testing."""
        hints = StructuralHints(
            has_headings=True,
            has_lists=False,
            has_tables=False,
            natural_boundaries=[],
        )
        yield NormalizedContent(
            markdown="# Test\n\nContent",
            source_id="test:source",
            structural_hints=hints,
            normalizer_version=self.normalizer_version,
        )


class TestBaseAdapterContract:
    """Tests for BaseAdapter abstract contract."""

    def test_cannot_instantiate_abstract_base(self):
        """BaseAdapter cannot be instantiated directly."""
        with pytest.raises(TypeError):
            BaseAdapter()

    def test_requires_fetch_method(self):
        """Subclass must implement fetch method."""

        class IncompleteAdapter(BaseAdapter):
            @property
            def adapter_id(self) -> str:
                return "incomplete"

            @property
            def domain(self) -> Domain:
                return Domain.NOTES

            @property
            def normalizer_version(self) -> str:
                return "1.0.0"

        with pytest.raises(TypeError):
            IncompleteAdapter()

    def test_requires_adapter_id_property(self):
        """Subclass must implement adapter_id property."""

        class IncompleteAdapter(BaseAdapter):
            @property
            def domain(self) -> Domain:
                return Domain.NOTES

            @property
            def normalizer_version(self) -> str:
                return "1.0.0"

            def fetch(self, source_ref: str):
                pass

        with pytest.raises(TypeError):
            IncompleteAdapter()

    def test_requires_domain_property(self):
        """Subclass must implement domain property."""

        class IncompleteAdapter(BaseAdapter):
            @property
            def adapter_id(self) -> str:
                return "incomplete"

            @property
            def normalizer_version(self) -> str:
                return "1.0.0"

            def fetch(self, source_ref: str):
                pass

        with pytest.raises(TypeError):
            IncompleteAdapter()

    def test_requires_normalizer_version_property(self):
        """Subclass must implement normalizer_version property."""

        class IncompleteAdapter(BaseAdapter):
            @property
            def adapter_id(self) -> str:
                return "incomplete"

            @property
            def domain(self) -> Domain:
                return Domain.NOTES

            def fetch(self, source_ref: str):
                pass

        with pytest.raises(TypeError):
            IncompleteAdapter()


class TestBaseAdapterRegister:
    """Tests for the register() concrete method."""

    def test_register_calls_document_store(self):
        """register() calls document_store.register_adapter() with correct config."""
        adapter = ConcreteAdapter(
            adapter_id="test:adapter",
            domain=Domain.NOTES,
            normalizer_version="1.0.0",
        )
        mock_store = MagicMock()
        mock_store.register_adapter.return_value = "test:adapter"

        result = adapter.register(mock_store)

        mock_store.register_adapter.assert_called_once()
        call_args = mock_store.register_adapter.call_args[0][0]

        assert isinstance(call_args, AdapterConfig)
        assert call_args.adapter_id == "test:adapter"
        assert call_args.adapter_type == "ConcreteAdapter"
        assert call_args.domain == Domain.NOTES
        assert call_args.normalizer_version == "1.0.0"
        assert call_args.config is None
        assert result == "test:adapter"

    def test_register_returns_adapter_id(self):
        """register() returns the adapter_id from document_store."""
        adapter = ConcreteAdapter(adapter_id="my:adapter")
        mock_store = MagicMock()
        mock_store.register_adapter.return_value = "my:adapter"

        result = adapter.register(mock_store)

        assert result == "my:adapter"

    def test_register_builds_correct_config(self):
        """register() constructs AdapterConfig with correct fields."""
        adapter = ConcreteAdapter(
            adapter_id="test:unique",
            domain=Domain.EVENTS,
            normalizer_version="2.0.0",
        )
        mock_store = MagicMock()

        adapter.register(mock_store)

        config = mock_store.register_adapter.call_args[0][0]
        assert config.adapter_id == "test:unique"
        assert config.adapter_type == "ConcreteAdapter"
        assert config.domain == Domain.EVENTS
        assert config.normalizer_version == "2.0.0"

    def test_register_with_different_domains(self):
        """register() works with all domain types."""
        for domain in [Domain.MESSAGES, Domain.NOTES, Domain.EVENTS, Domain.TASKS]:
            adapter = ConcreteAdapter(domain=domain)
            mock_store = MagicMock()

            adapter.register(mock_store)

            config = mock_store.register_adapter.call_args[0][0]
            assert config.domain == domain
