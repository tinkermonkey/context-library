"""RemoteAdapter for consuming content from remote adapter services via HTTP.

This adapter translates BaseAdapter.fetch() calls into HTTP POST requests to a remote
adapter service, deserializing responses into NormalizedContent objects.

Expected Remote Service API Contract:
====================================

The remote service should expose the following HTTP endpoint:

  POST /fetch
    Content-Type: application/json
    Authorization: Bearer <api_key>  (if api_key is set)

    Request body: { "source_ref": "<string>" }

    Response: JSON object with structure:
    {
      "normalized_contents": [
        {
          "markdown": "<string>",
          "source_id": "<string>",
          "structural_hints": {
            "has_headings": <bool>,
            "has_lists": <bool>,
            "has_tables": <bool>,
            "natural_boundaries": [<int>, ...],
            "file_path": "<string | null>",
            "modified_at": "<ISO 8601 | null>",
            "file_size_bytes": <int | null>,
            "extra_metadata": <dict | null>
          },
          "normalizer_version": "<string>"
        }
      ]
    }

This adapter:
- Sends POST requests to the remote service's /fetch endpoint
- Deserializes response into NormalizedContent objects via Pydantic validation
- Supports bearer token authentication if api_key is provided
- Propagates HTTP errors (4xx, 5xx) as exceptions
- Raises on malformed responses (missing/invalid normalized_contents)
"""

import logging
from typing import Iterator

from context_library.adapters.base import BaseAdapter
from context_library.storage.models import Domain, NormalizedContent

logger = logging.getLogger(__name__)

# Try to import optional dependencies
HAS_HTTPX = False

try:
    import httpx

    HAS_HTTPX = True
except ImportError:
    pass


class RemoteAdapter(BaseAdapter):
    """Adapter that consumes content from a remote adapter service via HTTP.

    This adapter sends HTTP POST requests to a remote service that implements
    the adapter protocol, receiving NormalizedContent objects in the response.
    It acts as a bridge between the Linux backend and Mac-side adapter services.
    """

    def __init__(
        self,
        service_url: str,
        domain: Domain,
        adapter_id: str,
        normalizer_version: str = "1.0.0",
        api_key: str | None = None,
        timeout: float = 30.0,
    ) -> None:
        """Initialize RemoteAdapter.

        Args:
            service_url: Base URL of the remote adapter service (e.g., http://localhost:8000)
            domain: Domain that this adapter serves
            adapter_id: Deterministic identifier for this adapter instance
            normalizer_version: Version of the normalizer implementation (default: "1.0.0")
            api_key: Optional bearer token for API authentication. Must not be an empty string.
            timeout: HTTP request timeout in seconds (default: 30.0)

        Raises:
            ImportError: If httpx is not installed.
            ValueError: If api_key is an empty string.
        """
        if not HAS_HTTPX:
            raise ImportError(
                "httpx is required for RemoteAdapter. "
                "Install with: pip install context-library[remote-adapter]"
            )

        if api_key is not None and api_key == "":
            raise ValueError("api_key must not be an empty string")

        self._service_url = service_url.rstrip("/")
        self._domain = domain
        self._adapter_id = adapter_id
        self._normalizer_version = normalizer_version
        self._api_key = api_key
        self._client = httpx.Client(timeout=timeout)

    @property
    def adapter_id(self) -> str:
        """Return the adapter ID provided at construction."""
        return self._adapter_id

    @property
    def domain(self) -> Domain:
        """Return the domain this adapter serves."""
        return self._domain

    @property
    def normalizer_version(self) -> str:
        """Return the normalizer version."""
        return self._normalizer_version

    def __enter__(self):
        """Context manager entry: return self for use in with statement."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit: clean up httpx.Client session."""
        self._client.close()
        return False

    def __del__(self) -> None:
        """Clean up httpx.Client session when adapter is destroyed (safety net)."""
        if hasattr(self, "_client"):
            self._client.close()

    def fetch(self, source_ref: str) -> Iterator[NormalizedContent]:
        """Fetch and normalize content from the remote adapter service.

        Sends a POST request to the remote service's /fetch endpoint with the
        source_ref in the request body. Deserializes the response into
        NormalizedContent objects via Pydantic validation.

        Args:
            source_ref: Source-specific reference to fetch from remote service

        Yields:
            NormalizedContent for each item in response["normalized_contents"]

        Raises:
            httpx.HTTPError: If the HTTP request fails (4xx, 5xx status codes)
            ValueError: If response is malformed (missing normalized_contents key)
            KeyError: If response is missing normalized_contents key
            TypeError: If normalized_contents is not a list
            pydantic.ValidationError: If any response item fails NormalizedContent validation
        """
        # Build headers with bearer token if api_key is set
        headers = {}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"

        # Send POST request to remote service
        response = self._client.post(
            f"{self._service_url}/fetch",
            json={"source_ref": source_ref},
            headers=headers,
        )

        # Propagate HTTP errors (4xx, 5xx)
        response.raise_for_status()

        # Parse JSON response
        data = response.json()

        # Validate normalized_contents is present
        if "normalized_contents" not in data:
            raise KeyError(
                f"Response missing 'normalized_contents' key. Got keys: {list(data.keys())}"
            )

        normalized_contents = data["normalized_contents"]

        # Validate normalized_contents is a list
        if not isinstance(normalized_contents, list):
            raise TypeError(
                f"'normalized_contents' must be a list, got {type(normalized_contents).__name__}"
            )

        # Deserialize and yield each NormalizedContent
        for item in normalized_contents:
            yield NormalizedContent.model_validate(item)
