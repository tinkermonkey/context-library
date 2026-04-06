"""Tests for AppleNotesAdapter."""

import pytest

# Skip all tests in this module if mistune is not installed
# (required by AppleNotesAdapter -> domains/notes.py)
pytest.importorskip("mistune")


from context_library.adapters.apple_notes import AppleNotesAdapter
from context_library.storage.models import Domain, PollStrategy


class TestAppleNotesAdapterInitialization:
    """Tests for AppleNotesAdapter initialization."""

    def test_init_valid_credentials(self):
        """Adapter initializes with valid credentials."""
        adapter = AppleNotesAdapter(
            api_url="http://localhost:7123",
            api_key="test-key",
        )
        assert adapter.adapter_id == "apple_notes:default"
        assert adapter.domain == Domain.NOTES
        assert adapter.poll_strategy == PollStrategy.PULL

    def test_init_custom_account_id(self):
        """Adapter accepts custom account_id parameter."""
        adapter = AppleNotesAdapter(
            api_url="http://localhost:7123",
            api_key="test-key",
            account_id="work-account",
        )
        assert adapter.adapter_id == "apple_notes:work-account"

    def test_init_with_folder_filter(self):
        """Adapter accepts optional folder_filter parameter."""
        adapter = AppleNotesAdapter(
            api_url="http://localhost:7123",
            api_key="test-key",
            folder_filter="Work",
        )
        assert adapter.adapter_id == "apple_notes:default"

    def test_init_requires_api_key(self):
        """Adapter raises ValueError if api_key is empty."""
        with pytest.raises(ValueError, match="api_key is required"):
            AppleNotesAdapter(
                api_url="http://localhost:7123",
                api_key="",
            )

    def test_normalizer_version(self):
        """Adapter has a normalizer version."""
        adapter = AppleNotesAdapter(
            api_url="http://localhost:7123",
            api_key="test-key",
        )
        assert adapter.normalizer_version == "1.0.0"


class TestAppleNotesAdapterImportability:
    """Test adapter is properly importable."""

    def test_importable_from_context_library_adapters(self):
        """AppleNotesAdapter is importable from context_library.adapters."""
        from context_library.adapters import AppleNotesAdapter as ImportedAdapter
        assert ImportedAdapter is AppleNotesAdapter
