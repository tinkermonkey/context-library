"""Computes diffs between normalized content versions to detect real changes."""

import hashlib
import re

from context_library.storage.models import DiffResult


class Differ:
    """Stateless hash-based change detector for document versions.

    Performs content-addressed diffing by:
    1. Computing full-document SHA-256 hashes (with normalization)
    2. Comparing chunk hash sets to identify added/removed/unchanged chunks
    3. Treating whitespace-only changes as no-change
    """

    @staticmethod
    def _normalize(text: str) -> str:
        """Normalize whitespace in text for consistent hashing.

        Normalization:
        - Collapse runs of spaces/tabs to single space
        - Strip trailing whitespace from each line
        - Strip leading/trailing whitespace from entire text

        Args:
            text: The text to normalize

        Returns:
            Normalized text
        """
        # Collapse runs of spaces and tabs to single space
        text = re.sub(r"[ \t]+", " ", text)
        # Strip trailing whitespace from each line
        text = "\n".join(line.rstrip() for line in text.splitlines())
        # Strip leading/trailing whitespace from entire text
        return text.strip()

    @staticmethod
    def _compute_hash(text: str) -> str:
        """Compute SHA-256 hash of normalized text.

        Args:
            text: The text to hash

        Returns:
            SHA-256 hash as lowercase hex string
        """
        normalized = Differ._normalize(text)
        return hashlib.sha256(normalized.encode("utf-8")).hexdigest()

    def diff(
        self,
        prev_markdown: str | None,
        curr_markdown: str,
        prev_chunk_hashes: set[str] | None,
        curr_chunk_hashes: set[str],
    ) -> DiffResult:
        """Compute diff between two document versions.

        Args:
            prev_markdown: Previous version's markdown (None for first ingest)
            curr_markdown: Current version's markdown
            prev_chunk_hashes: Previous version's chunk hashes (None for first ingest)
            curr_chunk_hashes: Current version's chunk hashes

        Returns:
            DiffResult with change detection and chunk hash set operations
        """
        # First ingest case: no previous version
        if prev_markdown is None:
            curr_hash = self._compute_hash(curr_markdown)
            return DiffResult(
                changed=True,
                added_hashes=curr_chunk_hashes,
                removed_hashes=set(),
                unchanged_hashes=set(),
                prev_hash=None,
                curr_hash=curr_hash,
            )

        # Compute hashes with normalization
        prev_hash = self._compute_hash(prev_markdown)
        curr_hash = self._compute_hash(curr_markdown)

        # No change detected
        if prev_hash == curr_hash:
            return DiffResult(
                changed=False,
                added_hashes=set(),
                removed_hashes=set(),
                unchanged_hashes=curr_chunk_hashes,
                prev_hash=prev_hash,
                curr_hash=curr_hash,
            )

        # Content changed: compute set operations on chunk hashes
        if prev_chunk_hashes is None:
            raise ValueError("prev_chunk_hashes must not be None when prev_markdown is provided")
        added = curr_chunk_hashes - prev_chunk_hashes
        removed = prev_chunk_hashes - curr_chunk_hashes
        unchanged = curr_chunk_hashes & prev_chunk_hashes

        return DiffResult(
            changed=True,
            added_hashes=added,
            removed_hashes=removed,
            unchanged_hashes=unchanged,
            prev_hash=prev_hash,
            curr_hash=curr_hash,
        )
