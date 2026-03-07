"""TasksDomain: one-task-per-chunk strategy with lifecycle state tracking."""

from pydantic import ValidationError

from context_library.domains.base import BaseDomain
from context_library.storage.models import (
    Chunk,
    ChunkType,
    NormalizedContent,
    TaskMetadata,
    compute_chunk_hash,
)


class TasksDomain(BaseDomain):
    """Domain-specific chunker for task content.

    Splits task content into semantically coherent chunks with task-specific
    handling: status-aware context headers, lifecycle metadata, and token-based
    splitting for long task descriptions.
    """

    def __init__(self, hard_limit: int = 1024) -> None:
        """Initialize the TasksDomain chunker.

        Args:
            hard_limit: Maximum token limit before forced splitting (default 1024)

        Raises:
            ValueError: If hard_limit is not a positive integer
        """
        if hard_limit <= 0:
            raise ValueError(
                f"hard_limit must be a positive integer, got {hard_limit}"
            )
        self.hard_limit = hard_limit

    def chunk(self, content: NormalizedContent) -> list[Chunk]:
        """Split task content into semantically coherent chunks.

        Algorithm:
        1. Extract TaskMetadata from content.structural_hints.extra_metadata
        2. Build context_header as "{title} [{status}]" with optional due date
        3. Split oversized task descriptions at sentence boundaries if exceeding hard_limit
        4. Compute chunk_hash from content only (excluding context_header)
        5. Assign sequential chunk_index values
        6. Set chunk_type to ChunkType.STANDARD
        7. Store domain_metadata from TaskMetadata.model_dump()

        Args:
            content: The normalized task content to chunk

        Returns:
            A list of Chunk instances with sequential chunk_index values
        """
        # Extract TaskMetadata from extra_metadata
        if not content.structural_hints.extra_metadata:
            raise ValueError(
                f"TasksDomain requires extra_metadata in structural_hints "
                f"for source {content.source_id}"
            )

        meta_dict = content.structural_hints.extra_metadata
        try:
            # Type contract: extra_metadata must be deserializable to TaskMetadata.
            # This is enforced at validation time rather than in the type system
            # because StructuralHints.extra_metadata is domain-agnostic (dict[str, object]).
            # See StructuralHints docstring for design rationale.
            meta = TaskMetadata(**meta_dict)  # type: ignore[arg-type]
        except ValidationError as e:
            raise ValueError(
                f"Invalid TaskMetadata for source {content.source_id}: "
                f"{e.error_count()} validation error(s) — {[err['msg'] for err in e.errors()]}"
            ) from e

        # Build context_header
        if meta.due_date:
            context_header = f"{meta.title} [due: {meta.due_date}] [{meta.status}]"
        else:
            context_header = f"{meta.title} [{meta.status}]"

        # Get the markdown text
        text = content.markdown

        # Guard against empty content
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
        import re

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
