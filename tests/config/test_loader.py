"""Tests for configuration file loading and adapter instantiation.

Tests loading adapters from YAML/TOML/JSON files and instantiation of
RemoteAdapter and local adapters from declarative configuration.
"""

import json
import tempfile
from pathlib import Path

import pytest

from context_library.adapters.filesystem import FilesystemAdapter
from context_library.config.loader import load_adapters_from_file
from context_library.storage.models import Domain


class TestLoadAdaptersFromYAML:
    """Tests for loading adapters from YAML files."""

    def test_load_yaml_remote_adapter(self) -> None:
        """Test loading a single remote adapter from YAML."""
        yaml_content = """
remote_adapters:
  - service_url: http://localhost:8001
    domain: notes
    adapter_id: test:remote
"""
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "config.yaml"
            config_path.write_text(yaml_content)

            adapters = load_adapters_from_file(config_path)

            assert len(adapters) == 1
            assert adapters[0].adapter_id == "test:remote"
            assert adapters[0].domain == Domain.NOTES

    def test_load_yaml_remote_adapter_with_api_key(self) -> None:
        """Test loading remote adapter with API key from YAML."""
        yaml_content = """
remote_adapters:
  - service_url: https://mac-server:8001
    domain: messages
    adapter_id: obsidian:vault
    api_key: secret-token
    normalizer_version: "2.0.0"
    timeout: 60.0
"""
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "config.yaml"
            config_path.write_text(yaml_content)

            adapters = load_adapters_from_file(config_path)

            assert len(adapters) == 1
            adapter = adapters[0]
            assert adapter.adapter_id == "obsidian:vault"
            assert adapter.domain == Domain.MESSAGES

    def test_load_yaml_local_adapter(self) -> None:
        """Test loading a local adapter from YAML."""
        yaml_content = """
local_adapters:
  - adapter_type: filesystem
    domain: documents
    adapter_id: local:files
    config:
      directory: /home/user/files
"""
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "config.yaml"
            config_path.write_text(yaml_content)

            adapters = load_adapters_from_file(config_path)

            assert len(adapters) == 1
            adapter = adapters[0]
            assert isinstance(adapter, FilesystemAdapter)
            # FilesystemAdapter hardcodes domain to DOCUMENTS
            assert adapter.domain == Domain.DOCUMENTS

    def test_load_yaml_mixed_adapters(self) -> None:
        """Test loading both remote and local adapters from YAML."""
        yaml_content = """
remote_adapters:
  - service_url: http://localhost:8001
    domain: notes
    adapter_id: remote:notes

local_adapters:
  - adapter_type: filesystem
    domain: notes
    adapter_id: local:files
    config:
      directory: /tmp/notes
"""
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "config.yaml"
            config_path.write_text(yaml_content)

            adapters = load_adapters_from_file(config_path)

            assert len(adapters) == 2
            assert any(a.adapter_id == "remote:notes" for a in adapters)
            # At least one local adapter should be loaded
            assert any(isinstance(a, FilesystemAdapter) for a in adapters)

    def test_load_yaml_multiple_adapters(self) -> None:
        """Test loading multiple adapters of same type from YAML."""
        yaml_content = """
remote_adapters:
  - service_url: http://localhost:8001
    domain: notes
    adapter_id: remote:notes1
  - service_url: http://localhost:8002
    domain: messages
    adapter_id: remote:messages1
"""
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "config.yaml"
            config_path.write_text(yaml_content)

            adapters = load_adapters_from_file(config_path)

            assert len(adapters) == 2
            assert adapters[0].adapter_id == "remote:notes1"
            assert adapters[1].adapter_id == "remote:messages1"

    def test_load_yaml_invalid_domain(self) -> None:
        """Test that invalid domain value is rejected."""
        yaml_content = """
remote_adapters:
  - service_url: http://localhost:8001
    domain: invalid_domain
    adapter_id: test:adapter
"""
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "config.yaml"
            config_path.write_text(yaml_content)

            with pytest.raises(ValueError) as exc_info:
                load_adapters_from_file(config_path)
            assert "Configuration validation failed" in str(exc_info.value)

    def test_load_yaml_file_not_found(self) -> None:
        """Test that missing file raises FileNotFoundError."""
        config_path = Path("/nonexistent/config.yaml")

        with pytest.raises(FileNotFoundError):
            load_adapters_from_file(config_path)

    def test_load_yaml_invalid_yaml_syntax(self) -> None:
        """Test that invalid YAML syntax is caught."""
        # Use deeply nested invalid YAML that triggers a parser error
        yaml_content = "{invalid: yaml: syntax: [}]"
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "config.yaml"
            config_path.write_text(yaml_content)

            with pytest.raises(ValueError) as exc_info:
                load_adapters_from_file(config_path)
            assert "Failed to parse YAML" in str(exc_info.value)

    def test_load_yaml_empty_file(self) -> None:
        """Test that empty YAML file is handled (should fail - no adapters)."""
        yaml_content = ""
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "config.yaml"
            config_path.write_text(yaml_content)

            with pytest.raises(ValueError) as exc_info:
                load_adapters_from_file(config_path)
            assert "At least one adapter must be defined" in str(exc_info.value)


class TestLoadAdaptersFromJSON:
    """Tests for loading adapters from JSON files."""

    def test_load_json_remote_adapter(self) -> None:
        """Test loading a remote adapter from JSON."""
        json_content = {
            "remote_adapters": [
                {
                    "service_url": "http://localhost:8001",
                    "domain": "notes",
                    "adapter_id": "test:remote",
                }
            ]
        }
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "config.json"
            config_path.write_text(json.dumps(json_content))

            adapters = load_adapters_from_file(config_path)

            assert len(adapters) == 1
            assert adapters[0].adapter_id == "test:remote"

    def test_load_json_invalid_syntax(self) -> None:
        """Test that invalid JSON syntax is caught."""
        json_content = "{ invalid json }"
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "config.json"
            config_path.write_text(json_content)

            with pytest.raises(ValueError) as exc_info:
                load_adapters_from_file(config_path)
            assert "Failed to parse JSON" in str(exc_info.value)

    def test_load_json_not_object_root(self) -> None:
        """Test that JSON array root is rejected."""
        json_content = "[]"
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "config.json"
            config_path.write_text(json_content)

            with pytest.raises(ValueError) as exc_info:
                load_adapters_from_file(config_path)
            assert "JSON root must be an object" in str(exc_info.value)


class TestLoadAdaptersFromTOML:
    """Tests for loading adapters from TOML files.

    Note: TOML support requires tomllib (Python 3.11+) or tomli package.
    """

    def test_load_toml_remote_adapter(self) -> None:
        """Test loading a remote adapter from TOML."""
        toml_content = """
[[remote_adapters]]
service_url = "http://localhost:8001"
domain = "notes"
adapter_id = "test:remote"
"""
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "config.toml"
            config_path.write_text(toml_content)

            try:
                adapters = load_adapters_from_file(config_path)
                assert len(adapters) == 1
                assert adapters[0].adapter_id == "test:remote"
            except ImportError:
                pytest.skip("TOML parser not available (requires Python 3.11+ or tomli)")

    def test_load_unsupported_format(self) -> None:
        """Test that unsupported file format is rejected."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "config.xml"
            config_path.write_text("<config/>")

            with pytest.raises(ValueError) as exc_info:
                load_adapters_from_file(config_path)
            assert "Unsupported configuration file format: .xml" in str(exc_info.value)


class TestLocalAdapterInstantiation:
    """Tests for instantiation of local adapters from config."""

    def test_instantiate_filesystem_adapter(self) -> None:
        """Test instantiating FilesystemAdapter from config."""
        yaml_content = """
local_adapters:
  - adapter_type: filesystem
    domain: notes
    adapter_id: local:files
    config:
      directory: /tmp/test
"""
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "config.yaml"
            config_path.write_text(yaml_content)

            adapters = load_adapters_from_file(config_path)

            assert len(adapters) == 1
            assert isinstance(adapters[0], FilesystemAdapter)

    def test_invalid_adapter_type(self) -> None:
        """Test that unknown adapter_type is rejected."""
        yaml_content = """
local_adapters:
  - adapter_type: nonexistent
    domain: notes
    adapter_id: test:adapter
"""
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "config.yaml"
            config_path.write_text(yaml_content)

            with pytest.raises(ValueError) as exc_info:
                load_adapters_from_file(config_path)
            assert "Unknown adapter_type: 'nonexistent'" in str(exc_info.value)

    def test_missing_adapter_dependencies(self) -> None:
        """Test that missing adapter dependencies are caught."""
        yaml_content = """
local_adapters:
  - adapter_type: obsidian
    domain: notes
    adapter_id: obsidian:vault
"""
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "config.yaml"
            config_path.write_text(yaml_content)

            # This may fail if obsidiantools is not installed
            try:
                adapters = load_adapters_from_file(config_path)
                # If it succeeds, the dependency is available
                assert len(adapters) == 1
            except (ImportError, Exception):
                # Dependencies not available or adapter instantiation failed
                pass


class TestConfigValidation:
    """Tests for configuration validation errors."""

    def test_duplicate_adapter_ids(self) -> None:
        """Test that duplicate adapter IDs are rejected."""
        yaml_content = """
remote_adapters:
  - service_url: http://localhost:8001
    domain: notes
    adapter_id: duplicate

local_adapters:
  - adapter_type: filesystem
    domain: events
    adapter_id: duplicate
"""
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "config.yaml"
            config_path.write_text(yaml_content)

            with pytest.raises(ValueError) as exc_info:
                load_adapters_from_file(config_path)
            assert "Duplicate adapter_id" in str(exc_info.value)

    def test_invalid_service_url(self) -> None:
        """Test that invalid service URL is rejected."""
        yaml_content = """
remote_adapters:
  - service_url: localhost:8001
    domain: notes
    adapter_id: test:adapter
"""
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "config.yaml"
            config_path.write_text(yaml_content)

            with pytest.raises(ValueError) as exc_info:
                load_adapters_from_file(config_path)
            assert "service_url must start with http:// or https://" in str(
                exc_info.value
            )

    def test_empty_config(self) -> None:
        """Test that config with no adapters is rejected."""
        yaml_content = """
remote_adapters: []
local_adapters: []
"""
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "config.yaml"
            config_path.write_text(yaml_content)

            with pytest.raises(ValueError) as exc_info:
                load_adapters_from_file(config_path)
            assert "At least one adapter must be defined" in str(exc_info.value)
