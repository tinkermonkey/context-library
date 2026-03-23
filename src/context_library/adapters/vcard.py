"""VCardAdapter for ingesting contacts from vCard (.vcf) files.

This adapter reads .vcf files from a configurable directory, parses vCard entries
per RFC 6350, and normalizes each contact into NormalizedContent with PeopleMetadata.

vCard Format (RFC 6350):
- FN: Full name (display name)
- N: Structured name (given, family)
- EMAIL: Email address(es)
- TEL: Phone number(s)
- ORG: Organization
- TITLE: Job title
- NOTE: Notes/description
- UID: Unique identifier (optional, used for stable source_id)

This adapter uses the vobject library for RFC 6350-compliant parsing.
"""

import hashlib
import logging
from pathlib import Path
from typing import Iterator

from context_library.adapters.base import BaseAdapter
from context_library.storage.models import (
    Domain,
    PollStrategy,
    PeopleMetadata,
    NormalizedContent,
    StructuralHints,
)

logger = logging.getLogger(__name__)

# Try to import optional dependency
HAS_VOBJECT = False
try:
    import vobject
    HAS_VOBJECT = True
except ImportError:
    pass


class VCardAdapter(BaseAdapter):
    """Adapter that ingests contacts from vCard (.vcf) files in a directory.

    This adapter reads .vcf files from a configured directory, parses vCard entries
    per RFC 6350 using the vobject library, and normalizes each contact to
    NormalizedContent with PeopleMetadata for indexing.

    Usage: Initialize with vcf_directory pointing to a directory containing .vcf files.
    The adapter will iterate through all .vcf files, parse vCard components, and yield
    normalized contact data.

    Raises:
        ImportError: If vobject is not installed
    """

    def __init__(self, vcf_directory: str, account_id: str = "default") -> None:
        """Initialize VCardAdapter.

        Args:
            vcf_directory: Path to directory containing .vcf files
            account_id: Account identifier for adapter_id generation (default: "default")

        Raises:
            ImportError: If vobject is not installed
        """
        if not HAS_VOBJECT:
            raise ImportError(
                "vobject is required for VCardAdapter. "
                "Install with: pip install context-library[vcard]"
            )

        self._vcf_directory = Path(vcf_directory)
        self._account_id = account_id

    @property
    def adapter_id(self) -> str:
        """Return a deterministic adapter ID based on account_id.

        Returns:
            f"vcard:{account_id}"
        """
        return f"vcard:{self._account_id}"

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

    def fetch(self, source_ref: str) -> Iterator[NormalizedContent]:
        """Fetch and normalize contacts from vCard files.

        Iterates through all .vcf files in the vcf_directory (sorted by name),
        parses vCard entries, and yields NormalizedContent for each contact.

        Args:
            source_ref: Source-specific reference (unused for vCard adapter)

        Yields:
            NormalizedContent for each contact found in .vcf files

        Raises:
            FileNotFoundError: If vcf_directory does not exist
            ValueError: If vCard parsing or field extraction fails
            KeyError: If required vCard fields are missing
            TypeError: If vCard field types are unexpected
        """
        # Ensure directory exists and is accessible
        if not self._vcf_directory.exists():
            raise FileNotFoundError(f"vCard directory does not exist: {self._vcf_directory}")

        # Process .vcf files in sorted order for deterministic results
        vcf_files = sorted(self._vcf_directory.glob("*.vcf"))

        for vcf_file in vcf_files:
            with open(vcf_file, "r", encoding="utf-8", errors="replace") as f:
                content = f.read()

            # Parse vCard components from file
            # vobject.readComponents returns an iterator of vCard component objects
            for vcard in vobject.readComponents(content):
                # Extract contact metadata and build normalized content
                # Errors propagate to caller for visibility
                metadata = self._extract_people_metadata(vcard)

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

                # Derive stable contact_id
                contact_id = self._derive_contact_id(vcard)

                # Yield normalized content
                yield NormalizedContent(
                    markdown=markdown,
                    source_id=contact_id,
                    structural_hints=hints,
                    normalizer_version=self.normalizer_version,
                )

    def _extract_people_metadata(self, vcard) -> PeopleMetadata:
        """Extract PeopleMetadata from a vCard component.

        Parses vCard fields per RFC 6350:
        - FN: Display name (required)
        - N: Structured name (given, family)
        - EMAIL: Email address(es)
        - TEL: Phone number(s)
        - ORG: Organization
        - TITLE: Job title
        - NOTE: Notes/description

        Args:
            vcard: vobject component representing a vCard

        Returns:
            PeopleMetadata object with extracted fields

        Raises:
            ValueError: If required fields are missing or have invalid values
            TypeError: If fields have unexpected types
        """
        # Extract required display name
        if not hasattr(vcard, "fn"):
            raise ValueError("vCard missing required FN (full name) field")

        display_name = vcard.fn.value
        if not isinstance(display_name, str) or not display_name.strip():
            raise ValueError(f"vCard FN must be non-empty string, got: {display_name!r}")

        # Derive contact_id (used later but needed for logging)
        contact_id = self._derive_contact_id(vcard)

        # Extract optional structured name (N field)
        given_name = None
        family_name = None
        if hasattr(vcard, "n"):
            n_value = vcard.n.value
            # N value has attributes: family, given, additional, prefix, suffix
            given_name = n_value.given if hasattr(n_value, "given") else None
            family_name = n_value.family if hasattr(n_value, "family") else None

            # Normalize empty strings to None
            if given_name == "":
                given_name = None
            if family_name == "":
                family_name = None

        # Extract email addresses (can be multiple)
        emails_raw = vcard.contents.get("email", [])
        emails = tuple(e.value for e in emails_raw if isinstance(e.value, str))

        # Extract phone numbers (can be multiple)
        phones_raw = vcard.contents.get("tel", [])
        phones = tuple(t.value for t in phones_raw if isinstance(t.value, str))

        # Extract optional organization
        organization = None
        if hasattr(vcard, "org"):
            org_value = vcard.org.value
            # ORG can be a list or string depending on vobject version
            if isinstance(org_value, (list, tuple)) and org_value:
                organization = org_value[0] if org_value[0] else None
            elif isinstance(org_value, str) and org_value:
                organization = org_value
            if organization == "":
                organization = None

        # Extract optional job title
        job_title = None
        if hasattr(vcard, "title"):
            job_title = vcard.title.value
            if job_title == "":
                job_title = None

        # Extract optional notes
        notes = None
        if hasattr(vcard, "note"):
            notes = vcard.note.value
            if notes == "":
                notes = None

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
            source_type="vcard",
        )

    def _derive_contact_id(self, vcard) -> str:
        """Derive a stable contact identifier from vCard.

        Uses UID if present, otherwise generates deterministic hash from
        FN + first EMAIL for stable re-ingestion identity.

        Args:
            vcard: vobject component representing a vCard

        Returns:
            Stable contact identifier (UUID or SHA-256 hash)

        Raises:
            ValueError: If FN field is missing (needed for fallback)
        """
        # Prefer UID if present
        if hasattr(vcard, "uid"):
            uid_value = vcard.uid.value
            if isinstance(uid_value, str):
                return uid_value
            return str(uid_value)

        # Fallback: deterministic hash of FN + first EMAIL
        if not hasattr(vcard, "fn"):
            raise ValueError("vCard missing FN field for identity derivation")

        fn = vcard.fn.value
        emails = vcard.contents.get("email", [])
        first_email = emails[0].value if emails else ""

        raw = f"{fn}:{first_email}"
        return hashlib.sha256(raw.encode()).hexdigest()

    def _build_contact_markdown(self, metadata: PeopleMetadata) -> str:
        """Build markdown representation of a contact.

        Generates human-readable prose markdown from contact metadata,
        following the same pattern as AppleContactsAdapter.

        Args:
            metadata: Extracted PeopleMetadata

        Returns:
            Markdown string representation
        """
        parts = []

        # Build professional title/organization summary
        if metadata.organization and metadata.job_title:
            parts.append(f"{metadata.display_name} is a {metadata.job_title} at {metadata.organization}.")
        elif metadata.organization:
            parts.append(f"{metadata.display_name} works at {metadata.organization}.")
        elif metadata.job_title:
            parts.append(f"{metadata.display_name} is a {metadata.job_title}.")
        else:
            parts.append(f"{metadata.display_name}.")

        # Add email addresses if present
        if metadata.emails:
            parts.append(f"Email addresses: {', '.join(metadata.emails)}.")

        # Add phone numbers if present
        if metadata.phones:
            parts.append(f"Phone numbers: {', '.join(metadata.phones)}.")

        # Add notes if present
        if metadata.notes:
            parts.append(f"Notes: {metadata.notes}")

        return "\n".join(parts)
