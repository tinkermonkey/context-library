"""Tests for AppleiMessageAdapter."""

import pytest

# Skip all tests in this module if mistune is not installed
# (required by AppleiMessageAdapter -> domains/messages.py which imports from domains/__init__.py)
pytest.importorskip("mistune")

import httpx

from context_library.adapters.apple_imessage import AppleiMessageAdapter
from context_library.storage.models import Domain, PollStrategy


class TestAppleiMessageAdapterInitialization:
    """Tests for AppleiMessageAdapter initialization."""

    def test_init_valid_credentials(self):
        """Adapter initializes with valid credentials."""
        adapter = AppleiMessageAdapter(
            api_url="http://localhost:7123",
            api_key="test-key",
        )
        assert adapter.adapter_id == "apple_imessage:default"
        assert adapter.domain == Domain.MESSAGES
        assert adapter.poll_strategy == PollStrategy.PULL

    def test_init_custom_account_id(self):
        """Adapter accepts custom account_id parameter."""
        adapter = AppleiMessageAdapter(
            api_url="http://localhost:7123",
            api_key="test-key",
            account_id="work-account",
        )
        assert adapter.adapter_id == "apple_imessage:work-account"

    def test_init_requires_api_key(self):
        """Adapter raises ValueError if api_key is empty."""
        with pytest.raises(ValueError, match="api_key is required"):
            AppleiMessageAdapter(
                api_url="http://localhost:7123",
                api_key="",
            )

    def test_normalizer_version(self):
        """Adapter has a normalizer version."""
        adapter = AppleiMessageAdapter(
            api_url="http://localhost:7123",
            api_key="test-key",
        )
        assert adapter.normalizer_version == "1.0.0"


class TestAppleiMessageAdapterImportability:
    """Test adapter is properly importable."""

    def test_importable_from_context_library_adapters(self):
        """AppleiMessageAdapter is importable from context_library.adapters."""
        from context_library.adapters import AppleiMessageAdapter as ImportedAdapter
        assert ImportedAdapter is AppleiMessageAdapter
