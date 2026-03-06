"""ObsidianAdapter for ingesting Obsidian vaults.

Extracts per-note YAML frontmatter metadata and vault-level wikilink graph data
using obsidiantools. Yields NormalizedContent with rich structural hints including:
- YAML frontmatter properties (tags, aliases, custom fields)
- Wikilink relationships (forward links, backlinks)
- File timestamps (creation, modification) in ISO 8601 format
- Markdown structure detection (headings, lists, tables)

Supports both pull-based (periodic directory walking) and push-based (filesystem
watching) ingestion strategies.

Dependencies:
- obsidiantools: For vault parsing and wikilink graph construction
- python-frontmatter: For YAML frontmatter parsing
- watchdog: For filesystem watching in push mode (optional, only if PollStrategy.PUSH is used)
"""

import logging
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator, Any

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

# Try to import obsidiantools and frontmatter
HAS_OBSIDIANTOOLS = False
HAS_FRONTMATTER = False

try:
    import obsidiantools.api as otools

    HAS_OBSIDIANTOOLS = True
except ImportError:
    pass

try:
    import frontmatter

    HAS_FRONTMATTER = True
except ImportError:
    pass


class ObsidianAdapter(BaseAdapter):
    """Adapter that ingests an Obsidian vault.

    Discovers all .md notes in a vault, extracts per-note YAML frontmatter metadata
    and vault-level wikilink graph data using obsidiantools, and yields NormalizedContent
    with rich structural hints including tags, aliases, frontmatter properties, and
    wikilink edges.

    Supports both pull-based (periodic directory walking) and push-based (filesystem
    watching) ingestion strategies.
    """

    def __init__(
        self,
        vault_path: Path | str,
        poll_strategy: PollStrategy = PollStrategy.PULL,
    ) -> None:
        """Initialize ObsidianAdapter.

        Args:
            vault_path: Path to the Obsidian vault directory
            poll_strategy: How to discover changes (PULL for directory walk, PUSH for watcher)

        Raises:
            ImportError: If obsidiantools or python-frontmatter are not installed
        """
        if not HAS_OBSIDIANTOOLS:
            raise ImportError(
                "obsidiantools is required for ObsidianAdapter. "
                "Install it with: pip install context-library[obsidian]"
            )
        if not HAS_FRONTMATTER:
            raise ImportError(
                "python-frontmatter is required for ObsidianAdapter. "
                "Install it with: pip install context-library[obsidian]"
            )

        self._vault_path = Path(vault_path).resolve()
        self._poll_strategy = poll_strategy
        self._vault = None  # lazy-loaded obsidiantools.Vault
        self._watcher: FileSystemWatcher | None = None

        if poll_strategy == PollStrategy.PUSH:
            # Create watcher for push-based ingestion
            self._watcher = FileSystemWatcher(
                watch_path=self._vault_path,
                callback=self._on_file_changed,
                extensions={".md"},
            )

    @property
    def adapter_id(self) -> str:
        """Return a deterministic adapter ID based on vault path.

        Returns:
            f"obsidian:{absolute_vault_path}"
        """
        return f"obsidian:{self._vault_path}"

    @property
    def domain(self) -> Domain:
        """Return the domain this adapter serves."""
        return Domain.NOTES

    @property
    def normalizer_version(self) -> str:
        """Return the normalizer version."""
        return "1.0.0"

    def _get_vault(self) -> Any:
        """Lazy-load and return the obsidiantools Vault instance.

        Returns:
            Connected Vault instance with wikilink graph built
        """
        if self._vault is None:
            self._vault = otools.Vault(self._vault_path).connect()
        return self._vault

    def _parse_note(self, note_path: Path) -> tuple[str, dict[str, Any]]:
        """Parse note file and extract both markdown body and frontmatter metadata.

        Consolidates file reading into a single frontmatter.load() call to avoid
        double I/O. Handles flexible tag/alias formats:
        - Accepts tags as string or list, normalizes to list
        - Accepts aliases as string or list, normalizes to list
        - Raises exception if file cannot be parsed or read

        Args:
            note_path: Path to the note file

        Returns:
            Tuple of (markdown_body, metadata_dict) where metadata_dict has keys:
            tags (list), aliases (list), frontmatter (dict of all YAML)

        Raises:
            FileNotFoundError: If file does not exist or is inaccessible
            OSError: If file cannot be read (permission, encoding, I/O errors)
            ValueError: If YAML frontmatter is malformed or cannot be parsed
        """
        try:
            post = frontmatter.load(str(note_path))
            fm_data = post.metadata
            markdown = post.content

            # Extract tags and aliases, defaulting to empty lists
            tags = fm_data.get("tags", [])
            if isinstance(tags, str):
                tags = [tags]
            elif not isinstance(tags, list):
                tags = []

            aliases = fm_data.get("aliases", [])
            if isinstance(aliases, str):
                aliases = [aliases]
            elif not isinstance(aliases, list):
                aliases = []

            metadata = {
                "tags": tags,
                "aliases": aliases,
                "frontmatter": fm_data,
            }
            return markdown, metadata
        except (ValueError, KeyError, AttributeError) as e:
            # Frontmatter parsing failed; attempt raw file read as fallback
            try:
                raw_content = note_path.read_text(encoding="utf-8")
                return raw_content, {
                    "tags": [],
                    "aliases": [],
                    "frontmatter": {},
                }
            except (FileNotFoundError, PermissionError, OSError, UnicodeDecodeError) as e2:
                # File cannot be read; raise to caller
                raise OSError(f"Cannot read file {note_path}: {e2}") from e2
        except (FileNotFoundError, PermissionError, OSError, UnicodeDecodeError) as e:
            # File access errors: raise explicitly
            raise OSError(f"Cannot access file {note_path}: {e}") from e
        except Exception as e:
            # Unexpected errors: wrap and raise
            raise ValueError(f"Unexpected error parsing note {note_path}: {e}") from e

    def _get_note_name(self, note_path: Path) -> str:
        """Get the note name (stem) from a note path.

        Args:
            note_path: Path to the note file

        Returns:
            Note name without .md extension
        """
        return note_path.stem

    def _extract_graph_metadata(self, note_name: str, vault: Any) -> dict[str, Any]:
        """Extract wikilink graph metadata for a note.

        Extracts both forward links (notes this note links TO) and backlinks
        (notes that link TO this note) from the vault's wikilink graph. Errors
        in graph extraction are logged with appropriate severity.

        Args:
            note_name: Name of the note (stem without .md)
            vault: Connected Vault instance

        Returns:
            Dictionary with keys: wikilinks (list of forward links), backlinks (list of back-references)
        """
        graph_data: dict[str, Any] = {
            "wikilinks": [],
            "backlinks": [],
        }

        try:
            # Get forward wikilinks (notes this note links TO)
            wikilinks = vault.get_wikilinks(note_name)
            if wikilinks:
                try:
                    graph_data["wikilinks"] = list(wikilinks)
                except (TypeError, ValueError) as e:
                    logger.warning(f"Cannot convert wikilinks to list for {note_name}: {e}")
        except KeyError:
            logger.debug(f"Note '{note_name}' not found in vault graph for wikilinks")
        except Exception as e:
            logger.warning(f"Failed to extract wikilinks for {note_name}: {e}")

        try:
            # Get backlinks (notes that link TO this note)
            backlinks = vault.get_backlinks(note_name)
            if backlinks:
                try:
                    graph_data["backlinks"] = list(backlinks)
                except (TypeError, ValueError) as e:
                    logger.warning(f"Cannot convert backlinks to list for {note_name}: {e}")
        except KeyError:
            logger.debug(f"Note '{note_name}' not found in vault graph for backlinks")
        except Exception as e:
            logger.warning(f"Failed to extract backlinks for {note_name}: {e}")

        return graph_data

    def _extract_timestamps(self, note_path: Path) -> tuple[str, str, int]:
        """Extract creation and modification timestamps and file size from a note.

        Returns file timestamps in ISO 8601 format and file size in bytes.

        Args:
            note_path: Path to the note file

        Returns:
            Tuple of (created_at, modified_at, file_size_bytes) where timestamps are
            in ISO 8601 format (UTC) and file_size_bytes is an integer

        Raises:
            FileNotFoundError: If the file does not exist
            OSError: If stat() fails due to permissions or other OS-level errors
            ValueError: If timestamp values are invalid or cannot be converted

        Note:
            On Linux, st_ctime is the inode metadata change time, not the file creation
            time. True file creation time (st_birthtime) is only available on macOS/Windows
            and some modern Linux filesystems. This is a known platform limitation.
        """
        stat = note_path.stat()
        # st_ctime is platform-dependent: creation time on macOS/Windows,
        # but inode change time on Linux (see docstring note)
        try:
            created_at = datetime.fromtimestamp(
                stat.st_ctime, tz=timezone.utc
            ).isoformat()
            modified_at = datetime.fromtimestamp(
                stat.st_mtime, tz=timezone.utc
            ).isoformat()
        except (ValueError, OverflowError) as e:
            raise ValueError(f"Invalid timestamp value in {note_path}: {e}") from e
        return created_at, modified_at, stat.st_size

    def fetch(self, source_ref: str) -> Iterator[NormalizedContent]:
        """Fetch and normalize notes from the Obsidian vault.

        Recursively discovers all .md files in the vault and yields NormalizedContent
        for each one with YAML frontmatter metadata and wikilink graph data.

        Rebuilds the vault graph on each fetch() call to reflect added/modified notes
        and wikilinks, ensuring wikilink data is always current.

        Args:
            source_ref: Unused for Obsidian adapter (uses self._vault_path)

        Yields:
            NormalizedContent for each note found

        Raises:
            FileNotFoundError: If the vault directory does not exist
            NotADirectoryError: If the vault path exists but is not a directory
        """
        if not self._vault_path.exists():
            raise FileNotFoundError(f"Vault directory does not exist: {self._vault_path}")

        if not self._vault_path.is_dir():
            raise NotADirectoryError(f"Vault path is not a directory: {self._vault_path}")

        # Rebuild vault graph on each fetch to reflect changes
        self._vault = None
        vault = self._get_vault()

        for note_path in self._vault_path.rglob("*.md"):
            if not note_path.is_file():
                continue

            try:
                # Parse note once to extract both markdown and frontmatter metadata
                markdown, fm_metadata = self._parse_note(note_path)
            except (OSError, ValueError) as e:
                logger.warning(f"Skipping unparseable note: {e}")
                continue

            # Skip intentionally empty notes (valid in Obsidian for placeholders)
            if not markdown.strip():
                logger.debug(f"Skipping empty note: {note_path}")
                continue

            try:
                # Get note name for graph lookups
                note_name = self._get_note_name(note_path)

                # Extract graph metadata
                graph_metadata = self._extract_graph_metadata(note_name, vault)

                # Extract timestamps and file size (single stat() call)
                try:
                    created_at, modified_at, file_size = self._extract_timestamps(note_path)
                except FileNotFoundError:
                    logger.warning(f"File disappeared during timestamp extraction: {note_path}")
                    continue
                except (OSError, ValueError) as e:
                    logger.warning(f"Cannot extract metadata from file {note_path}: {e}")
                    continue

                # Compute relative path from vault root for source_id
                source_id = str(note_path.relative_to(self._vault_path))

                # Build extra metadata combining frontmatter, graph, and timestamps
                extra_metadata: dict[str, object] = {
                    "tags": fm_metadata["tags"],
                    "aliases": fm_metadata["aliases"],
                    "frontmatter": fm_metadata["frontmatter"],
                    "wikilinks": graph_metadata["wikilinks"],
                    "backlinks": graph_metadata["backlinks"],
                    "created_at": created_at,
                    "modified_at": modified_at,
                }

                # Compute structural hints from markdown
                # Detect ATX-style headings (# through ######)
                has_headings = bool(
                    re.search(r"^#{1,6}\s", markdown, re.MULTILINE)
                )
                # Detect unordered lists (-, *, +) and ordered lists (1., 2., etc.)
                has_lists = bool(
                    re.search(r"^(?:[\-\*\+]|\d+\.)\s", markdown, re.MULTILINE)
                )
                # Detect pipe-delimited table rows
                has_tables = bool(
                    re.search(r"^\|.+\|$", markdown, re.MULTILINE)
                )

                # Build structural hints
                structural_hints = StructuralHints(
                    has_headings=has_headings,
                    has_lists=has_lists,
                    has_tables=has_tables,
                    natural_boundaries=[],
                    file_path=str(note_path.resolve()),
                    modified_at=modified_at,
                    file_size_bytes=file_size,
                    extra_metadata=extra_metadata,
                )

                # Yield normalized content
                yield NormalizedContent(
                    markdown=markdown,
                    source_id=source_id,
                    structural_hints=structural_hints,
                    normalizer_version=self.normalizer_version,
                )

            except UnicodeDecodeError:
                logger.warning(f"Failed to decode file as UTF-8: {note_path}")
                continue
            except PermissionError:
                logger.warning(f"Permission denied reading file: {note_path}")
                continue
            except FileNotFoundError:
                logger.warning(f"File was deleted during iteration: {note_path}")
                continue
            except OSError as e:
                logger.warning(f"Error processing file {note_path}: {e}")
                continue

    def _on_file_changed(self, event: FileEvent) -> None:
        """Handle filesystem changes in push mode.

        Called by FileSystemWatcher when a file is created, modified, or deleted.
        Invalidates the vault graph cache so that the next fetch() rebuilds the graph
        and reflects the changed note's wikilinks and backlinks.

        Args:
            event: FileEvent containing the path and event type

        Note:
            This method invalidates the vault cache but does not trigger re-ingestion.
            Full push-mode support (triggering selective re-ingestion of a single changed note)
            requires integration with the document store framework. For now, the framework
            should call fetch() after detecting a file change, which will rebuild the vault
            and return current wikilink graph data.
        """
        logger.debug(f"File change detected in vault: {event.path} ({event.event_type})")
        # Invalidate vault cache so next fetch() rebuilds the graph
        self._vault = None
