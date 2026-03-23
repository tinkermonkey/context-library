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

import logging
import uuid
from pathlib import Path
from typing import Iterator, Optional

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
            for contact_index, vcard in enumerate(vobject.readComponents(content)):
                # Extract contact metadata and build normalized content
                # Pass file path and index for deterministic UID generation
                metadata = self._extract_people_metadata(vcard, vcf_file, contact_index)

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

                # Use contact_id from metadata (already derived above)
                contact_id = metadata.contact_id

                # Yield normalized content
                yield NormalizedContent(
                    markdown=markdown,
                    source_id=contact_id,
                    structural_hints=hints,
                    normalizer_version=self.normalizer_version,
                )

    def _extract_people_metadata(self, vcard, vcf_file: Optional[Path] = None, contact_index: int = 0) -> PeopleMetadata:
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
            vcf_file: Path to the vCard file (for deterministic UID generation)
            contact_index: Index of contact in file (for deterministic UID generation)

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

        # Derive contact_id for PeopleMetadata
        contact_id = self._derive_contact_id(vcard, vcf_file, contact_index)

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

    def _derive_contact_id(self, vcard, vcf_file: Optional[Path] = None, contact_index: int = 0) -> str:
        """Derive a stable contact identifier from vCard.

        Uses UID if present. For vCards without UID, generates a deterministic
        UUID5 based on file location and contact position, independent of
        mutable contact data (name, email).

        This approach prevents identity instability: if a contact's name or
        email changes, the contact_id remains constant, preserving entity links
        and preventing duplicate person chunks. Additionally, it prevents
        collisions between different contacts that have the same name.

        **Limitation**: Contact index is used as part of the identifier. If a
        contact is deleted or inserted before another contact in the same .vcf
        file, subsequent contacts will shift indices and be assigned new IDs.
        This is an inherent limitation of file-based indexing. Mitigation: ensure
        vCard files include explicit UID fields for stable identity across
        structural changes.

        Args:
            vcard: vobject component representing a vCard
            vcf_file: Path to the vCard file (for deterministic UUID generation)
            contact_index: Index of contact in file (for deterministic UUID generation)

        Returns:
            Stable contact identifier (UUID string)

        Raises:
            ValueError: If vcf_file is None (required for deterministic derivation)
        """
        # Prefer UID if present (most stable, from vCard itself)
        if hasattr(vcard, "uid"):
            uid_value = vcard.uid.value
            if isinstance(uid_value, str):
                return uid_value
            return str(uid_value)

        # Fallback: Generate deterministic UUID from file path + contact index
        # This ensures stable identity across re-ingests without depending on
        # mutable fields like name or email, and avoids collisions between
        # different contacts with the same name.
        if vcf_file is None:
            raise ValueError("vcf_file is required for deterministic identity derivation")

        # Create a deterministic namespace identifier from:
        # 1. Absolute file path (immutable across re-ingests)
        # 2. Contact index in file (immutable once file is written)
        namespace_key = f"file://{vcf_file.resolve()}#{contact_index}"

        # Use UUID5 (deterministic SHA-1 based UUID) with URL namespace
        # This ensures the same file + position always generates the same UUID
        return str(uuid.uuid5(uuid.NAMESPACE_URL, namespace_key))

    def _build_contact_markdown(self, metadata: PeopleMetadata) -> str:
        """Build markdown representation of a contact.

        Args:
            metadata: Extracted PeopleMetadata

        Returns:
            Markdown string representation
        """
        return PeopleDomain.build_contact_markdown(metadata)
