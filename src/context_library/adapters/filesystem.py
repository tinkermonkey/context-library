"""FilesystemAdapter for discovering and normalizing markdown files."""

import re
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator

from context_library.adapters.base import BaseAdapter
from context_library.storage.models import (
    Domain,
    NormalizedContent,
    StructuralHints,
)

logger = logging.getLogger(__name__)


class FilesystemAdapter(BaseAdapter):
    """Adapter that discovers and normalizes markdown files from a directory.

    Recursively walks a directory tree, yielding NormalizedContent for all .md files.
    """

    def __init__(self, directory: str | Path):
        """Initialize FilesystemAdapter.

        Args:
            directory: Root directory to scan for markdown files
        """
        self._directory = Path(directory)

    @property
    def adapter_id(self) -> str:
        """Return a deterministic adapter ID based on adapter type and directory path.

        Returns:
            f"filesystem:{absolute_path}"
        """
        return f"filesystem:{self._directory.resolve()}"

    @property
    def domain(self) -> Domain:
        """Return the domain this adapter serves."""
        return Domain.NOTES

    @property
    def normalizer_version(self) -> str:
        """Return the normalizer version."""
        return "1.0.0"

    def fetch(self, source_ref: str) -> Iterator[NormalizedContent]:
        """Fetch and normalize markdown files from the directory.

        Recursively discovers all .md files in the directory tree and yields
        NormalizedContent for each one.

        Args:
            source_ref: Unused for filesystem adapter (uses self._directory)

        Yields:
            NormalizedContent for each .md file found

        Raises:
            FileNotFoundError: If the configured directory does not exist
            NotADirectoryError: If the configured path exists but is not a directory
        """
        if not self._directory.exists():
            raise FileNotFoundError(f"Directory does not exist: {self._directory}")

        if not self._directory.is_dir():
            raise NotADirectoryError(f"Path is not a directory: {self._directory}")

        for md_file in self._directory.rglob("*.md"):
            if not md_file.is_file():
                continue

            try:
                # Read file contents
                markdown = md_file.read_text(encoding="utf-8")

                # Get file stats for structural hints
                stat = md_file.stat()

                # Compute structural hints from content
                has_headings = bool(
                    re.search(r"^#{1,6}\s", markdown, re.MULTILINE)
                )
                has_lists = bool(
                    re.search(r"^(?:[\-\*\+]|\d+\.)\s", markdown, re.MULTILINE)
                )
                has_tables = bool(
                    re.search(r"^\|.+\|$", markdown, re.MULTILINE)
                )

                # Compute modified_at in ISO 8601 format
                modified_at = datetime.fromtimestamp(
                    stat.st_mtime, tz=timezone.utc
                ).isoformat()

                # Compute relative path from base directory
                source_id = str(md_file.relative_to(self._directory))

                # Build structural hints
                structural_hints = StructuralHints(
                    has_headings=has_headings,
                    has_lists=has_lists,
                    has_tables=has_tables,
                    natural_boundaries=[],
                    file_path=str(md_file.resolve()),
                    modified_at=modified_at,
                    file_size_bytes=stat.st_size,
                )

                # Yield normalized content
                yield NormalizedContent(
                    markdown=markdown,
                    source_id=source_id,
                    structural_hints=structural_hints,
                    normalizer_version=self.normalizer_version,
                )

            except UnicodeDecodeError:
                logger.warning(f"Failed to decode file as UTF-8: {md_file}")
                continue
            except PermissionError:
                logger.warning(f"Permission denied reading file: {md_file}")
                continue
            except FileNotFoundError:
                logger.warning(f"File was deleted during iteration: {md_file}")
                continue
            except OSError as e:
                logger.warning(f"Error processing file {md_file}: {e}")
                continue
