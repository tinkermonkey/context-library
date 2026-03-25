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
from typing import Any, Iterator, Optional

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
VOBJECT_PARSE_ERROR = None
try:
    import vobject
    from vobject.base import ParseError as VObjectParseError
    HAS_VOBJECT = True
    VOBJECT_PARSE_ERROR = VObjectParseError
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

    def __enter__(self):
        """Context manager entry: return self for use in with statement."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit: clean up resources."""
        return False

    def __del__(self) -> None:
        """Clean up resources when adapter is destroyed (safety net)."""
        pass

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

        Error handling:
        - Per-contact parsing errors (malformed vCard fields, validation errors) are
          caught and logged; the contact is skipped and processing continues.
        - File-level parse errors (e.g., vobject.ParseError on malformed vCard syntax)
          are caught, logged, and the next file is processed.
        - Encoding errors (non-UTF-8 input) are detected and logged; latin-1 fallback
          is attempted with an explicit warning that data may be garbled.

        Known limitation: When two distinct contacts have identical FN and first EMAIL
        (or identical FN with no email), they will generate the same source_id hash.
        This is spec-compliant per FR-5.4 (deterministic hash of FN + first EMAIL),
        but downstream deduplication logic (DocumentStore, Differ) keying on source_id
        may silently overwrite one contact with the other. Upstream systems should
        use explicit UIDs to distinguish logically separate contacts.

        Args:
            source_ref: Source-specific reference (unused for vCard adapter)

        Yields:
            NormalizedContent for each contact found in .vcf files

        Raises:
            FileNotFoundError: If vcf_directory does not exist
        """
        # Ensure directory exists and is accessible
        if not self._vcf_directory.exists():
            raise FileNotFoundError(f"vCard directory does not exist: {self._vcf_directory}")

        # Process .vcf files in sorted order for deterministic results
        vcf_files = sorted(self._vcf_directory.glob("*.vcf"))

        # Track seen source_ids within this fetch() call to detect collisions
        seen_ids: dict[str, tuple[str, Any]] = {}  # Maps source_id -> (display_name, vcf_file Path object)

        for vcf_file in vcf_files:
            # Read file with explicit encoding detection and error handling
            # First try UTF-8, then fallback to latin-1 with warning
            try:
                with open(vcf_file, "r", encoding="utf-8") as f:
                    content = f.read()
            except UnicodeDecodeError as e:
                logger.warning(
                    f"File {vcf_file.name} is not valid UTF-8. "
                    f"Attempting to read as latin-1 (may produce garbled data). "
                    f"Error: {e}"
                )
                try:
                    with open(vcf_file, "r", encoding="latin-1") as f:
                        content = f.read()
                except Exception as fallback_err:
                    logger.error(f"Failed to read {vcf_file.name} with both UTF-8 and latin-1: {fallback_err}")
                    continue

            # Parse vCard components from file with per-contact error isolation
            # vobject.readComponents returns an iterator of vCard component objects
            contact_index = 0
            try:
                for vcard in vobject.readComponents(content):
                    try:
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

                        # Detect collisions: same source_id for different contacts
                        if contact_id in seen_ids:
                            prev_name, prev_file = seen_ids[contact_id]
                            logger.warning(
                                f"Contact ID collision detected: '{metadata.display_name}' (from {vcf_file.name}) "
                                f"and '{prev_name}' (from {prev_file.name}) both hash to {contact_id}. "
                                f"This occurs when contacts have identical FN and first EMAIL. "
                                f"Skipping this contact to prevent data loss; use explicit UIDs to distinguish."
                            )
                            # Skip yielding this contact to prevent overwriting the first contact
                            contact_index += 1
                            continue

                        # Record this contact_id to detect future collisions
                        seen_ids[contact_id] = (metadata.display_name, vcf_file)

                        # Yield normalized content
                        yield NormalizedContent(
                            markdown=markdown,
                            source_id=contact_id,
                            structural_hints=hints,
                            normalizer_version=self.normalizer_version,
                        )
                        contact_index += 1

                    except Exception as contact_err:  # Catch all per-contact errors (ValueError, KeyError, TypeError, AttributeError, ValidationError, etc.)
                        logger.error(
                            f"Error processing contact at index {contact_index} in {vcf_file.name}: {contact_err}. "
                            f"Skipping this contact and continuing with next."
                        )
                        contact_index += 1
                        continue

            except Exception as parse_err:
                # Catch vobject.ParseError (if vobject is available) and other exceptions
                # from vobject.readComponents. Check if it's a vobject ParseError specifically.
                if HAS_VOBJECT and VOBJECT_PARSE_ERROR is not None and isinstance(parse_err, VOBJECT_PARSE_ERROR):
                    logger.error(
                        f"Parse error while reading vCard file {vcf_file.name}: {parse_err}. "
                        f"Processed {contact_index} contacts before error. Continuing with next file."
                    )
                else:
                    # For non-vobject errors, log and continue
                    logger.error(
                        f"Error while reading vCard file {vcf_file.name}: {parse_err}. "
                        f"Processed {contact_index} contacts before error. Continuing with next file."
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
        emails_list = []
        for e in emails_raw:
            if isinstance(e.value, str):
                emails_list.append(e.value)
            else:
                logger.warning(
                    f"Skipping non-string email value in contact '{display_name}': "
                    f"type={type(e.value).__name__}, value={e.value!r}"
                )
        emails = tuple(emails_list)

        # Extract phone numbers (can be multiple)
        phones_raw = vcard.contents.get("tel", [])
        phones_list = []
        for t in phones_raw:
            if isinstance(t.value, str):
                phones_list.append(t.value)
            else:
                logger.warning(
                    f"Skipping non-string phone value in contact '{display_name}': "
                    f"type={type(t.value).__name__}, value={t.value!r}"
                )
        phones = tuple(phones_list)

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
        """Derive a stable contact identifier from vCard per RFC 6350 spec.

        Uses UID if present. For vCards without UID, generates a deterministic
        SHA-256 hash of FN (full name) + first EMAIL address, per spec FR-5.4.
        This approach ensures stable identity that persists across structural
        changes (insertions/deletions) while remaining deterministic.

        The SHA-256 hash of "FN + first EMAIL" is deterministic and independent
        of file location or index, preventing identity instability when contacts
        are reordered. If a contact's name or email changes, entity links should
        be updated by the upstream system. Contacts without email use FN alone
        for hashing.

        Args:
            vcard: vobject component representing a vCard
            vcf_file: Path to the vCard file (unused, kept for backward compatibility)
            contact_index: Index of contact in file (unused, kept for backward compatibility)

        Returns:
            Stable contact identifier (hex-encoded SHA-256 hash or UID)

        Raises:
            ValueError: If vCard has no FN (required field per RFC 6350)
        """
        # Prefer UID if present and non-empty (most stable, from vCard itself)
        if hasattr(vcard, "uid"):
            uid_value = vcard.uid.value
            # Accept only non-empty string UIDs; empty strings fall through to hash fallback
            if isinstance(uid_value, str) and uid_value.strip():
                return uid_value
            # Non-string or empty UID: convert to string and check if non-empty
            uid_str = str(uid_value).strip()
            if uid_str:
                return uid_str
            # Empty UID: fall through to hash-based fallback below

        # Fallback: Generate deterministic SHA-256 hash from FN + first EMAIL
        # per spec requirement FR-5.4. This ensures stable identity across
        # structural changes (insertions/deletions) in source files.
        # Note: FN is guaranteed to be present and valid by _extract_people_metadata
        # (which calls this method), so we can safely access it here.
        fn_value = vcard.fn.value

        # Get first email if available
        emails_raw = vcard.contents.get("email", [])
        first_email = None
        if emails_raw and isinstance(emails_raw[0].value, str):
            first_email = emails_raw[0].value

        # Create deterministic hash from FN + first EMAIL
        # Use FN alone if no email is present
        if first_email:
            hash_input = f"{fn_value}:{first_email}"
        else:
            hash_input = fn_value

        # Generate SHA-256 hash for deterministic, stable identity
        hash_digest = hashlib.sha256(hash_input.encode("utf-8")).hexdigest()
        return hash_digest

    def _build_contact_markdown(self, metadata: PeopleMetadata) -> str:
        """Build markdown representation of a contact.

        Args:
            metadata: Extracted PeopleMetadata

        Returns:
            Markdown string representation
        """
        return PeopleDomain.build_contact_markdown(metadata)
