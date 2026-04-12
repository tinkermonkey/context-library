"""Tests for ObsidianHelperAdapter."""

from unittest.mock import MagicMock, patch

import pytest
import httpx
from pydantic import ValidationError

from context_library.adapters.obsidian_helper import ObsidianHelperAdapter
from context_library.adapters.base import ResetResult


# ── Fixtures ──────────────────────────────────────────────────────────────────


def _make_mock_response(data, status_code: int = 200):
    """Return a mock httpx response."""
    mock = MagicMock()
    mock.status_code = status_code
    mock.json.return_value = data
    if status_code >= 400:
        mock.raise_for_status.side_effect = httpx.HTTPStatusError(
            f"HTTP {status_code}",
            request=MagicMock(),
            response=MagicMock(status_code=status_code, text="error"),
        )
    else:
        mock.raise_for_status.return_value = None
    return mock


def _make_adapter(**kwargs) -> ObsidianHelperAdapter:
    """Create adapter with mock httpx.Client so no real HTTP is made."""
    defaults = {"api_url": "http://localhost:7123", "api_key": "test-key"}
    defaults.update(kwargs)
    with patch("httpx.Client"):
        adapter = ObsidianHelperAdapter(**defaults)
    return adapter


# ── Initialization tests ──────────────────────────────────────────────────────


class TestObsidianHelperAdapterInitialization:
    def test_init_stores_api_url(self):
        adapter = _make_adapter(api_url="http://192.168.1.50:7123")
        assert adapter._service_url == "http://192.168.1.50:7123"

    def test_init_strips_trailing_slash(self):
        adapter = _make_adapter(api_url="http://192.168.1.50:7123/")
        assert adapter._service_url == "http://192.168.1.50:7123"

    def test_init_stores_api_key(self):
        adapter = _make_adapter(api_key="my-secret")
        assert adapter._api_key == "my-secret"

    def test_init_default_vault_id(self):
        adapter = _make_adapter()
        assert adapter._vault_id == "default"

    def test_init_custom_vault_id(self):
        adapter = _make_adapter(vault_id="main")
        assert adapter._vault_id == "main"

    def test_adapter_id_property(self):
        adapter = _make_adapter(vault_id="main")
        assert adapter.adapter_id == "obsidian_helper:main"


# ── Reset tests ───────────────────────────────────────────────────────────────


class TestObsidianHelperAdapterReset:
    def test_reset_success_returns_result(self):
        """reset() returns ResetResult on successful response."""
        adapter = _make_adapter()
        adapter._client.post.return_value = _make_mock_response(
            {"ok": True, "cleared": ["sync_cursor"], "errors": []}
        )

        result = adapter.reset()

        assert isinstance(result, ResetResult)
        assert result.ok is True
        assert result.cleared == ["sync_cursor"]
        assert result.errors == []

        # Verify POST was called to correct endpoint with auth
        adapter._client.post.assert_called_once()
        call_args = adapter._client.post.call_args
        assert "/collectors/obsidian/reset" in call_args[0][0]
        assert call_args[1]["headers"]["Authorization"] == "Bearer test-key"

    def test_reset_with_errors_returns_ok_false(self):
        """reset() returns ResetResult with ok=False when helper reports errors."""
        adapter = _make_adapter()
        adapter._client.post.return_value = _make_mock_response(
            {"ok": False, "cleared": [], "errors": ["vault_locked", "sync_in_progress"]}
        )

        result = adapter.reset()

        assert result.ok is False
        assert result.cleared == []
        assert result.errors == ["vault_locked", "sync_in_progress"]

    def test_reset_raises_on_http_4xx(self):
        """reset() raises HTTPStatusError on 4xx response."""
        adapter = _make_adapter()
        adapter._client.post.return_value = _make_mock_response({}, status_code=403)

        with pytest.raises(httpx.HTTPStatusError):
            adapter.reset()

    def test_reset_raises_on_http_5xx(self):
        """reset() raises HTTPStatusError on 5xx response."""
        adapter = _make_adapter()
        adapter._client.post.return_value = _make_mock_response({}, status_code=500)

        with pytest.raises(httpx.HTTPStatusError):
            adapter.reset()

    def test_reset_raises_on_malformed_json(self):
        """reset() raises ValueError when response is not valid JSON."""
        adapter = _make_adapter()
        mock_response = MagicMock()
        mock_response.raise_for_status.return_value = None
        mock_response.json.side_effect = ValueError("Invalid JSON")
        adapter._client.post.return_value = mock_response

        with pytest.raises(ValueError):
            adapter.reset()

    def test_reset_raises_on_missing_fields(self):
        """reset() raises ValidationError when response is missing required fields."""
        adapter = _make_adapter()
        # Missing 'cleared' field
        adapter._client.post.return_value = _make_mock_response(
            {"ok": True, "errors": []}
        )

        with pytest.raises(ValidationError):
            adapter.reset()

    def test_reset_raises_on_invalid_field_types(self):
        """reset() raises ValidationError when response fields have wrong types."""
        adapter = _make_adapter()
        # cleared should be list, not dict
        adapter._client.post.return_value = _make_mock_response(
            {"ok": True, "cleared": {"cursor": "sync"}, "errors": []}
        )

        with pytest.raises(ValidationError):
            adapter.reset()
