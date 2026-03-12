# Adapter Configuration Schema

This document specifies the YAML/TOML/JSON configuration format for declaratively configuring adapters in the context library.

## Overview

The configuration layer allows users to declare adapters (both remote and local) in a configuration file instead of instantiating them directly in Python code. This enables:

- **Declarative configuration**: Define adapters in configuration files alongside application settings
- **Runtime instantiation**: Adapters are instantiated from the configuration at application startup
- **Type validation**: Pydantic models validate all configuration parameters
- **Multiple file formats**: Support for YAML, TOML, and JSON

## Configuration File Format

### YAML Example

```yaml
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
    adapter_id: local:files
    config:
      root_path: /home/user/documents
```

### JSON Example

```json
{
  "remote_adapters": [
    {
      "service_url": "http://mac-server:8001",
      "domain": "notes",
      "adapter_id": "obsidian:vault",
      "api_key": "shared-secret",
      "normalizer_version": "1.0.0",
      "timeout": 30.0
    }
  ],
  "local_adapters": []
}
```

### TOML Example

```toml
[[remote_adapters]]
service_url = "http://mac-server:8001"
domain = "notes"
adapter_id = "obsidian:vault"
api_key = "shared-secret"
normalizer_version = "1.0.0"
timeout = 30.0

[[local_adapters]]
adapter_type = "filesystem"
domain = "notes"
adapter_id = "local:files"

[local_adapters.config]
root_path = "/home/user/documents"
```

## Root Level Fields

### `remote_adapters` (optional)

List of remote adapter configurations. Each entry configures an adapter that communicates with a remote service via HTTP.

**Type**: Array of [RemoteAdapterConfig](#remoteadapterconfig)
**Default**: `[]`
**Minimum valid length**: 0, but at least one of `remote_adapters` or `local_adapters` must be non-empty

### `local_adapters` (optional)

List of local adapter configurations. Each entry configures an adapter instantiated directly in the context library.

**Type**: Array of [LocalAdapterConfig](#localadapterconfig)
**Default**: `[]`
**Minimum valid length**: 0, but at least one of `remote_adapters` or `local_adapters` must be non-empty

## RemoteAdapterConfig

Configuration for instantiating a `RemoteAdapter` that communicates with a remote adapter service via HTTP.

### Fields

#### `service_url` (required)

Base URL of the remote adapter service.

**Type**: String
**Constraints**: Must start with `http://` or `https://`
**Examples**:
- `http://localhost:8001`
- `https://mac-server:8001`
- `http://adapter-service.example.com:8000`

#### `domain` (required)

Domain category that this adapter serves. Indicates the type of content provided.

**Type**: Enum string
**Valid values**: `notes`, `messages`, `events`, `tasks`
**Description**:
- `notes`: Document and note content
- `messages`: Email and messaging content
- `events`: Calendar and event content
- `tasks`: Task lists and TODO items

#### `adapter_id` (required)

Unique identifier for this adapter instance. Must be unique across all adapters in the configuration.

**Type**: String
**Constraints**:
- Non-empty
- Unique within configuration file
- Recommended format: `namespace:name` (e.g., `obsidian:vault`, `mail:primary`)

#### `api_key` (optional)

Bearer token for authentication with the remote service. If provided, it's sent as an HTTP Authorization header with all requests.

**Type**: String or null
**Default**: `null`
**Constraints**: If provided, must not be an empty string (use `null` to omit)

#### `normalizer_version` (optional)

Version identifier of the normalization algorithm used by the remote service. Used for provenance tracking and ensuring consistent content normalization across adapter versions.

**Type**: String
**Default**: `"1.0.0"`
**Constraints**: Non-empty string

#### `timeout` (optional)

HTTP request timeout in seconds for communication with the remote service.

**Type**: Float
**Default**: `30.0`
**Constraints**: Must be positive (> 0)
**Examples**: `10.0`, `30.0`, `60.0`

## LocalAdapterConfig

Configuration for instantiating a local adapter (e.g., `FilesystemAdapter`, `ObsidianAdapter`).

### Fields

#### `adapter_type` (required)

Type of adapter to instantiate. Determines which adapter class is loaded.

**Type**: String
**Valid values**:
- `filesystem` → `FilesystemAdapter`
- `obsidian` → `ObsidianAdapter`
- `obsidian_tasks` → `ObsidianTasksAdapter`
- `email` → `EmailAdapter`
- `caldav` → `CalDAVAdapter`
- `apple_reminders` → `AppleRemindersAdapter`
- `apple_health` → `AppleHealthAdapter`

#### `domain` (required)

Domain category that this adapter serves.

**Type**: Enum string
**Valid values**: `notes`, `messages`, `events`, `tasks`

#### `adapter_id` (required)

Unique identifier for this adapter instance. Must be unique across all adapters in the configuration.

**Type**: String
**Constraints**:
- Non-empty
- Unique within configuration file
- Recommended format: `namespace:name` (e.g., `local:documents`, `obsidian:vault`)

#### `config` (optional)

Adapter-specific configuration parameters. This dictionary is passed directly to the adapter constructor.

**Type**: Object (dict)
**Default**: `null`
**Description**: Parameter names and values depend on the specific adapter type.

**Example for FilesystemAdapter**:
```yaml
config:
  root_path: /home/user/documents
  extensions:
    - .md
    - .txt
```

**Example for ObsidianAdapter**:
```yaml
config:
  vault_path: /home/user/vault
  include_frontmatter: true
```

## Validation Rules

The configuration is validated at load time. All violations result in clear error messages.

### Schema Validation

- **Extra fields forbidden**: Configuration objects cannot contain unrecognized fields
- **Type checking**: All fields are type-checked according to their schema
- **Enum validation**: Domain values must match valid Domain enum values

### Semantic Validation

- **Unique adapter IDs**: All `adapter_id` values must be unique across both `remote_adapters` and `local_adapters`
- **At least one adapter**: Configuration must define at least one adapter
- **Valid URLs**: Remote adapter `service_url` values must start with `http://` or `https://`
- **Non-empty strings**: String fields (adapter_id, adapter_type, normalizer_version) cannot be empty
- **Positive timeout**: Timeout values must be greater than zero

### Instantiation Validation

Beyond schema validation, adapters are instantiated and may raise errors during construction:

- **Missing dependencies**: Attempting to load an adapter whose dependencies are not installed (e.g., `obsidian` without `obsidiantools`)
- **Invalid credentials**: Remote adapters may validate API keys or connection parameters
- **Constructor errors**: Adapter-specific validation (e.g., invalid filesystem paths)

## Loading Configuration

### Python API

```python
from context_library.config import load_adapters_from_file

# Load from YAML
adapters = load_adapters_from_file("config/adapters.yaml")

# Load from JSON
adapters = load_adapters_from_file("config/adapters.json")

# Load from TOML
adapters = load_adapters_from_file("config/adapters.toml")

# Process adapters
for adapter in adapters:
    print(f"Loaded: {adapter.adapter_id} ({adapter.domain})")
```

### Error Handling

```python
from context_library.config import load_adapters_from_file

try:
    adapters = load_adapters_from_file("adapters.yaml")
except FileNotFoundError as e:
    print(f"Configuration file not found: {e}")
except ValueError as e:
    print(f"Configuration validation error: {e}")
except ImportError as e:
    print(f"Required dependency missing: {e}")
except Exception as e:
    print(f"Adapter instantiation failed: {e}")
```

## Best Practices

### Naming Conventions

Use a `namespace:name` format for `adapter_id` values to organize adapters:

- `obsidian:vault` - Obsidian vault on Mac server
- `obsidian:tasks` - Obsidian tasks adapter on Mac server
- `mail:primary` - Primary email account
- `mail:archive` - Archived email account
- `local:documents` - Local filesystem documents
- `local:calendar` - Local filesystem calendar files

### Credential Management

Never commit API keys to version control. Use environment variables or secrets management:

```yaml
remote_adapters:
  - service_url: http://mac-server:8001
    domain: notes
    adapter_id: obsidian:vault
    # Read from environment: ${API_KEY_OBSIDIAN}
    # Or load from secrets file
```

### Configuration Organization

For complex setups, organize adapters by domain:

```yaml
# Remote adapters - accessed via HTTP
remote_adapters:
  - service_url: http://mac-server:8001
    domain: notes
    adapter_id: remote:notes
  - service_url: http://mac-server:8002
    domain: messages
    adapter_id: remote:messages

# Local adapters - direct instantiation
local_adapters:
  - adapter_type: filesystem
    domain: events
    adapter_id: local:calendar
  - adapter_type: filesystem
    domain: tasks
    adapter_id: local:tasks
```

## File Format Considerations

### YAML (Recommended)

- **Pros**: Human-readable, minimal syntax, supports comments
- **Pros**: Standard for Python applications
- **Cons**: Requires PyYAML dependency (usually included in most projects)
- **Usage**: Best for configuration files that humans will edit

### JSON

- **Pros**: No external dependencies (part of Python stdlib)
- **Pros**: Language-agnostic
- **Cons**: No comment support, more verbose
- **Usage**: Best for programmatically generated configurations

### TOML

- **Pros**: Human-readable, structured, supports comments
- **Pros**: Increasingly used for Python configuration
- **Cons**: Requires tomllib (Python 3.11+) or tomli package
- **Usage**: Best when familiar with TOML syntax

## Troubleshooting

### "Configuration file not found"

- Verify the file path exists
- Check for typos in the filename
- Ensure the file is readable

### "Configuration validation failed"

- Check that all required fields are present
- Verify field types match the schema
- Look for duplicate adapter_ids
- Ensure at least one adapter is defined

### "Unsupported configuration file format"

- Use `.yaml`, `.yml`, `.json`, or `.toml` extension
- Check that the file extension is lowercase

### "Unknown adapter_type"

- Verify the adapter_type value is spelled correctly
- Check supported adapter types list above
- Ensure the required dependencies are installed

### "Failed to parse YAML/JSON/TOML"

- Validate syntax using online validators
- Check for missing quotes or colons
- Ensure proper indentation (YAML)

### "Failed to import adapter"

- Install missing dependencies (e.g., `pip install obsidiantools`)
- Verify the adapter type is supported
- Check that the library version is compatible
