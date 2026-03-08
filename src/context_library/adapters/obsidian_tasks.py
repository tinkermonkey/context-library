"""ObsidianTasksAdapter for ingesting task-formatted content from an Obsidian vault.

Extracts task-formatted content from .md files using:
- Obsidian Tasks plugin checkbox syntax: - [ ], - [x], - [/], - [-], etc.
- Kanban plugin format (detected via kanban-plugin: basic YAML frontmatter)

Yields NormalizedContent with TaskMetadata for each discovered task,
including status, due date, priority, and dependencies.

Supports both pull-based (periodic directory walking) and push-based (filesystem
watching) ingestion strategies.

Dependencies:
- python-frontmatter: For YAML frontmatter and kanban-plugin detection
- watchdog or watchfiles: For filesystem watching in push mode (optional)
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

# Try to import frontmatter
HAS_FRONTMATTER = False

try:
    import frontmatter

    HAS_FRONTMATTER = True
except ImportError:
    pass

# Task status mapping from checkbox markers
_STATUS_MAP = {
    " ": "open",
    "x": "completed",
    "/": "in-progress",
    "-": "cancelled",
}

# Priority emoji mapping (1 = highest, 4 = lowest)
_PRIORITY_MAP = {
    "🔺": 1,
    "⏫": 2,
    "🔼": 3,
    "🔽": 4,
}

# Kanban lane name to status mapping
_KANBAN_STATUS_MAP = {
    "done": "completed",
    "complete": "completed",
    "completed": "completed",
    "in progress": "in-progress",
    "doing": "in-progress",
}

# Regex patterns for task and metadata extraction
TASK_PATTERN = re.compile(r"^\s*- \[([^\]]*)\] (.+)$", re.MULTILINE)
DUE_EMOJI = re.compile(r"📅 (\d{4}-\d{2}-\d{2})")
DUE_DATAVIEW = re.compile(r"\[due:: (\d{4}-\d{2}-\d{2})\]")
PRIORITY_EMOJI = re.compile(r"(🔺|⏫|🔼|🔽)")
DEPENDENCY = re.compile(r"⛔ ([a-zA-Z0-9_\-/]+)")
DEPENDENCY_DATAVIEW = re.compile(r"\[depends:: ([^\]]+)\]")


class ObsidianTasksAdapter(BaseAdapter):
    """Adapter that ingests task-formatted content from an Obsidian vault.

    Discovers .md files in a vault, extracts tasks using Obsidian Tasks plugin
    checkbox syntax (- [ ], - [x], - [/], - [-], etc.) or Kanban plugin format
    (detected via kanban-plugin: basic frontmatter), and yields NormalizedContent
    with TaskMetadata.

    Supports both pull-based (periodic directory walking) and push-based (filesystem
    watching) ingestion strategies.
    """

    def __init__(
        self,
        vault_path: Path | str,
        poll_strategy: PollStrategy = PollStrategy.PULL,
    ) -> None:
        """Initialize ObsidianTasksAdapter.

        Args:
            vault_path: Path to the Obsidian vault directory
            poll_strategy: How to discover changes (PULL for directory walk, PUSH for watcher)

        Raises:
            ImportError: If python-frontmatter is not installed
        """
        if not HAS_FRONTMATTER:
            raise ImportError(
                "python-frontmatter is required for ObsidianTasksAdapter. "
                "Install it with: pip install context-library[obsidian]"
            )

        self._vault_path = Path(vault_path).resolve()
        self._poll_strategy = poll_strategy
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
            f"obsidian_tasks:{absolute_vault_path}"
        """
        return f"obsidian_tasks:{self._vault_path}"

    @property
    def domain(self) -> Domain:
        """Return the domain this adapter serves."""
        return Domain.TASKS

    @property
    def normalizer_version(self) -> str:
        """Return the normalizer version."""
        return "1.0.0"

    def _is_kanban_file(self, post_metadata: dict[str, Any]) -> bool:
        """Check if frontmatter metadata indicates Kanban plugin format.

        Args:
            post_metadata: The YAML frontmatter metadata dictionary

        Returns:
            True if the metadata has kanban-plugin: basic
        """
        return post_metadata.get("kanban-plugin") == "basic"

    def _is_kanban_file_from_content(self, markdown: str) -> bool:
        """Detect Kanban format from markdown content when frontmatter is unavailable.

        Since Kanban files created by the Obsidian Kanban plugin always have
        `kanban-plugin` in their frontmatter, we detect this specific marker
        even when YAML parsing fails. This is much more conservative than
        structural heuristics which could match any markdown file with headings.

        Args:
            markdown: The markdown content

        Returns:
            True if the content contains the kanban-plugin marker
        """
        # Check for the kanban-plugin marker in the first 500 characters
        # (frontmatter block is always at the start)
        return "kanban-plugin" in markdown[:500]

    def _extract_due_date(self, text: str) -> str | None:
        """Extract due date from task text.

        Checks emoji format (📅 YYYY-MM-DD) first, then dataview format ([due:: YYYY-MM-DD]).
        Emoji format takes precedence.

        Args:
            text: The task text

        Returns:
            ISO 8601 formatted date string (YYYY-MM-DDTHH:MM:SSZ) or None
        """
        # Check emoji format first (higher precedence)
        match = DUE_EMOJI.search(text)
        if match:
            # Convert YYYY-MM-DD to ISO 8601 format with time
            date_str = match.group(1)
            return f"{date_str}T00:00:00Z"

        # Check dataview format
        match = DUE_DATAVIEW.search(text)
        if match:
            # Convert YYYY-MM-DD to ISO 8601 format with time
            date_str = match.group(1)
            return f"{date_str}T00:00:00Z"

        return None

    def _extract_priority(self, text: str) -> int | None:
        """Extract priority from task text using emoji flags.

        Args:
            text: The task text

        Returns:
            Priority number (1-4, where 1 is highest) or None
        """
        match = PRIORITY_EMOJI.search(text)
        if match:
            emoji = match.group(1)
            return _PRIORITY_MAP.get(emoji)
        return None

    def _extract_dependencies(self, text: str) -> tuple[str, ...]:
        """Extract task dependencies from task text.

        Checks emoji format (⛔ task-id) first, then dataview format ([depends:: ...]).

        Args:
            text: The task text

        Returns:
            Tuple of dependency task IDs
        """
        dependencies = []

        # Check emoji format
        for match in DEPENDENCY.finditer(text):
            dependencies.append(match.group(1))

        # Check dataview format (only if no emoji format dependencies found)
        if not dependencies:
            dv_match = DEPENDENCY_DATAVIEW.search(text)
            if dv_match:
                # Parse comma-separated list
                deps_str = dv_match.group(1)
                for dep in deps_str.split(","):
                    dep = dep.strip()
                    if dep:
                        dependencies.append(dep)

        return tuple(dependencies)

    def _parse_standard_tasks(self, file_path: Path, markdown: str) -> Iterator[dict[str, Any]]:
        """Parse tasks from standard Obsidian Tasks checkbox syntax.

        Args:
            file_path: Path to the markdown file
            markdown: Markdown content of the file

        Yields:
            Dictionary with task metadata
        """
        for task_match in TASK_PATTERN.finditer(markdown):
            marker = task_match.group(1)
            title = task_match.group(2).strip()

            # Skip empty tasks
            if not title:
                continue

            status = _STATUS_MAP.get(marker.lower(), "open")
            due_date = self._extract_due_date(title)
            priority = self._extract_priority(title)
            dependencies = self._extract_dependencies(title)

            # Compute actual line number from match position in markdown
            line_number = markdown[:task_match.start()].count('\n') + 1

            # Get file-relative path for source_id
            file_rel_path = file_path.relative_to(self._vault_path)

            yield {
                "source_id": f"{file_rel_path}/{line_number}",
                "title": title,
                "status": status,
                "due_date": due_date,
                "priority": priority,
                "dependencies": dependencies,
                "file_path": str(file_path),
                "line_number": line_number,
            }

    def _parse_kanban_tasks(self, file_path: Path, markdown: str) -> Iterator[dict[str, Any]]:
        """Parse tasks from Kanban plugin format (headings as lanes, list items as tasks).

        Kanban format:
        - Headings (##, ###) represent lanes/statuses
        - List items under headings are task cards

        Args:
            file_path: Path to the markdown file
            markdown: Markdown content of the file

        Yields:
            Dictionary with task metadata
        """
        lines = markdown.split("\n")
        current_lane = "open"

        for line_number, line in enumerate(lines, start=1):
            # Check for heading (lane name)
            heading_match = re.match(r"^#{2,3}\s+(.+)$", line)
            if heading_match:
                lane_name = heading_match.group(1).strip()
                # Map lane name to status
                current_lane = _KANBAN_STATUS_MAP.get(
                    lane_name.lower(), "open"
                )
                continue

            # Check for list item (task card)
            list_match = re.match(r"^\s*[-*]\s+(.+)$", line)
            if list_match:
                title = list_match.group(1).strip()

                # Strip checkbox prefix if present (e.g., "[ ] Task" -> "Task")
                checkbox_match = re.match(r"^\[.\]\s+(.+)$", title)
                if checkbox_match:
                    title = checkbox_match.group(1).strip()

                if not title:
                    continue

                # Get file-relative path for source_id
                file_rel_path = file_path.relative_to(self._vault_path)

                # Extract metadata from kanban task text
                due_date = self._extract_due_date(title)
                priority = self._extract_priority(title)
                dependencies = self._extract_dependencies(title)

                yield {
                    "source_id": f"{file_rel_path}/{line_number}",
                    "title": title,
                    "status": current_lane,
                    "due_date": due_date,
                    "priority": priority,
                    "dependencies": dependencies,
                    "file_path": str(file_path),
                    "line_number": line_number,
                }

    def fetch(self, source_ref: str) -> Iterator[NormalizedContent]:
        """Fetch and normalize tasks from the Obsidian vault.

        Recursively discovers all .md files in the vault and yields NormalizedContent
        for each task found, using either standard Obsidian Tasks syntax or Kanban format.

        Args:
            source_ref: Unused for Obsidian Tasks adapter (uses self._vault_path)

        Yields:
            NormalizedContent for each task found

        Raises:
            FileNotFoundError: If the vault directory does not exist
            NotADirectoryError: If the vault path exists but is not a directory
        """
        if not self._vault_path.exists():
            raise FileNotFoundError(f"Vault directory does not exist: {self._vault_path}")

        if not self._vault_path.is_dir():
            raise NotADirectoryError(f"Vault path is not a directory: {self._vault_path}")

        for file_path in self._vault_path.rglob("*.md"):
            if not file_path.is_file():
                continue

            try:
                post = frontmatter.load(str(file_path))
                markdown = post.content
            except (PermissionError, FileNotFoundError) as e:
                # File access errors - don't try fallback
                logger.warning(f"Cannot access file {file_path}: {e}")
                continue
            except UnicodeDecodeError as e:
                # Encoding error in frontmatter parsing
                logger.warning(f"Cannot decode file {file_path}: {e}")
                continue
            except Exception as e:
                # Frontmatter parsing errors (YAML errors, etc.) - try reading raw content
                logger.warning(
                    f"Frontmatter parsing failed for {file_path} ({type(e).__name__}), "
                    f"trying raw content only (Kanban detection may be inaccurate)"
                )
                try:
                    markdown = file_path.read_text(encoding="utf-8")
                    # If we got raw content, we don't have metadata for kanban detection
                    post = None
                except UnicodeDecodeError:
                    logger.warning(
                        f"Cannot read file {file_path} - not UTF-8 encoded. "
                        f"Ensure all vault files are UTF-8 encoded."
                    )
                    continue
                except PermissionError:
                    logger.warning(f"Cannot read file {file_path} - permission denied")
                    continue
                except FileNotFoundError:
                    logger.debug(f"File disappeared during processing: {file_path}")
                    continue
                except OSError as os_error:
                    logger.warning(f"Cannot read file {file_path} - OS error: {os_error}")
                    continue

            # Skip empty files
            if not markdown.strip():
                logger.debug(f"Skipping empty file: {file_path} (no tasks)")
                continue

            # Determine if this is a Kanban file
            # First check frontmatter metadata if available, then fall back to content analysis
            if post is not None:
                is_kanban = self._is_kanban_file(post.metadata)
            else:
                is_kanban = self._is_kanban_file_from_content(markdown)
                if is_kanban:
                    logger.debug(
                        f"Detected Kanban format from content in {file_path} "
                        f"(frontmatter metadata unavailable)"
                    )

            # Parse tasks based on format
            if is_kanban:
                task_gen = self._parse_kanban_tasks(file_path, markdown)
            else:
                task_gen = self._parse_standard_tasks(file_path, markdown)

            # Yield NormalizedContent for each task
            for task_data in task_gen:
                try:
                    now = datetime.now(timezone.utc).isoformat()

                    # Build extra_metadata with TaskMetadata fields
                    extra_metadata = {
                        "task_id": task_data["source_id"],
                        "title": task_data["title"],
                        "status": task_data["status"],
                        "due_date": task_data["due_date"],
                        "priority": task_data["priority"],
                        "dependencies": task_data["dependencies"],
                        "collaborators": (),
                        "date_first_observed": now,
                        "source_type": "obsidian_tasks",
                    }

                    # Build structural hints
                    structural_hints = StructuralHints(
                        has_headings=False,
                        has_lists=False,
                        has_tables=False,
                        natural_boundaries=(),
                        file_path=task_data["file_path"],
                        extra_metadata=extra_metadata,
                    )

                    # Yield normalized content
                    yield NormalizedContent(
                        markdown=task_data["title"],
                        source_id=task_data["source_id"],
                        structural_hints=structural_hints,
                        normalizer_version=self.normalizer_version,
                    )

                except ValueError as parse_error:
                    # Data validation error in task creation (Pydantic validation error)
                    logger.warning(
                        f"Invalid task data in {file_path} "
                        f"(source_id={task_data.get('source_id')}): {parse_error}"
                    )
                    continue

    def _on_file_changed(self, event: FileEvent) -> None:
        """Handle filesystem changes in push mode.

        Called by FileSystemWatcher when a file is created, modified, or deleted.

        Args:
            event: FileEvent containing the path and event type

        Note:
            This method logs the change but does not trigger re-ingestion.
            Full push-mode support (triggering selective re-ingestion) requires
            integration with the document store framework. The framework should
            call fetch() after detecting a file change.
        """
        logger.debug(f"File change detected in vault: {event.path} ({event.event_type})")
