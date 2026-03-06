"""MessagesDomain: chunking and metadata for email, chat, and forum content."""

import re
from typing import Any

from context_library.domains.base import BaseDomain
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
        # Also skip attribution lines that end with "wrote:"
        if line.startswith(">"):
            continue
        if line.strip().endswith("wrote:"):
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
        """
        self.hard_limit = hard_limit

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
        meta = MessageMetadata(**meta_dict)  # type: ignore[arg-type]

        # Build context_header
        subject = meta.subject or "(no subject)"
        context_header = f"{subject} — {meta.sender}"

        # Strip quoted content
        text = _strip_quoted_content(content.markdown)

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

        return chunks

    def _token_count(self, text: str) -> int:
        """Count tokens as whitespace-split words.

        Args:
            text: The text to count

        Returns:
            Approximate token count (1 word ≈ 1 token)
        """
        return len(text.split())

    def _split_if_needed(self, text: str) -> list[str]:
        """Split text into segments respecting hard_limit token boundaries.

        Splits at sentence boundaries if text exceeds hard_limit tokens.
        Falls back to word boundaries for oversized sentences.

        Args:
            text: The text to split

        Returns:
            A list of text segments, each under hard_limit tokens
        """
        token_count = self._token_count(text)

        # If under hard limit, return as single segment
        if token_count <= self.hard_limit:
            return [text]

        # Split into sentences at boundaries (. ! ?)
        sentences = re.split(r'(?<=[.!?])\s+', text)
        sentences = [s for s in sentences if s.strip()]

        segments = []
        current_segment = ""

        for sent in sentences:
            if not sent.strip():
                continue

            sent_tokens = self._token_count(sent)

            # If sentence itself exceeds hard_limit, split at word boundaries
            if sent_tokens > self.hard_limit:
                # Flush current segment if it has content
                if current_segment.strip():
                    segments.append(current_segment.strip())
                    current_segment = ""

                # Split sentence at word boundaries
                words = sent.split()
                word_segment = ""
                for word in words:
                    test_segment = (word_segment + " " + word).strip()

                    if self._token_count(test_segment) <= self.hard_limit:
                        word_segment = test_segment
                    else:
                        # Flush word segment and start new
                        if word_segment:
                            segments.append(word_segment)
                        word_segment = word

                # Flush final word segment
                if word_segment:
                    current_segment = word_segment
            else:
                # Sentence fits - try to add to current segment
                test_segment = (current_segment + " " + sent).strip()

                if self._token_count(test_segment) <= self.hard_limit:
                    current_segment = test_segment
                else:
                    # Flush current segment and start new with sentence
                    if current_segment.strip():
                        segments.append(current_segment.strip())
                    current_segment = sent.strip()

        # Flush final segment
        if current_segment.strip():
            segments.append(current_segment.strip())

        return segments if segments else [text]
