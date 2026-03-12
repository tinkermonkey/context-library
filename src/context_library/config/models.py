"""Pydantic models defining the adapter configuration schema.

This module defines the data models for declaratively configuring adapters
(both local and remote) via YAML/TOML/JSON configuration files.

Configuration examples:

  remote_adapters:
    - service_url: http://mac-server:8001
      domain: notes
      adapter_id: obsidian:vault
      api_key: shared-secret
      normalizer_version: "1.0.0"
      timeout: 30.0

  local_adapters:
    - adapter_type: filesystem
      domain: notes
      adapter_id: local:filesystem
      config:
        root_path: /path/to/files
"""

from typing import Any

from pydantic import BaseModel, ConfigDict, field_validator

from context_library.storage.models import Domain


class RemoteAdapterConfig(BaseModel):
    """Configuration for a RemoteAdapter instance.

    Specifies the remote service URL and connection parameters needed to
    instantiate a RemoteAdapter that communicates with a remote adapter service.

    Invariants:
    - service_url must be a valid HTTP(S) URL
    - domain must be a valid Domain enum value
    - adapter_id must be a non-empty string
    - api_key must not be an empty string (None is allowed)
    - normalizer_version must be a non-empty string
    - timeout must be positive
    """

    model_config = ConfigDict(extra="forbid")

    service_url: str
    domain: Domain
    adapter_id: str
    normalizer_version: str = "1.0.0"
    api_key: str | None = None
    timeout: float = 30.0

    @field_validator("service_url")
    @classmethod
    def validate_service_url(cls, value: str) -> str:
        """Validate that service_url is a valid HTTP(S) URL."""
        if not value.startswith(("http://", "https://")):
            raise ValueError(
                f"service_url must start with http:// or https://, got: {value}"
            )
        return value

    @field_validator("adapter_id")
    @classmethod
    def validate_adapter_id(cls, value: str) -> str:
        """Validate that adapter_id is not empty."""
        if not value:
            raise ValueError("adapter_id must be a non-empty string")
        return value

    @field_validator("api_key")
    @classmethod
    def validate_api_key(cls, value: str | None) -> str | None:
        """Validate that api_key is not an empty string."""
        if value is not None and not value:
            raise ValueError("api_key must not be an empty string (use None to omit)")
        return value

    @field_validator("normalizer_version")
    @classmethod
    def validate_normalizer_version(cls, value: str) -> str:
        """Validate that normalizer_version is not empty."""
        if not value:
            raise ValueError("normalizer_version must be a non-empty string")
        return value

    @field_validator("timeout")
    @classmethod
    def validate_timeout(cls, value: float) -> float:
        """Validate that timeout is positive."""
        if value <= 0:
            raise ValueError(f"timeout must be positive, got: {value}")
        return value


class LocalAdapterConfig(BaseModel):
    """Configuration for a local (file-based) adapter instance.

    Specifies the adapter type and domain, plus optional configuration
    parameters passed to the adapter constructor.

    Note on domain and adapter_id:
        These fields are used for validation and identification within the
        configuration file. However, the actual domain and adapter_id used by
        the adapter instance are typically derived from the adapter's own
        configuration or hardcoded values. For example, FilesystemAdapter
        hardcodes domain=NOTES and derives adapter_id from its file path.
        These configuration fields are NOT passed to the adapter constructor.

    Invariants:
    - adapter_type must be a non-empty string
    - domain must be a valid Domain enum value
    - adapter_id must be a non-empty string
    - config dict values can be any JSON-serializable type
    """

    model_config = ConfigDict(extra="forbid")

    adapter_type: str
    domain: Domain
    adapter_id: str
    config: dict[str, Any] | None = None

    @field_validator("adapter_type")
    @classmethod
    def validate_adapter_type(cls, value: str) -> str:
        """Validate that adapter_type is not empty."""
        if not value:
            raise ValueError("adapter_type must be a non-empty string")
        return value

    @field_validator("adapter_id")
    @classmethod
    def validate_adapter_id(cls, value: str) -> str:
        """Validate that adapter_id is not empty."""
        if not value:
            raise ValueError("adapter_id must be a non-empty string")
        return value


class AdaptersConfig(BaseModel):
    """Top-level configuration for all adapters.

    Defines the complete set of adapters to instantiate: both remote adapters
    (accessed via HTTP) and local adapters (instantiated directly).

    Used to deserialize adapter configuration from YAML/TOML/JSON files.

    Invariants:
    - At least one of remote_adapters or local_adapters must be provided
    - All adapter_ids (across both lists) must be unique within the configuration
    """

    model_config = ConfigDict(extra="forbid")

    remote_adapters: list[RemoteAdapterConfig] = []
    local_adapters: list[LocalAdapterConfig] = []

    def model_post_init(self, __context: Any) -> None:
        """Validate AdaptersConfig invariants after model construction.

        Enforces:
        - At least one adapter (remote or local) is defined
        - All adapter_ids are unique across both lists
        """
        if not self.remote_adapters and not self.local_adapters:
            raise ValueError(
                "At least one adapter must be defined (remote_adapters or local_adapters)"
            )

        # Collect all adapter_ids and check for duplicates
        all_adapter_ids = [
            config.adapter_id for config in self.remote_adapters
        ] + [config.adapter_id for config in self.local_adapters]

        seen = set()
        for adapter_id in all_adapter_ids:
            if adapter_id in seen:
                raise ValueError(
                    f"Duplicate adapter_id found: {adapter_id!r}. "
                    "All adapter_ids must be unique."
                )
            seen.add(adapter_id)
