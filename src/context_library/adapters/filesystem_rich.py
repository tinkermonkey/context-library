"""RichFilesystemAdapter for converting non-markdown files to markdown.

Converts non-markdown files (PDF, DOCX, XLSX, PPTX, HTML, images, audio) to markdown
using MarkItDown with Pandoc fallback. Yields NormalizedContent with rich structural
metadata including MIME type, file size, timestamps, and directory hierarchy.
"""

import logging
import mimetypes
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator

from context_library.adapters.base import BaseAdapter
from context_library.adapters._watching import (
    FileEvent,
    FileSystemWatcher,
)
from context_library.storage.models import (
    Domain,
    NormalizedContent,
    PollStrategy,
    StructuralHints,
)

logger = logging.getLogger(__name__)

# Try to import MarkItDown
HAS_MARKITDOWN = False
try:
    from markitdown import MarkItDown
    HAS_MARKITDOWN = True
except ImportError:
    pass


def _convert_with_markitdown(file_path: Path) -> str | None:
    """Convert a file to markdown using MarkItDown.

    Args:
        file_path: Path to the file to convert

    Returns:
        Markdown text content if successful, None if conversion failed
    """
    if not HAS_MARKITDOWN:
        return None

    try:
        md = MarkItDown()
        result = md.convert(str(file_path))
        return result.text_content
    except Exception as e:
        logger.debug(f"MarkItDown conversion failed for {file_path}: {e}")
        return None


def _convert_with_pandoc(file_path: Path) -> str | None:
    """Convert a file to markdown using Pandoc subprocess.

    Args:
        file_path: Path to the file to convert

    Returns:
        Markdown text content if successful, None if conversion failed
    """
    try:
        result = subprocess.run(
            ["pandoc", "-t", "markdown", str(file_path)],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode == 0:
            return result.stdout
        return None
    except (FileNotFoundError, subprocess.TimeoutExpired) as e:
        logger.debug(f"Pandoc conversion failed for {file_path}: {e}")
        return None


class RichFilesystemAdapter(BaseAdapter):
    """Adapter that converts non-markdown files to markdown from a directory.

    Recursively walks a directory tree, discovering non-markdown files (PDF, DOCX, XLSX,
    PPTX, HTML, images, audio, etc.) and converting them to markdown using MarkItDown
    with Pandoc fallback. Yields NormalizedContent with rich structural hints including
    MIME type, file size, creation/modification timestamps, and directory hierarchy.

    Supports both pull-based (periodic directory walking) and push-based (filesystem
    watching) ingestion strategies.
    """

    def __init__(
        self,
        directory: Path | str,
        poll_strategy: PollStrategy = PollStrategy.PULL,
        extensions: set[str] | None = None,
    ) -> None:
        """Initialize RichFilesystemAdapter.

        Args:
            directory: Root directory to scan for non-markdown files
            poll_strategy: How to discover changes (PULL for directory walk, PUSH for watcher)
            extensions: Optional set of file extensions to include (e.g., {'.pdf', '.docx'}).
                       If None, all supported non-markdown formats are included.
        """
        self._directory = Path(directory)
        self._poll_strategy = poll_strategy
        self._extensions = extensions
        self._watcher: FileSystemWatcher | None = None

        if poll_strategy == PollStrategy.PUSH:
            # Create watcher for push-based ingestion
            # It will be started by the adapter framework
            self._watcher = FileSystemWatcher(
                watch_path=self._directory,
                callback=self._on_file_changed,
                extensions=extensions,
            )

    @property
    def adapter_id(self) -> str:
        """Return a deterministic adapter ID based on adapter type and directory path.

        Returns:
            f"filesystem_rich:{absolute_path}"
        """
        return f"filesystem_rich:{self._directory.resolve()}"

    @property
    def domain(self) -> Domain:
        """Return the domain this adapter serves."""
        return Domain.NOTES

    @property
    def normalizer_version(self) -> str:
        """Return the normalizer version."""
        return "1.0.0"

    def fetch(self, source_ref: str) -> Iterator[NormalizedContent]:
        """Fetch and convert non-markdown files from the directory.

        Recursively discovers all non-markdown files in the directory tree and yields
        NormalizedContent for each one after conversion to markdown.

        Args:
            source_ref: Unused for filesystem adapter (uses self._directory)

        Yields:
            NormalizedContent for each converted file found

        Raises:
            FileNotFoundError: If the configured directory does not exist
            NotADirectoryError: If the configured path exists but is not a directory
        """
        if not self._directory.exists():
            raise FileNotFoundError(f"Directory does not exist: {self._directory}")

        if not self._directory.is_dir():
            raise NotADirectoryError(f"Path is not a directory: {self._directory}")

        for file_path in self._directory.rglob("*"):
            if not file_path.is_file():
                continue

            # Skip markdown files (handled by FilesystemAdapter)
            if file_path.suffix.lower() == ".md":
                continue

            # Filter by extensions if configured
            if self._extensions is not None:
                if file_path.suffix.lower() not in self._extensions:
                    continue

            try:
                # Try to convert file to markdown
                markdown = _convert_with_markitdown(file_path)
                if markdown is None:
                    # Fall back to Pandoc
                    markdown = _convert_with_pandoc(file_path)

                if markdown is None:
                    # Both converters failed
                    logger.warning(
                        f"Could not convert file to markdown (both MarkItDown and Pandoc failed): {file_path}"
                    )
                    continue

                # Get file stats for structural hints
                stat = file_path.stat()

                # Get MIME type
                mime_type, _ = mimetypes.guess_type(str(file_path))

                # Compute modified_at in ISO 8601 format
                modified_at = datetime.fromtimestamp(
                    stat.st_mtime, tz=timezone.utc
                ).isoformat()

                # Compute creation_at in ISO 8601 format (use ctime which may be creation time)
                created_at = datetime.fromtimestamp(
                    stat.st_ctime, tz=timezone.utc
                ).isoformat()

                # Compute relative path from base directory for source_id
                relative = file_path.relative_to(self._directory)
                source_id = str(relative)

                # Build extra metadata with MIME type, creation timestamp, and directory hierarchy
                extra_metadata = {
                    "mime_type": mime_type,
                    "created_at": created_at,
                    "directory_hierarchy": list(relative.parent.parts),
                }

                # Build structural hints
                # For converted files, we check if the markdown has structure
                has_headings = bool(
                    re.search(r"^#{1,6}\s", markdown, re.MULTILINE)
                )
                has_lists = bool(
                    re.search(r"^(?:[\-\*\+]|\d+\.)\s", markdown, re.MULTILINE)
                )
                has_tables = bool(
                    re.search(r"^\|.+\|$", markdown, re.MULTILINE)
                )

                structural_hints = StructuralHints(
                    has_headings=has_headings,
                    has_lists=has_lists,
                    has_tables=has_tables,
                    natural_boundaries=[],
                    file_path=str(file_path.resolve()),
                    modified_at=modified_at,
                    file_size_bytes=stat.st_size,
                    extra_metadata=extra_metadata,
                )

                # Yield normalized content
                yield NormalizedContent(
                    markdown=markdown,
                    source_id=source_id,
                    structural_hints=structural_hints,
                    normalizer_version=self.normalizer_version,
                )

            except PermissionError:
                logger.warning(f"Permission denied reading file: {file_path}")
                continue
            except FileNotFoundError:
                logger.warning(f"File was deleted during iteration: {file_path}")
                continue
            except OSError as e:
                logger.warning(f"Error processing file {file_path}: {e}")
                continue

    def _on_file_changed(self, event: FileEvent) -> None:
        """Handle filesystem changes in push mode.

        Called by FileSystemWatcher when a file is created, modified, or deleted.

        Args:
            event: FileEvent containing the path and event type

        Note:
            This method is currently a placeholder for future implementation.
            Full push-mode support will require integration with the document store
            framework to trigger re-ingestion on file changes. The watcher is created
            and available via self._watcher for framework-level lifecycle management.
        """
        logger.debug(f"File change detected: {event.path} ({event.event_type})")
