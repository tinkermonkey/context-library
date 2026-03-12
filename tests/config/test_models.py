"""Tests for configuration Pydantic models.

Tests validation of RemoteAdapterConfig, LocalAdapterConfig, and AdaptersConfig.
Ensures schema constraints are enforced and helpful error messages are provided.
"""

import pytest
from pydantic import ValidationError

from context_library.config.models import (
    AdaptersConfig,
    LocalAdapterConfig,
    RemoteAdapterConfig,
)
from context_library.storage.models import Domain


class TestRemoteAdapterConfig:
    """Tests for RemoteAdapterConfig validation."""

    def test_valid_minimal_config(self) -> None:
        """Test valid remote adapter config with minimal parameters."""
        config = RemoteAdapterConfig(
            service_url="http://localhost:8001",
            domain=Domain.NOTES,
            adapter_id="test:adapter",
        )
        assert config.service_url == "http://localhost:8001"
        assert config.domain == Domain.NOTES
        assert config.adapter_id == "test:adapter"
        assert config.normalizer_version == "1.0.0"
        assert config.api_key is None
        assert config.timeout == 30.0

    def test_valid_full_config(self) -> None:
        """Test valid remote adapter config with all parameters."""
        config = RemoteAdapterConfig(
            service_url="https://mac-server:8001",
            domain=Domain.MESSAGES,
            adapter_id="obsidian:vault",
            api_key="secret-key",
            normalizer_version="2.0.0",
            timeout=60.0,
        )
        assert config.service_url == "https://mac-server:8001"
        assert config.domain == Domain.MESSAGES
        assert config.adapter_id == "obsidian:vault"
        assert config.api_key == "secret-key"
        assert config.normalizer_version == "2.0.0"
        assert config.timeout == 60.0

    def test_invalid_service_url_missing_protocol(self) -> None:
        """Test that service_url without http/https is rejected."""
        with pytest.raises(ValidationError) as exc_info:
            RemoteAdapterConfig(
                service_url="localhost:8001",
                domain=Domain.NOTES,
                adapter_id="test:adapter",
            )
        assert "service_url must start with http:// or https://" in str(
            exc_info.value
        )

    def test_invalid_service_url_bad_protocol(self) -> None:
        """Test that service_url with ftp:// is rejected."""
        with pytest.raises(ValidationError) as exc_info:
            RemoteAdapterConfig(
                service_url="ftp://server:8001",
                domain=Domain.NOTES,
                adapter_id="test:adapter",
            )
        assert "service_url must start with http:// or https://" in str(
            exc_info.value
        )

    def test_invalid_empty_adapter_id(self) -> None:
        """Test that empty adapter_id is rejected."""
        with pytest.raises(ValidationError) as exc_info:
            RemoteAdapterConfig(
                service_url="http://localhost:8001",
                domain=Domain.NOTES,
                adapter_id="",
            )
        assert "adapter_id must be a non-empty string" in str(exc_info.value)

    def test_invalid_empty_api_key(self) -> None:
        """Test that empty string api_key is rejected."""
        with pytest.raises(ValidationError) as exc_info:
            RemoteAdapterConfig(
                service_url="http://localhost:8001",
                domain=Domain.NOTES,
                adapter_id="test:adapter",
                api_key="",
            )
        assert "api_key must not be an empty string" in str(exc_info.value)

    def test_valid_none_api_key(self) -> None:
        """Test that None api_key is allowed."""
        config = RemoteAdapterConfig(
            service_url="http://localhost:8001",
            domain=Domain.NOTES,
            adapter_id="test:adapter",
            api_key=None,
        )
        assert config.api_key is None

    def test_invalid_empty_normalizer_version(self) -> None:
        """Test that empty normalizer_version is rejected."""
        with pytest.raises(ValidationError) as exc_info:
            RemoteAdapterConfig(
                service_url="http://localhost:8001",
                domain=Domain.NOTES,
                adapter_id="test:adapter",
                normalizer_version="",
            )
        assert "normalizer_version must be a non-empty string" in str(exc_info.value)

    def test_invalid_negative_timeout(self) -> None:
        """Test that negative timeout is rejected."""
        with pytest.raises(ValidationError) as exc_info:
            RemoteAdapterConfig(
                service_url="http://localhost:8001",
                domain=Domain.NOTES,
                adapter_id="test:adapter",
                timeout=-1.0,
            )
        assert "timeout must be positive" in str(exc_info.value)

    def test_invalid_zero_timeout(self) -> None:
        """Test that zero timeout is rejected."""
        with pytest.raises(ValidationError) as exc_info:
            RemoteAdapterConfig(
                service_url="http://localhost:8001",
                domain=Domain.NOTES,
                adapter_id="test:adapter",
                timeout=0.0,
            )
        assert "timeout must be positive" in str(exc_info.value)

    def test_forbid_extra_fields(self) -> None:
        """Test that extra fields are rejected."""
        with pytest.raises(ValidationError) as exc_info:
            RemoteAdapterConfig(
                service_url="http://localhost:8001",
                domain=Domain.NOTES,
                adapter_id="test:adapter",
                extra_field="should not be allowed",
            )
        assert "extra_field" in str(exc_info.value)


class TestLocalAdapterConfig:
    """Tests for LocalAdapterConfig validation."""

    def test_valid_minimal_config(self) -> None:
        """Test valid local adapter config with minimal parameters."""
        config = LocalAdapterConfig(
            adapter_type="filesystem",
            domain=Domain.NOTES,
            adapter_id="local:files",
        )
        assert config.adapter_type == "filesystem"
        assert config.domain == Domain.NOTES
        assert config.adapter_id == "local:files"
        assert config.config is None

    def test_valid_config_with_parameters(self) -> None:
        """Test valid local adapter config with custom parameters."""
        config = LocalAdapterConfig(
            adapter_type="obsidian",
            domain=Domain.NOTES,
            adapter_id="obsidian:vault",
            config={"root_path": "/home/user/vault", "nested": {"param": "value"}},
        )
        assert config.adapter_type == "obsidian"
        assert config.config == {"root_path": "/home/user/vault", "nested": {"param": "value"}}

    def test_invalid_empty_adapter_type(self) -> None:
        """Test that empty adapter_type is rejected."""
        with pytest.raises(ValidationError) as exc_info:
            LocalAdapterConfig(
                adapter_type="",
                domain=Domain.NOTES,
                adapter_id="test:adapter",
            )
        assert "adapter_type must be a non-empty string" in str(exc_info.value)

    def test_invalid_empty_adapter_id(self) -> None:
        """Test that empty adapter_id is rejected."""
        with pytest.raises(ValidationError) as exc_info:
            LocalAdapterConfig(
                adapter_type="filesystem",
                domain=Domain.NOTES,
                adapter_id="",
            )
        assert "adapter_id must be a non-empty string" in str(exc_info.value)

    def test_forbid_extra_fields(self) -> None:
        """Test that extra fields are rejected."""
        with pytest.raises(ValidationError) as exc_info:
            LocalAdapterConfig(
                adapter_type="filesystem",
                domain=Domain.NOTES,
                adapter_id="test:adapter",
                extra_field="should not be allowed",
            )
        assert "extra_field" in str(exc_info.value)


class TestAdaptersConfig:
    """Tests for AdaptersConfig validation."""

    def test_valid_remote_only(self) -> None:
        """Test valid config with only remote adapters."""
        config = AdaptersConfig(
            remote_adapters=[
                RemoteAdapterConfig(
                    service_url="http://localhost:8001",
                    domain=Domain.NOTES,
                    adapter_id="remote:notes",
                )
            ]
        )
        assert len(config.remote_adapters) == 1
        assert len(config.local_adapters) == 0

    def test_valid_local_only(self) -> None:
        """Test valid config with only local adapters."""
        config = AdaptersConfig(
            local_adapters=[
                LocalAdapterConfig(
                    adapter_type="filesystem",
                    domain=Domain.NOTES,
                    adapter_id="local:files",
                )
            ]
        )
        assert len(config.remote_adapters) == 0
        assert len(config.local_adapters) == 1

    def test_valid_mixed_adapters(self) -> None:
        """Test valid config with both remote and local adapters."""
        config = AdaptersConfig(
            remote_adapters=[
                RemoteAdapterConfig(
                    service_url="http://localhost:8001",
                    domain=Domain.NOTES,
                    adapter_id="remote:notes",
                )
            ],
            local_adapters=[
                LocalAdapterConfig(
                    adapter_type="filesystem",
                    domain=Domain.EVENTS,
                    adapter_id="local:files",
                )
            ],
        )
        assert len(config.remote_adapters) == 1
        assert len(config.local_adapters) == 1

    def test_invalid_no_adapters(self) -> None:
        """Test that config with no adapters is rejected."""
        with pytest.raises(ValidationError) as exc_info:
            AdaptersConfig()
        assert "At least one adapter must be defined" in str(exc_info.value)

    def test_invalid_duplicate_adapter_ids_same_list(self) -> None:
        """Test that duplicate adapter_ids in same list are rejected."""
        with pytest.raises(ValidationError) as exc_info:
            AdaptersConfig(
                remote_adapters=[
                    RemoteAdapterConfig(
                        service_url="http://localhost:8001",
                        domain=Domain.NOTES,
                        adapter_id="duplicate",
                    ),
                    RemoteAdapterConfig(
                        service_url="http://localhost:8002",
                        domain=Domain.MESSAGES,
                        adapter_id="duplicate",
                    ),
                ]
            )
        assert "Duplicate adapter_id found: 'duplicate'" in str(exc_info.value)

    def test_invalid_duplicate_adapter_ids_different_lists(self) -> None:
        """Test that duplicate adapter_ids across lists are rejected."""
        with pytest.raises(ValidationError) as exc_info:
            AdaptersConfig(
                remote_adapters=[
                    RemoteAdapterConfig(
                        service_url="http://localhost:8001",
                        domain=Domain.NOTES,
                        adapter_id="shared:id",
                    )
                ],
                local_adapters=[
                    LocalAdapterConfig(
                        adapter_type="filesystem",
                        domain=Domain.EVENTS,
                        adapter_id="shared:id",
                    )
                ],
            )
        assert "Duplicate adapter_id found: 'shared:id'" in str(exc_info.value)

    def test_forbid_extra_fields(self) -> None:
        """Test that extra fields are rejected."""
        with pytest.raises(ValidationError) as exc_info:
            AdaptersConfig(
                remote_adapters=[
                    RemoteAdapterConfig(
                        service_url="http://localhost:8001",
                        domain=Domain.NOTES,
                        adapter_id="test:adapter",
                    )
                ],
                extra_field="should not be allowed",
            )
        assert "extra_field" in str(exc_info.value)

    def test_valid_multiple_adapters_unique_ids(self) -> None:
        """Test valid config with multiple adapters with unique IDs."""
        config = AdaptersConfig(
            remote_adapters=[
                RemoteAdapterConfig(
                    service_url="http://localhost:8001",
                    domain=Domain.NOTES,
                    adapter_id="remote:notes",
                ),
                RemoteAdapterConfig(
                    service_url="http://localhost:8002",
                    domain=Domain.MESSAGES,
                    adapter_id="remote:messages",
                ),
            ],
            local_adapters=[
                LocalAdapterConfig(
                    adapter_type="filesystem",
                    domain=Domain.EVENTS,
                    adapter_id="local:events",
                ),
            ],
        )
        assert len(config.remote_adapters) == 2
        assert len(config.local_adapters) == 1
