# Adapter HTTP Server Guide

## Overview

The `serve_adapter()` function wraps any `BaseAdapter` instance in a minimal HTTP server, exposing `POST /fetch` and `GET /health` endpoints. This enables macOS adapters to be served remotely without modifying the adapters themselves.

## Function Signature

```python
def serve_adapter(
    adapter: BaseAdapter,
    host: str = "0.0.0.0",
    port: int = 8000,
    api_key: str | None = None,
) -> None:
    """Serve a BaseAdapter instance as an HTTP service."""
```

## Parameters

- **adapter** (`BaseAdapter`): The adapter instance to serve. Works with any `BaseAdapter` subclass without adapter-specific code.
- **host** (str): Bind address. Defaults to `"0.0.0.0"` to accept remote connections. Use `"127.0.0.1"` for localhost-only access.
- **port** (int): Bind port. Defaults to 8000.
- **api_key** (str | None): Optional API key for Bearer token authentication. If set, POST /fetch requests must include `Authorization: Bearer <api_key>` header. GET /health does not require authentication. If None, authentication is disabled.

## HTTP Endpoints

### GET /health

Returns adapter metadata and health status.

**Response (200 OK):**
```json
{
  "status": "ok",
  "adapter_id": "<adapter.adapter_id>",
  "domain": "<adapter.domain.value>"
}
```

**Example:**
```bash
curl http://localhost:8001/health
```

### POST /fetch

Calls `adapter.fetch(source_ref)` and returns normalized content.

**Request:**
```json
{
  "source_ref": "<string>"
}
```

**Response (200 OK):**
```json
{
  "normalized_contents": [
    {
      "markdown": "...",
      "source_id": "...",
      "structural_hints": {
        "has_headings": true,
        "has_lists": false,
        "has_tables": false,
        "natural_boundaries": [10, 20],
        "file_path": null,
        "modified_at": null,
        "file_size_bytes": null,
        "extra_metadata": null
      },
      "normalizer_version": "1.0.0"
    }
  ]
}
```

**Response (400 Bad Request):** Malformed body or missing `source_ref`
```json
{
  "error": "Bad request"
}
```

**Response (401 Unauthorized):** Missing or incorrect Bearer token
```json
{
  "error": "Unauthorized"
}
```

**Response (500 Internal Server Error):** Adapter exception
```json
{
  "error": "<exception message>"
}
```

**Example:**
```bash
curl -X POST http://localhost:8001/fetch \
  -H "Content-Type: application/json" \
  -d '{"source_ref": "My Note"}'
```

## Security

### Bearer Token Authentication

If `api_key` is configured, all requests to `POST /fetch` must include a valid Bearer token:

```bash
curl -X POST http://localhost:8001/fetch \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer secret-key-here" \
  -d '{"source_ref": "My Note"}'
```

The `GET /health` endpoint does **not** require authentication.

### Network Interface

By default, `serve_adapter()` binds to `0.0.0.0`, which accepts connections from any network interface. For local development, use:

```python
serve_adapter(adapter, host="127.0.0.1", port=8001)
```

For cross-machine connections (recommended for production):

```python
serve_adapter(adapter, host="0.0.0.0", port=8001, api_key="shared-secret")
```

## Launching Mac-Side Services

### Obsidian Adapter Service

```python
#!/usr/bin/env python3
"""Launch Obsidian adapter as HTTP service."""

from context_library.adapters import ObsidianAdapter
from context_library.adapters.serve import serve_adapter

# Configure your Obsidian vault path
adapter = ObsidianAdapter(vault_path="/Users/me/Documents/Obsidian")

# Start server on 0.0.0.0:8001 with API key protection
serve_adapter(
    adapter,
    host="0.0.0.0",
    port=8001,
    api_key="your-secure-api-key-here"
)
```

Run:
```bash
python obsidian_service.py
```

Test:
```bash
# Health check
curl http://localhost:8001/health

# Fetch content
curl -X POST http://localhost:8001/fetch \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer your-secure-api-key-here" \
  -d '{"source_ref": "Note Title"}'
```

### Apple Reminders Adapter Service

```python
#!/usr/bin/env python3
"""Launch Apple Reminders adapter as HTTP service."""

from context_library.adapters import AppleRemindersAdapter
from context_library.adapters.serve import serve_adapter

# Point to the localhost Apple Reminders helper service (macOS helper)
adapter = AppleRemindersAdapter(
    api_url="http://localhost:7123",
    account_id="default"
)

# Start server on 0.0.0.0:8002 with API key protection
serve_adapter(
    adapter,
    host="0.0.0.0",
    port=8002,
    api_key="your-secure-api-key-here"
)
```

Run:
```bash
python reminders_service.py
```

Test:
```bash
# Health check
curl http://localhost:8002/health

# Fetch reminders
curl -X POST http://localhost:8002/fetch \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer your-secure-api-key-here" \
  -d '{"source_ref": "All"}'
```

### Apple Health Adapter Service

```python
#!/usr/bin/env python3
"""Launch Apple Health adapter as HTTP service."""

from context_library.adapters import AppleHealthAdapter
from context_library.adapters.serve import serve_adapter

# Point to the localhost Apple Health helper service (macOS helper)
adapter = AppleHealthAdapter(
    api_url="http://localhost:7124",
    device_id="default"
)

# Start server on 0.0.0.0:8003 with API key protection
serve_adapter(
    adapter,
    host="0.0.0.0",
    port=8003,
    api_key="your-secure-api-key-here"
)
```

Run:
```bash
python health_service.py
```

Test:
```bash
# Health check
curl http://localhost:8003/health

# Fetch health data
curl -X POST http://localhost:8003/fetch \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer your-secure-api-key-here" \
  -d '{"source_ref": "all"}'
```

## Localhost Helper Services

The existing Apple Reminders and Apple Health adapters use localhost-only helper services:

- **Apple Reminders helper:** `http://127.0.0.1:7123`
- **Apple Health helper:** `http://127.0.0.1:7124`

These helpers are designed for single-machine access on macOS. When serving these adapters cross-machine via `serve_adapter()`, the server-side bind address changes from `127.0.0.1` to `0.0.0.0` (or a specific network interface), while the adapter client code remains unchanged.

Example flow:
```
Linux Client → RemoteAdapter → http://localhost:8002 → Mac Server (serve_adapter)
                                                              ↓
                                                        AppleRemindersAdapter
                                                              ↓
                                                        http://127.0.0.1:7123
                                                      (macOS helper service)
```

## Integration with RemoteAdapter

On the Linux client side, use `RemoteAdapter` to connect to the served adapter:

```python
from context_library.adapters import RemoteAdapter
from context_library.storage.models import Domain

# Create a remote adapter pointing to the Mac service
remote_adapter = RemoteAdapter(
    service_url="http://mac-machine-ip:8001",
    domain=Domain.NOTES,
    adapter_id="obsidian:vault",
    api_key="your-secure-api-key-here"
)

# Fetch content as if it were local
for content in remote_adapter.fetch("My Note"):
    print(content.markdown)
```

## Implementation Details

### Framework

The `serve_adapter()` function uses Python's built-in `http.server` module, which is sufficient for single-machine, low-concurrency use cases. The server:

- Uses `BaseHTTPRequestHandler` for request routing
- Supports graceful shutdown on `KeyboardInterrupt`
- Logs requests using Python's standard `logging` module
- Serializes/deserializes Pydantic models via `model_dump()` and `model_validate()`

### JSON Serialization

NormalizedContent objects are serialized using Pydantic v2:

```python
# Server side (in serve_adapter)
results = list(adapter.fetch(source_ref))
response = {
    "normalized_contents": [item.model_dump() for item in results]
}

# Client side (in RemoteAdapter)
for item in data["normalized_contents"]:
    yield NormalizedContent.model_validate(item)
```

### Error Handling

- **400 Bad Request:** Malformed JSON, missing `source_ref`, non-string `source_ref`
- **401 Unauthorized:** Missing or incorrect Bearer token (when `api_key` configured)
- **404 Not Found:** Unknown endpoint
- **500 Internal Server Error:** Exception from `adapter.fetch()`

## Running in Production

For production use, consider:

1. **Use a reverse proxy** (nginx, Apache) for SSL/TLS encryption
2. **Run as a system service** (systemd, launchd) for automatic startup
3. **Enable logging** to track requests and errors
4. **Use strong API keys** with sufficient entropy
5. **Monitor resource usage** (memory, connections)

Example systemd service file for macOS (launchd):

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.example.obsidian-adapter-service</string>

    <key>ProgramArguments</key>
    <array>
        <string>/usr/local/bin/python3</string>
        <string>/path/to/obsidian_service.py</string>
    </array>

    <key>RunAtLoad</key>
    <true/>

    <key>StandardOutPath</key>
    <string>/var/log/obsidian-adapter.log</string>

    <key>StandardErrorPath</key>
    <string>/var/log/obsidian-adapter-error.log</string>
</dict>
</plist>
```

Save as `com.example.obsidian-adapter-service.plist` and load:

```bash
launchctl load ~/Library/LaunchAgents/com.example.obsidian-adapter-service.plist
```

## Troubleshooting

### Server won't bind to port

- Check if another process is using the port: `lsof -i :8001`
- Try a different port: `serve_adapter(adapter, port=9001)`
- On Unix systems, ports < 1024 require root privileges

### Client can't connect

- Verify the server is running: `curl http://localhost:8001/health`
- Check firewall rules: `sudo ufw allow 8001`
- Verify API key if configured: Include `Authorization: Bearer ...` header

### Requests timing out

- Increase the timeout in the client: `RemoteAdapter(..., timeout=60.0)`
- Check server logs for slow `adapter.fetch()` calls
- Reduce the amount of data returned per request (via `source_ref`)

### Authentication failing

- Verify API key is exact match (including case and spacing)
- Use `curl -v` to see request/response headers
- Ensure header format is exactly `Authorization: Bearer <token>`

## See Also

- `RemoteAdapter` - Client-side adapter for connecting to remote services
- `BaseAdapter` - Abstract base class for all adapters
- `NormalizedContent` - Data model for normalized content
