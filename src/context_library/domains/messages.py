"""MessagesDomain: chunking and metadata for email, chat, and forum content."""

import re

from pydantic import ValidationError

from context_library.domains.base import BaseDomain
from context_library.storage.cross_refs import detect_cross_references
from context_library.storage.models import (
    Chunk,
    ChunkType,
    MessageMetadata,
    NormalizedContent,
    compute_chunk_hash,
)


def _strip_quoted_content(text: str) -> str:
    """Strip quoted reply content from text.

    Removes lines starting with '>' (email reply markers) and attribution lines
    like "On <date>, <sender> wrote:".

    Args:
        text: The text to clean

    Returns:
        The text with quoted content and attribution lines removed
    """
    lines = text.splitlines()
    result = []

    for line in lines:
        # Skip lines starting with '>' (quoted material)
        stripped = line.strip()
        if stripped.startswith(">"):
            continue
        # Only strip lines matching the pattern "On ... wrote:" (attribution lines)
        if re.match(r'^On .+ wrote:$', stripped):
            continue
        result.append(line)

    return "\n".join(result).strip()


class MessagesDomain(BaseDomain):
    """Domain-specific chunker for email and messaging content.

    Splits message content into semantically coherent chunks with email-specific
    handling: quoted reply stripping, sender/subject context headers, and token-based
    splitting for long messages.
    """

    def __init__(self, hard_limit: int = 1024) -> None:
        """Initialize the MessagesDomain chunker.

        Args:
            hard_limit: Maximum token limit before forced splitting (default 1024)

        Raises:
            ValueError: If hard_limit is not a positive integer
        """
        super().__init__(hard_limit)

    def chunk(self, content: NormalizedContent) -> list[Chunk]:
        """Split message content into semantically coherent chunks.

        Algorithm:
        1. Extract MessageMetadata from content.structural_hints.extra_metadata
        2. Build context_header as "{subject} — {sender}"
        3. Strip quoted reply content (lines starting with '>')
        4. Split oversized messages at sentence boundaries if exceeding hard_limit
        5. Compute chunk_hash from content only (excluding context_header)
        6. Assign sequential chunk_index values
        7. Set chunk_type to ChunkType.STANDARD
        8. Store domain_metadata from MessageMetadata.model_dump()

        Args:
            content: The normalized message content to chunk

        Returns:
            A list of Chunk instances with sequential chunk_index values
        """
        # Extract MessageMetadata from extra_metadata
        if not content.structural_hints.extra_metadata:
            raise ValueError(
                f"MessagesDomain requires extra_metadata in structural_hints "
                f"for source {content.source_id}"
            )

        meta_dict = content.structural_hints.extra_metadata
        try:
            # Type contract: extra_metadata must be deserializable to MessageMetadata.
            # This is enforced at validation time rather than in the type system
            # because StructuralHints.extra_metadata is domain-agnostic (dict[str, object]).
            # See StructuralHints docstring for design rationale.
            meta = MessageMetadata(**meta_dict)  # type: ignore[arg-type]
        except ValidationError as e:
            raise ValueError(
                f"Invalid MessageMetadata for source {content.source_id}: "
                f"{e.error_count()} validation error(s) — {[err['msg'] for err in e.errors()]}"
            ) from e

        # Build context_header
        subject = meta.subject or "(no subject)"
        context_header = f"{subject} — {meta.sender}"

        # Strip quoted content
        text = _strip_quoted_content(content.markdown)

        # Guard against empty content after stripping (all content was quoted)
        if not text.strip():
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

        # Detect cross-references between chunks
        final_chunks = []
        for chunk in chunks:
            cross_refs = detect_cross_references(chunk, chunks)
            if cross_refs:
                # Reconstruct chunk with cross_refs
                chunk_with_refs = Chunk(
                    chunk_hash=chunk.chunk_hash,
                    content=chunk.content,
                    context_header=chunk.context_header,
                    chunk_index=chunk.chunk_index,
                    chunk_type=chunk.chunk_type,
                    domain_metadata=chunk.domain_metadata,
                    cross_refs=cross_refs,
                )
                final_chunks.append(chunk_with_refs)
            else:
                final_chunks.append(chunk)

        return final_chunks

