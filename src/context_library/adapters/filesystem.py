"""FilesystemAdapter for discovering and normalizing files from a directory.

Handles markdown files directly and converts other formats (PDF, DOCX, XLSX,
PPTX, HTML, CSV, JSON, XML, EPUB, ZIP, etc.) to markdown using MarkItDown
with Pandoc as a fallback.

Image and audio file support:
- MarkItDown can process images and audio files, but requires optional heavy
  dependencies (vision APIs, speech-to-text services). Without these, images
  and audio files are skipped.
- Pandoc does not support binary media formats, so they cannot be recovered
  via fallback conversion.
- Use the extensions parameter to pre-filter unwanted file types.
"""

import mimetypes
import re
import subprocess
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator, cast

from context_library.adapters.base import BaseAdapter
from context_library.adapters._watching import FileEvent, FileSystemWatcher
from context_library.storage.models import (
    Domain,
    NormalizedContent,
    PollStrategy,
    StructuralHints,
)

logger = logging.getLogger(__name__)

# Try to import MarkItDown (optional dependency)
HAS_MARKITDOWN = False
MarkItDown: type | None = None
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
        Markdown text content if successful, None if conversion failed or
        MarkItDown is not installed.
    """
    if not HAS_MARKITDOWN or MarkItDown is None:
        return None

    try:
        md = MarkItDown(enable_plugins=False)
        result = md.convert(str(file_path))
        return cast(str, result.text_content) or None
    except Exception as e:
        logger.warning("MarkItDown conversion failed for %s: %s", file_path, e, exc_info=True)
        return None


def _convert_with_pandoc(file_path: Path) -> str | None:
    """Convert a file to markdown using Pandoc subprocess.

    Args:
        file_path: Path to the file to convert

    Returns:
        Markdown text content if successful, None if Pandoc is not installed
        or conversion failed.
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
        logger.warning(
            "Pandoc conversion failed for %s (exit %d): %s",
            file_path,
            result.returncode,
            result.stderr,
        )
        return None
    except FileNotFoundError:
        logger.debug("Pandoc not found; skipping Pandoc fallback for %s", file_path)
        return None
    except subprocess.TimeoutExpired:
        logger.warning("Pandoc timed out converting %s", file_path)
        return None


def _detect_structure(text: str) -> tuple[bool, bool, bool]:
    """Return (has_headings, has_lists, has_tables) for a markdown string."""
    has_headings = bool(re.search(r"^#{1,6}\s", text, re.MULTILINE))
    has_lists = bool(re.search(r"^(?:[\-\*\+]|\d+\.)\s", text, re.MULTILINE))
    has_tables = bool(re.search(r"^\|.+\|$", text, re.MULTILINE))
    return has_headings, has_lists, has_tables


class FilesystemAdapter(BaseAdapter):
    """Adapter that discovers and normalizes files from a directory.

    Recursively walks a directory tree. Markdown files are read directly;
    all other files are converted to markdown using MarkItDown (with Pandoc
    as a fallback). Files that cannot be converted are skipped with a warning.

    Supports both pull-based (periodic directory walking) and push-based
    (filesystem watching via inotify/FSEvents) ingestion strategies.
    """

    def __init__(
        self,
        directory: str | Path,
        poll_strategy: PollStrategy = PollStrategy.PULL,
        extensions: set[str] | None = None,
    ) -> None:
        """Initialize FilesystemAdapter.

        Args:
            directory: Root directory to scan for files.
            poll_strategy: PULL for periodic directory walks, PUSH for
                filesystem-event-driven ingestion.
            extensions: Optional set of file extensions to include
                (e.g. {'.pdf', '.docx', '.md'}). If None, all files are
                processed. Non-markdown files that cannot be converted are
                skipped regardless.
        """
        self._directory = Path(directory)
        self._poll_strategy = poll_strategy
        self._extensions = extensions
        self._watcher: FileSystemWatcher | None = None

        if poll_strategy == PollStrategy.PUSH:
            self._watcher = FileSystemWatcher(
                watch_path=self._directory,
                callback=self._on_file_changed,
                extensions=extensions,
            )

    @property
    def adapter_id(self) -> str:
        return f"filesystem:{self._directory.resolve()}"

    @property
    def domain(self) -> Domain:
        return Domain.DOCUMENTS

    @property
    def normalizer_version(self) -> str:
        return "2.0.0"

    def fetch(self, source_ref: str) -> Iterator[NormalizedContent]:
        """Fetch and normalize files from the directory.

        Markdown files are read directly. All other files are converted to
        markdown via MarkItDown → Pandoc fallback chain. Files where both
        converters fail are skipped.

        Args:
            source_ref: Unused for filesystem adapters (uses self._directory).

        Yields:
            NormalizedContent for each successfully processed file.

        Raises:
            FileNotFoundError: If the configured directory does not exist.
            NotADirectoryError: If the configured path is not a directory.
        """
        if not self._directory.exists():
            raise FileNotFoundError(f"Directory does not exist: {self._directory}")

        if not self._directory.is_dir():
            raise NotADirectoryError(f"Path is not a directory: {self._directory}")

        for file_path in self._directory.rglob("*"):
            if not file_path.is_file():
                continue

            if self._extensions is not None:
                if file_path.suffix.lower() not in self._extensions:
                    continue

            try:
                yield from self._process_file(file_path)
            except PermissionError:
                logger.warning("Permission denied reading file: %s", file_path)
            except FileNotFoundError:
                logger.warning("File was deleted during iteration: %s", file_path)
            except OSError as e:
                logger.warning("Error processing file %s: %s", file_path, e)

    def _process_file(self, file_path: Path) -> Iterator[NormalizedContent]:
        """Convert a single file and yield NormalizedContent, or nothing if it fails."""
        is_markdown = file_path.suffix.lower() == ".md"

        if is_markdown:
            try:
                markdown = file_path.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                logger.warning("Failed to decode file as UTF-8: %s", file_path)
                return
        else:
            markdown = _convert_with_markitdown(file_path)
            if markdown is None:
                markdown = _convert_with_pandoc(file_path)
            if markdown is None:
                logger.warning(
                    "Could not convert %s to markdown (MarkItDown and Pandoc both failed)",
                    file_path,
                )
                return

        stat = file_path.stat()
        modified_at = datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat()
        created_at = datetime.fromtimestamp(stat.st_ctime, tz=timezone.utc).isoformat()
        relative = file_path.relative_to(self._directory)
        source_id = str(relative)
        mime_type, _ = mimetypes.guess_type(str(file_path))
        document_type = mime_type or ("text/markdown" if is_markdown else "application/octet-stream")

        has_headings, has_lists, has_tables = _detect_structure(markdown)

        extra_metadata: dict[str, object] = {
            "document_id": source_id,
            "title": file_path.name,
            "document_type": document_type,
            "source_type": "filesystem",
            "created_at": created_at,
            "modified_at": modified_at,
            "file_size_bytes": stat.st_size,
            "directory_hierarchy": list(relative.parent.parts),
        }

        structural_hints = StructuralHints(
            has_headings=has_headings,
            has_lists=has_lists,
            has_tables=has_tables,
            natural_boundaries=(),
            file_path=str(file_path.resolve()),
            modified_at=modified_at,
            file_size_bytes=stat.st_size,
            extra_metadata=extra_metadata,
        )

        yield NormalizedContent(
            markdown=markdown,
            source_id=source_id,
            structural_hints=structural_hints,
            normalizer_version=self.normalizer_version,
        )

    def _on_file_changed(self, event: FileEvent) -> None:
        """Handle filesystem changes in push mode."""
        logger.warning(
            "File change detected in watched directory: %s (%s)",
            event.path,
            event.event_type,
        )
