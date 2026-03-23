"""PeopleDomain: one-contact-per-chunk strategy with natural-language prose rendering."""

from pydantic import ValidationError

from context_library.domains.base import BaseDomain
from context_library.storage.models import (
    Chunk,
    ChunkType,
    NormalizedContent,
    PeopleMetadata,
    compute_chunk_hash,
)


class PeopleDomain(BaseDomain):
    """Domain-specific chunker for contact/people content.

    Splits contact content into semantically coherent chunks with contact-specific
    handling: contact-aware context headers with organization, natural-language prose
    rendering, and token-based splitting for large contact fields.
    """

    def __init__(self, hard_limit: int = 1024) -> None:
        """Initialize the PeopleDomain chunker.

        Args:
            hard_limit: Maximum token limit before forced splitting (default 1024)

        Raises:
            ValueError: If hard_limit is not a positive integer
        """
        super().__init__(hard_limit)

    @staticmethod
    def build_contact_markdown(metadata: PeopleMetadata) -> str:
        """Build markdown representation of a contact.

        Generates human-readable prose markdown from contact metadata.
        This is the canonical formatter for all people domain adapters.

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

    def chunk(self, content: NormalizedContent) -> list[Chunk]:
        """Split contact content into semantically coherent chunks.

        Algorithm:
        1. Extract PeopleMetadata from content.structural_hints.extra_metadata
        2. Build context_header as "Contact: {display_name} — {organization}"
           or "Contact: {display_name}" if organization is None
        3. Split oversized contact descriptions at sentence boundaries if exceeding hard_limit
        4. Compute chunk_hash from content only (excluding context_header)
        5. Assign sequential chunk_index values
        6. Set chunk_type to ChunkType.STANDARD
        7. Store domain_metadata from PeopleMetadata.model_dump()

        Args:
            content: The normalized contact content to chunk

        Returns:
            A list of Chunk instances with sequential chunk_index values

        Raises:
            ValueError: If extra_metadata is missing or contains invalid PeopleMetadata
        """
        # Extract PeopleMetadata from extra_metadata
        if not content.structural_hints.extra_metadata:
            raise ValueError(
                f"PeopleDomain requires extra_metadata in structural_hints "
                f"for source {content.source_id}"
            )

        meta_dict = content.structural_hints.extra_metadata
        try:
            # Type contract: extra_metadata must be deserializable to PeopleMetadata.
            # This is enforced at validation time rather than in the type system
            # because StructuralHints.extra_metadata is domain-agnostic (dict[str, object]).
            # See StructuralHints docstring for design rationale.
            meta = PeopleMetadata(**meta_dict)  # type: ignore[arg-type]
        except ValidationError as e:
            raise ValueError(
                f"Invalid PeopleMetadata for source {content.source_id}: "
                f"{e.error_count()} validation error(s) — {[err['msg'] for err in e.errors()]}"
            ) from e

        # Build context_header
        if meta.organization:
            context_header = f"Contact: {meta.display_name} — {meta.organization}"
        else:
            context_header = f"Contact: {meta.display_name}"

        # Get the markdown text as the body
        text = content.markdown.strip()

        # Per spec: return empty list if no description content
        if not text:
            return []

        # Split if over hard_limit
        segments = self._split_if_needed(text)

        # Build Chunk objects with sequential indices
        chunks = []
        for idx, segment in enumerate(segments):
            chunk_hash = compute_chunk_hash(segment)
            chunk = Chunk(
                chunk_hash=chunk_hash,
                content=segment,
                context_header=context_header,
                chunk_index=idx,
                chunk_type=ChunkType.STANDARD,
                domain_metadata=meta.model_dump(),
            )
            chunks.append(chunk)

        # Apply cross-reference detection to all chunks
        return self._apply_cross_references(chunks)
