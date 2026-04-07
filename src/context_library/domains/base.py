"""Abstract base class defining the BaseDomain interface."""

import re
from abc import ABC, abstractmethod

from context_library.storage.cross_refs import detect_cross_references
from context_library.storage.models import Chunk, NormalizedContent


class BaseDomain(ABC):
    """Abstract base class defining the domain chunking contract.

    All domain implementations (MESSAGES, NOTES, EVENTS, TASKS, HEALTH, DOCUMENTS, PEOPLE, LOCATION)
    must inherit from this class and implement the chunk() method with domain-specific chunking strategies.

    Provides shared utility methods for token counting and text splitting that respect
    hard_limit token boundaries. Subclasses must call super().__init__(hard_limit) to
    validate and set self.hard_limit.
    """

    hard_limit: int

    def __init__(self, hard_limit: int = 1024) -> None:
        """Initialize the BaseDomain with hard_limit validation.

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

    @abstractmethod
    def chunk(self, content: NormalizedContent) -> list[Chunk]:
        """Split normalized content into semantically coherent chunks.

        Args:
            content: The normalized content to chunk

        Returns:
            A list of Chunk instances with sequential chunk_index values
        """
        pass

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

    def _apply_cross_references(self, chunks: list[Chunk]) -> list[Chunk]:
        """Apply cross-reference detection to chunks using Pydantic's model_copy.

        Detects cross-references between chunks and reconstructs chunks with
        populated cross_refs fields. Uses model_copy for safe, idiomatic updates.

        Args:
            chunks: List of chunks to process

        Returns:
            List of chunks with cross_refs fields populated via heuristic detection
        """
        result = []
        for chunk in chunks:
            cross_refs = detect_cross_references(chunk, chunks)
            if cross_refs:
                # Use Pydantic's model_copy for safe, idiomatic mutation of frozen model
                chunk_with_refs = chunk.model_copy(update={"cross_refs": cross_refs})
                result.append(chunk_with_refs)
            else:
                result.append(chunk)
        return result
