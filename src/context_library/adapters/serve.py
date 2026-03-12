"""HTTP server wrapper for serving BaseAdapter instances over the network.

This module provides a generic serve_adapter() function that wraps any BaseAdapter
in a minimal HTTP server, exposing POST /fetch and GET /health endpoints. This enables
existing macOS adapters (ObsidianAdapter, AppleRemindersAdapter, AppleHealthAdapter)
to be served remotely without modifying the adapters themselves.

Security Notes:
- The /health endpoint does not require authentication, even when api_key is set,
  as it is intended for health checks and monitoring. It exposes adapter_id and domain.
- All Bearer token comparisons use constant-time comparison (hmac.compare_digest).
- Request body size is limited to prevent memory exhaustion attacks.
- Exception details from adapter.fetch() are returned in the 500 response (adapter
  is internal, not exposed to untrusted clients). Exceptions are also logged.

Example:
    Launch an Obsidian adapter service:

    .. code-block:: python

        from context_library.adapters import ObsidianAdapter
        from context_library.adapters.serve import serve_adapter

        adapter = ObsidianAdapter(vault_path="/Users/me/Documents/Obsidian")
        serve_adapter(adapter, host="0.0.0.0", port=8001, api_key="shared-secret")

    Launch an Apple Reminders service:

    .. code-block:: python

        from context_library.adapters import AppleRemindersAdapter
        from context_library.adapters.serve import serve_adapter

        adapter = AppleRemindersAdapter(
            service_url="http://localhost:7123",
            api_key="reminders-api-key"
        )
        serve_adapter(adapter, host="0.0.0.0", port=8002)

    Launch an Apple Health service:

    .. code-block:: python

        from context_library.adapters import AppleHealthAdapter
        from context_library.adapters.serve import serve_adapter

        adapter = AppleHealthAdapter(
            service_url="http://localhost:7124",
            api_key="health-api-key"
        )
        serve_adapter(adapter, host="0.0.0.0", port=8003)

Note on localhost helpers:
    The existing localhost helpers (AppleRemindersAdapter with localhost:7123 and
    AppleHealthAdapter with localhost:7124) are designed for single-machine access
    to macOS helper services. When serving cross-machine connections via serve_adapter(),
    the bind address must change from 127.0.0.1 to 0.0.0.0 or a specific network interface.
    This is handled transparently by specifying host="0.0.0.0" when calling serve_adapter().
"""

import hmac
import json
import logging
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any

from context_library.adapters.base import BaseAdapter

logger = logging.getLogger(__name__)

# Maximum request body size (10 MB) to prevent memory exhaustion
MAX_BODY_SIZE = 10 * 1024 * 1024


class AdapterHTTPHandler(BaseHTTPRequestHandler):
    """HTTP request handler for adapter endpoints.

    Supports:
    - GET /health: Returns adapter metadata and health status
    - POST /fetch: Calls adapter.fetch(source_ref) and returns NormalizedContent list

    Bearer token authentication is enforced if api_key is configured on the server.
    """

    server: "AdapterHTTPServer"

    def do_GET(self) -> None:
        """Handle GET requests."""
        if self.path == "/health":
            self._handle_health()
        else:
            self._error_response(404, "Not Found")

    def do_POST(self) -> None:
        """Handle POST requests."""
        if self.path == "/fetch":
            self._handle_fetch()
        else:
            self._error_response(404, "Not Found")

    def _handle_health(self) -> None:
        """Handle GET /health endpoint.

        Returns 200 with:
        {
            "status": "ok",
            "adapter_id": "<adapter.adapter_id>",
            "domain": "<adapter.domain.value>"
        }
        """
        if self.server.adapter is None:
            self._error_response(500, "Adapter not configured")
            return

        response = {
            "status": "ok",
            "adapter_id": self.server.adapter.adapter_id,
            "domain": self.server.adapter.domain.value,
        }
        self._json_response(200, response)

    def _handle_fetch(self) -> None:
        """Handle POST /fetch endpoint.

        Request body: {"source_ref": "<string>"}

        Returns:
        - 200: {"normalized_contents": [<NormalizedContent.model_dump()>, ...]}
        - 400: {"error": "Bad request"} - malformed body or missing source_ref
        - 401: {"error": "Unauthorized"} - missing or invalid Bearer token
        - 500: {"error": "<exception message>"} - adapter error
        """
        # Check authentication if api_key is configured
        if self.server.api_key is not None:
            auth_result = self._check_bearer_token()
            if not auth_result:
                self._error_response(401, "Unauthorized")
                return

        # Parse Content-Length header (reject non-integer or out-of-range values)
        try:
            content_length = int(self.headers.get("Content-Length", 0))
        except ValueError:
            self._error_response(400, "Bad request")
            return

        if content_length <= 0 or content_length > MAX_BODY_SIZE:
            self._error_response(400, "Bad request")
            return

        # Read and decode request body
        try:
            body_bytes = self.rfile.read(content_length)
            body_str = body_bytes.decode("utf-8")
            body = json.loads(body_str)
        except (UnicodeDecodeError, json.JSONDecodeError):
            self._error_response(400, "Bad request")
            return

        # Extract and validate source_ref
        source_ref = body.get("source_ref")
        if source_ref is None or not isinstance(source_ref, str):
            self._error_response(400, "Bad request")
            return

        # Call adapter.fetch() and collect results
        if self.server.adapter is None:
            self._error_response(500, "Adapter not configured")
            return

        try:
            results = list(self.server.adapter.fetch(source_ref))
        except Exception as e:
            logger.exception(
                "adapter.fetch() failed for source_ref=%s", source_ref
            )
            self._error_response(500, str(e))
            return

        # Serialize and send response (connection errors propagate naturally)
        response = {
            "normalized_contents": [item.model_dump() for item in results]
        }
        self._json_response(200, response)

    def _check_bearer_token(self) -> bool:
        """Check if Authorization header contains correct Bearer token.

        Uses constant-time comparison (hmac.compare_digest) to prevent timing
        side-channel attacks.

        Returns:
            True if token is valid or no api_key is configured, False otherwise.
        """
        if self.server.api_key is None:
            return True

        auth_header = self.headers.get("Authorization", "")
        expected_prefix = "Bearer "

        if not auth_header.startswith(expected_prefix):
            return False

        token = auth_header[len(expected_prefix) :]
        return hmac.compare_digest(token, self.server.api_key)

    def _json_response(self, status_code: int, data: dict[str, Any]) -> None:
        """Send a JSON response.

        Args:
            status_code: HTTP status code
            data: Dictionary to serialize as JSON
        """
        response_body = json.dumps(data).encode("utf-8")

        self.send_response(status_code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(response_body)))
        self.end_headers()
        self.wfile.write(response_body)

    def _error_response(self, status_code: int, error_msg: str) -> None:
        """Send an error response.

        Args:
            status_code: HTTP status code
            error_msg: Error message to include in response
        """
        response = {"error": error_msg}
        self._json_response(status_code, response)

    def log_message(self, format: str, *args: Any) -> None:
        """Log HTTP requests using the module logger instead of stderr."""
        logger.debug(format, *args)


class AdapterHTTPServer(HTTPServer):
    """Custom HTTPServer that allows setting adapter and api_key for handlers.

    The adapter and api_key are stored as instance attributes on the server object,
    and handlers access them via self.server.adapter and self.server.api_key.
    This avoids thread-safety issues with class-level mutation.
    """

    def __init__(
        self,
        server_address: tuple[str, int],
        adapter: BaseAdapter,
        api_key: str | None = None,
    ) -> None:
        """Initialize the server with adapter and api_key.

        Args:
            server_address: (host, port) tuple
            adapter: The BaseAdapter instance to serve
            api_key: Optional API key for Bearer token authentication
        """
        self.adapter = adapter
        self.api_key = api_key
        super().__init__(server_address, AdapterHTTPHandler)


def serve_adapter(
    adapter: BaseAdapter,
    host: str = "0.0.0.0",
    port: int = 8000,
    api_key: str | None = None,
) -> None:
    """Serve a BaseAdapter instance as an HTTP service.

    Exposes two endpoints:
    - POST /fetch: Call adapter.fetch(source_ref), return NormalizedContent list
    - GET /health: Return adapter metadata and health status

    HTTP contract:

    POST /fetch
    -----------
    Request:
        Content-Type: application/json
        Authorization: Bearer <token>  (required if api_key configured)

        Body: { "source_ref": "<string>" }

    Response 200:
        {
            "normalized_contents": [
                {
                    "markdown": "...",
                    "source_id": "...",
                    "structural_hints": { ... },
                    "normalizer_version": "1.0.0"
                }
            ]
        }

    Response 401: { "error": "Unauthorized" }      (missing/invalid token)
    Response 400: { "error": "Bad request" }        (malformed body)
    Response 500: { "error": "<exception message>" } (adapter error)

    GET /health
    -----------
    Response 200:
        {
            "status": "ok",
            "adapter_id": "<adapter.adapter_id>",
            "domain": "<adapter.domain.value>"
        }

    Args:
        adapter: The BaseAdapter instance to serve. Works with any BaseAdapter
                 subclass without adapter-specific code.
        host: Bind address. Defaults to "0.0.0.0" to accept remote connections.
              Use "127.0.0.1" for localhost-only access.
        port: Bind port. Defaults to 8000.
        api_key: Optional API key for Bearer token authentication. If set, all
                 requests must include Authorization: Bearer <api_key> header.
                 If None, authentication is disabled.

    Example:
        Serve an ObsidianAdapter on 0.0.0.0:8001 with API key protection:

        .. code-block:: python

            from context_library.adapters import ObsidianAdapter
            from context_library.adapters.serve import serve_adapter

            adapter = ObsidianAdapter(vault_path="/Users/me/Documents/Obsidian")
            serve_adapter(adapter, host="0.0.0.0", port=8001, api_key="secret")

    Note:
        This function blocks indefinitely. Run in a background thread or process
        if you need other code to execute concurrently.

        The server uses Python's http.server stdlib module and is suitable for
        single-machine, low-concurrency use cases. For higher concurrency, consider
        wrapping this with async/ASGI infrastructure.
    """
    server = AdapterHTTPServer((host, port), adapter, api_key)
    logger.info(
        "Starting adapter HTTP server on %s:%d for adapter_id=%s, domain=%s",
        host,
        port,
        adapter.adapter_id,
        adapter.domain.value,
    )
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        logger.info("Shutting down adapter HTTP server")
    finally:
        server.server_close()
