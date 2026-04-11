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
import time
from typing import Iterator
from urllib.parse import urlparse

from pydantic import ValidationError

from context_library.adapters.base import BaseAdapter, ResetResult
from context_library.storage.models import Domain, NormalizedContent

logger = logging.getLogger(__name__)

# Try to import optional dependencies
HAS_HTTPX = False
_IMPORT_ERROR: str | None = None

try:
    import httpx

    HAS_HTTPX = True
except ImportError as e:
    _IMPORT_ERROR = str(e)


def _post_reset_to_helper(
    client: "httpx.Client",
    base_url: str,
    collector_name: str,
    api_key: str | None = None,
) -> ResetResult:
    """Call the helper's reset endpoint and deserialize the response.

    This helper is shared by RemoteAdapter and helper-backed adapters
    (ObsidianHelperAdapter, YouTubeWatchHistoryAdapter) to avoid code duplication
    when calling the POST /collectors/{name}/reset endpoint.

    Args:
        client: httpx.Client to use for the request.
        base_url: Base URL of the helper service (e.g., "http://localhost:7123").
        collector_name: Name of the collector (e.g., "obsidian", "youtube").
        api_key: Optional bearer token for authentication.

    Returns:
        ResetResult with ok, cleared, and errors fields from the helper.

    Raises:
        httpx.HTTPStatusError: If the HTTP request fails with 4xx/5xx status.
        httpx.RequestError: If the request fails (connection, timeout, etc.).
        ValueError: If the response body cannot be parsed as JSON.
        ValidationError: If the response is missing required fields or has invalid types.
    """
    headers = {}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    try:
        response = client.post(
            f"{base_url}/collectors/{collector_name}/reset",
            headers=headers,
        )

        # Propagate HTTP errors (4xx, 5xx)
        response.raise_for_status()

        # Parse JSON response
        try:
            data = response.json()
        except ValueError as e:
            logger.error(
                f"Failed to parse JSON response from helper reset endpoint: {e} "
                f"(collector_name={collector_name}, base_url={base_url})"
            )
            raise

        # Deserialize into ResetResult via Pydantic validation
        try:
            return ResetResult.model_validate(data)
        except ValidationError as e:
            logger.error(
                f"Failed to validate helper reset response: {e} "
                f"(collector_name={collector_name}, base_url={base_url})"
            )
            raise

    except httpx.HTTPStatusError as e:
        logger.error(
            f"HTTP error from helper reset endpoint: {e.response.status_code} {e.response.text} "
            f"(collector_name={collector_name}, base_url={base_url})"
        )
        raise
    except httpx.RequestError as e:
        logger.error(
            f"Request error connecting to helper reset endpoint: {e} "
            f"(collector_name={collector_name}, base_url={base_url})"
        )
        raise


class RemoteAdapter(BaseAdapter):
    """Adapter that consumes content from a remote adapter service via HTTP.

    This adapter sends HTTP POST requests to a remote service that implements
    the adapter protocol, receiving NormalizedContent objects in the response.
    It acts as a bridge between the Linux backend and Mac-side adapter services.
    """

    def __init_subclass__(cls, **kwargs):
        """Validate that subclasses define _collector_name.

        This check runs when a subclass is defined, catching missing implementations
        early rather than at runtime.
        """
        super().__init_subclass__(**kwargs)
        # Check that the subclass overrides _collector_name
        if "_collector_name" not in cls.__dict__:
            # Allow RemoteAdapter itself to not have _collector_name, but subclasses must define it
            if cls.__name__ != "RemoteAdapter":
                raise TypeError(
                    f"{cls.__name__} must define _collector_name property. "
                    f"This should match the collector name in the context-helpers registry."
                )

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
            ValueError: If api_key is an empty string or if service_url format is invalid.
        """
        if not HAS_HTTPX:
            msg = (
                "httpx is required for RemoteAdapter. "
                "Install with: pip install context-library[remote-adapter]"
            )
            if _IMPORT_ERROR:
                msg += f"\n\nDiagnostics: Failed to import httpx due to: {_IMPORT_ERROR}"
            raise ImportError(msg)

        if api_key is not None and api_key == "":
            raise ValueError("api_key must not be an empty string")

        # Validate service_url format
        if not service_url:
            raise ValueError("service_url must not be empty")

        parsed = urlparse(service_url)
        if not parsed.scheme:
            raise ValueError(
                f"service_url must include a scheme (e.g., 'http://localhost:8000', "
                f"'https://example.com'). Got: {service_url}"
            )
        if parsed.scheme not in ("http", "https"):
            raise ValueError(
                f"service_url must use http or https scheme, got: {parsed.scheme}. "
                f"Full URL: {service_url}"
            )
        if not parsed.netloc:
            raise ValueError(
                f"service_url must include a host (e.g., 'http://localhost:8000', "
                f"'https://example.com'). Got: {service_url}"
            )

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

    @property
    def _collector_name(self) -> str:
        """Return the name of the collector on the helper service.

        This is used to construct the reset endpoint URL:
        POST {service_url}/collectors/{_collector_name}/reset

        Subclasses must override this property and return a collector name
        that matches the helper service's collector registry. The __init_subclass__
        hook enforces this at subclass definition time.
        """
        raise NotImplementedError(
            f"{self.__class__.__name__} must define _collector_name property. "
            f"This should match the collector name in the context-helpers registry."
        )

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

    def fetch(self, source_ref: str, extra_body: dict | None = None) -> Iterator[NormalizedContent]:
        """Fetch and normalize content from the remote adapter service.

        Sends a POST request to the remote service's /fetch endpoint with the
        source_ref in the request body. Deserializes the response into
        NormalizedContent objects via Pydantic validation.

        Implements exponential backoff retry for transient failures (502, 503, 504,
        connection errors, and timeouts).

        Args:
            source_ref: Source-specific reference to fetch from remote service
            extra_body: Optional additional fields merged into the JSON request body

        Yields:
            NormalizedContent for each item in response["normalized_contents"]

        Raises:
            httpx.HTTPStatusError: If the HTTP request fails with non-transient errors
            httpx.RequestError: If the request fails after max retries (connection, timeout, etc.)
            ValueError: If the response body cannot be parsed as JSON
            KeyError: If response is missing normalized_contents key
            TypeError: If normalized_contents is not a list
            pydantic.ValidationError: If any response item fails NormalizedContent validation
        """
        # Retry configuration for transient failures
        max_retries = 3
        base_delay = 1.0  # seconds
        max_delay = 32.0  # seconds

        # Build headers with bearer token if api_key is set
        headers = {}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"

        # Retry loop for transient failures
        for attempt in range(max_retries + 1):
            try:
                # Build request body, merging any extra params from subclasses
                body: dict = {"source_ref": source_ref}
                if extra_body:
                    body.update(extra_body)

                # Send POST request to remote service
                response = self._client.post(
                    f"{self._service_url}/fetch",
                    json=body,
                    headers=headers,
                )

                # Check for transient errors (502, 503, 504) and retry
                if response.status_code in (502, 503, 504):
                    if attempt < max_retries:
                        delay = min(base_delay * (2 ** attempt), max_delay)
                        logger.warning(
                            f"Transient error {response.status_code} from remote service, "
                            f"retrying in {delay}s (attempt {attempt + 1}/{max_retries})"
                        )
                        time.sleep(delay)
                        continue
                    # On final attempt, raise the error
                    response.raise_for_status()

                # Propagate other HTTP errors (4xx, 5xx)
                response.raise_for_status()

                # Parse JSON response
                try:
                    data = response.json()
                except ValueError as e:
                    logger.error(f"Failed to parse JSON response from remote service: {e}")
                    raise

                # Validate normalized_contents is present
                if "normalized_contents" not in data:
                    logger.error(
                        f"Response missing 'normalized_contents' key. Got keys: {list(data.keys())}"
                    )
                    raise KeyError(
                        f"Response missing 'normalized_contents' key. Got keys: {list(data.keys())}"
                    )

                # Log optional pagination metadata (informational for pull-flow clients)
                if data.get("has_more"):
                    logger.debug(
                        "RemoteAdapter: has_more=True, next_cursor=%s",
                        data.get("next_cursor"),
                    )

                normalized_contents = data["normalized_contents"]

                # Validate normalized_contents is a list
                if not isinstance(normalized_contents, list):
                    logger.error(
                        f"'normalized_contents' must be a list, got {type(normalized_contents).__name__}"
                    )
                    raise TypeError(
                        f"'normalized_contents' must be a list, got {type(normalized_contents).__name__}"
                    )

                # Validate and collect all items before yielding
                # This ensures callers receive either all valid items or an exception,
                # preventing partial results if validation fails mid-stream
                validated_items = []
                for idx, item in enumerate(normalized_contents):
                    try:
                        validated_items.append(NormalizedContent.model_validate(item))
                    except ValidationError as e:
                        logger.error(
                            f"Failed to validate NormalizedContent at index {idx}: {e}"
                        )
                        raise

                # All items validated successfully; now yield them to the caller
                for item in validated_items:
                    yield item

                # Success - exit retry loop
                return

            except httpx.HTTPStatusError as e:
                logger.error(
                    f"HTTP error from remote service: {e.response.status_code} {e.response.text}"
                )
                raise
            except httpx.RequestError as e:
                # Retry on connection-level transient failures (connection errors, timeouts, DNS failures)
                if attempt < max_retries:
                    delay = min(base_delay * (2 ** attempt), max_delay)
                    logger.warning(
                        f"Request error connecting to remote service: {e}, "
                        f"retrying in {delay}s (attempt {attempt + 1}/{max_retries})"
                    )
                    time.sleep(delay)
                    continue
                # On final attempt, log and re-raise
                logger.error(f"Request error connecting to remote service at {self._service_url}: {e}")
                raise

    def reset(self) -> ResetResult:
        """Reset the helper service's delivery state for this collector.

        Sends a POST request to the helper service's reset endpoint and
        deserializes the response into a ResetResult.

        Returns:
            ResetResult with ok, cleared, and errors fields from the helper.

        Raises:
            httpx.HTTPStatusError: If the HTTP request fails with 4xx/5xx status.
            httpx.RequestError: If the request fails (connection, timeout, etc.).
            ValueError: If the response body cannot be parsed as JSON.
            ValidationError: If the response is missing required fields or has invalid types.
        """
        return _post_reset_to_helper(
            client=self._client,
            base_url=self._service_url,
            collector_name=self._collector_name,
            api_key=self._api_key,
        )
