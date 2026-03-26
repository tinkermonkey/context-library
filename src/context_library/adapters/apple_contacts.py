"""AppleContactsAdapter for ingesting contacts from a macOS helper service.

This adapter consumes an HTTP REST API served by a macOS helper process that reads
from Apple Contacts and exposes contact data. The helper process binds to 0.0.0.0
and requires a Bearer API token for authentication.

Expected Local Service API Contract:
====================================

The macOS helper service should expose the following HTTP endpoint:

  GET /contacts
    Query parameters:
      - since (optional): ISO 8601 timestamp; return contacts modified after this time

    Response: JSON array of contact objects
    Status: 200 OK
    Content-Type: application/json

    Example response body:
    [
      {
        "id": "<CNContactIdentifier string>",
        "displayName": "<string>",
        "givenName": "<string | null>",
        "familyName": "<string | null>",
        "emails": ["<email>", ...],
        "phones": ["<phone>", ...],
        "organization": "<string | null>",
        "jobTitle": "<string | null>",
        "notes": "<string | null>",
        "modifiedAt": "<ISO 8601>"
      }
    ]

Security:
  The helper binds to 0.0.0.0 for network access from remote servers.
  A Bearer API token is REQUIRED: Authorization: Bearer <api_key>

This adapter:
- Fetches contacts from the local macOS helper API
- Maps contact fields to PeopleMetadata
- Yields NormalizedContent with PeopleMetadata in extra_metadata
- Supports both initial ingestion and incremental updates via 'since' parameter
"""

import logging
from typing import Iterator

from context_library.adapters.base import BaseAdapter
from context_library.domains.people import PeopleDomain
from context_library.storage.models import (
    Domain,
    PollStrategy,
    PeopleMetadata,
    NormalizedContent,
    StructuralHints,
)

logger = logging.getLogger(__name__)

# Try to import optional dependencies
HAS_HTTPX = False

try:
    import httpx

    HAS_HTTPX = True
except ImportError:
    pass


class AppleContactsAdapter(BaseAdapter):
    """Adapter that ingests contacts from a macOS Apple Contacts helper service.

    This adapter communicates with an HTTP service on the Mac that reads from
    Apple Contacts and exposes contact data via REST API. The helper binds to
    0.0.0.0 and requires a Bearer API token for authentication.

    Usage: Start the macOS helper service, then instantiate this adapter with
    the helper's base URL and API key. The adapter will fetch contacts and
    normalize them to PeopleMetadata for indexing.
    """

    def __init__(
        self,
        api_url: str,
        api_key: str,
        account_id: str = "default",
    ) -> None:
        """Initialize AppleContactsAdapter.

        Args:
            api_url: Base URL of the macOS helper API (e.g., "http://192.168.1.50:7123")
            api_key: Required bearer token for API authentication
            account_id: Account identifier for adapter_id generation (default: "default")

        Raises:
            ImportError: If httpx is not installed.
            ValueError: If api_key is empty.
        """
        if not HAS_HTTPX:
            raise ImportError(
                "httpx is required for AppleContactsAdapter. "
                "Install with: pip install context-library[apple-contacts]"
            )
        if not api_key:
            raise ValueError("api_key is required for AppleContactsAdapter")

        self._api_url = api_url.rstrip("/")
        self._api_key = api_key
        self._account_id = account_id
        self._client = httpx.Client(timeout=30.0)

    @property
    def adapter_id(self) -> str:
        """Return a deterministic adapter ID based on account_id.

        Returns:
            f"apple_contacts:{account_id}"
        """
        return f"apple_contacts:{self._account_id}"

    @property
    def domain(self) -> Domain:
        """Return the domain this adapter serves."""
        return Domain.PEOPLE

    @property
    def poll_strategy(self) -> PollStrategy:
        """Return the polling strategy for this adapter."""
        return PollStrategy.PULL

    @property
    def normalizer_version(self) -> str:
        """Return the normalizer version."""
        return "1.0.0"

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
            try:
                self._client.close()
            except Exception:
                # Silently ignore exceptions during cleanup (e.g., from httpx internals during interpreter shutdown)
                pass

    def fetch(self, source_ref: str) -> Iterator[NormalizedContent]:
        """Fetch and normalize contacts from the macOS helper API.

        The source_ref can optionally contain a last_fetched_at timestamp in ISO 8601
        format. If provided, only contacts modified after that timestamp are fetched.
        Errors in contact processing (schema mismatches, missing fields) are NOT caught —
        they propagate to caller for visibility. This prevents silent skipping when
        the API format changes.

        Args:
            source_ref: ISO 8601 timestamp for incremental ingestion, or empty string for initial

        Yields:
            NormalizedContent for each contact

        Raises:
            httpx.HTTPError: If the API request fails
            ValueError: If the helper API returns unexpected response schema or a contact
                has missing/malformed fields
            KeyError: If a contact is missing required fields
            TypeError: If a contact field has unexpected type
        """
        # Determine incremental fetch by presence of timestamp
        since = source_ref if source_ref else None

        # Fetch contacts from the local API (errors propagate)
        contacts = self._fetch_contacts(since)

        # Convert each contact to NormalizedContent
        # Process without catching errors to ensure visibility of API schema changes
        for contact in contacts:
            # Extract contact metadata - errors propagate
            metadata = self._extract_people_metadata(contact)

            # Build structural hints with metadata
            hints = StructuralHints(
                has_headings=False,
                has_lists=False,
                has_tables=False,
                natural_boundaries=(),
                extra_metadata=metadata.model_dump(),
            )

            # Build markdown representation of contact
            markdown = self._build_contact_markdown(metadata)

            # Yield normalized content
            yield NormalizedContent(
                markdown=markdown,
                source_id=contact["id"],
                structural_hints=hints,
                normalizer_version=self.normalizer_version,
            )

    def _fetch_contacts(self, since: str | None) -> list[dict]:
        """Fetch contact list from the local macOS helper API.

        Args:
            since: Optional ISO 8601 timestamp to fetch only contacts modified after this time

        Returns:
            List of contact dictionaries

        Raises:
            httpx.HTTPError: If the API request fails
            ValueError: If the API returns unexpected response schema
        """
        # Build query parameters
        params = {}
        if since:
            params["since"] = since

        # Build headers
        headers = {"Authorization": f"Bearer {self._api_key}"}

        # Make the API request
        response = self._client.get(
            f"{self._api_url}/contacts",
            params=params,
            headers=headers,
        )
        response.raise_for_status()

        # Parse response
        contacts = response.json()

        # Validate that response is a list
        if not isinstance(contacts, list):
            raise ValueError(
                f"macOS helper API 'contacts' response must be a list, got {type(contacts).__name__}"
            )

        return contacts

    def _extract_people_metadata(self, contact: dict) -> PeopleMetadata:
        """Extract PeopleMetadata from contact response.

        Args:
            contact: Contact dictionary from macOS helper API

        Returns:
            PeopleMetadata object with extracted fields

        Raises:
            KeyError: If required fields are missing
            TypeError: If fields have unexpected types
            ValueError: If fields fail validation
        """
        # Extract required fields
        if "id" not in contact:
            raise KeyError("Contact missing required 'id' field")
        contact_id = contact["id"]

        if "displayName" not in contact:
            raise KeyError("Contact missing required 'displayName' field")
        display_name = contact["displayName"]

        if not isinstance(display_name, str):
            raise TypeError(f"'displayName' field must be str, got {type(display_name).__name__}")
        if not display_name:
            raise ValueError("Contact displayName must be non-empty")

        # Extract optional fields
        given_name = contact.get("givenName")
        if given_name is not None and not isinstance(given_name, str):
            raise TypeError(f"'givenName' field must be str or null, got {type(given_name).__name__}")

        family_name = contact.get("familyName")
        if family_name is not None and not isinstance(family_name, str):
            raise TypeError(f"'familyName' field must be str or null, got {type(family_name).__name__}")

        organization = contact.get("organization")
        if organization is not None and not isinstance(organization, str):
            raise TypeError(f"'organization' field must be str or null, got {type(organization).__name__}")

        job_title = contact.get("jobTitle")
        if job_title is not None and not isinstance(job_title, str):
            raise TypeError(f"'jobTitle' field must be str or null, got {type(job_title).__name__}")

        notes = contact.get("notes")
        if notes is not None and not isinstance(notes, str):
            raise TypeError(f"'notes' field must be str or null, got {type(notes).__name__}")

        # Extract email addresses
        emails_raw = contact.get("emails", [])
        if not isinstance(emails_raw, list):
            raise TypeError(f"'emails' field must be list, got {type(emails_raw).__name__}")
        # Validate each email is a string
        for i, email in enumerate(emails_raw):
            if not isinstance(email, str):
                raise TypeError(f"'emails[{i}]' must be str, got {type(email).__name__}")
        emails = tuple(emails_raw)

        # Extract phone numbers
        phones_raw = contact.get("phones", [])
        if not isinstance(phones_raw, list):
            raise TypeError(f"'phones' field must be list, got {type(phones_raw).__name__}")
        # Validate each phone is a string
        for i, phone in enumerate(phones_raw):
            if not isinstance(phone, str):
                raise TypeError(f"'phones[{i}]' must be str, got {type(phone).__name__}")
        phones = tuple(phones_raw)

        # Build PeopleMetadata
        return PeopleMetadata(
            contact_id=contact_id,
            display_name=display_name,
            given_name=given_name,
            family_name=family_name,
            emails=emails,
            phones=phones,
            organization=organization,
            job_title=job_title,
            notes=notes,
            source_type="apple_contacts",
        )

    def _build_contact_markdown(self, metadata: PeopleMetadata) -> str:
        """Build markdown representation of a contact.

        Args:
            metadata: Extracted PeopleMetadata

        Returns:
            Markdown string representation
        """
        return PeopleDomain.build_contact_markdown(metadata)
