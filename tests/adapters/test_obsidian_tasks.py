"""Tests for the ObsidianTasksAdapter."""

from datetime import datetime

import pytest

from context_library.adapters.obsidian_tasks import ObsidianTasksAdapter
from context_library.storage.models import (
    Domain,
    NormalizedContent,
    PollStrategy,
    TaskMetadata,
)


@pytest.fixture
def vault_with_standard_tasks(tmp_path):
    """Create a fixture vault with standard Obsidian Tasks checkbox syntax."""
    vault = tmp_path / "test_vault_standard"
    vault.mkdir()

    # Create a file with various task statuses
    task_file = vault / "tasks.md"
    task_content = """---
title: "Task List"
tags:
  - tasks
---

# My Tasks

- [ ] Open task with no metadata
- [x] Completed task 📅 2024-12-25
- [/] In progress task 🔺
- [-] Cancelled task

## High Priority Tasks

- [ ] Important task 🔺 📅 2024-12-20
- [ ] High priority task ⏫ 🔼 depends on task-1
- [ ] Medium priority task 🔼 [due:: 2024-12-31]

## With Dependencies

- [ ] Task with dependency ⛔ parent-task-1
- [ ] Task with dataview dependency [depends:: dep1, dep2]
- [ ] Task with emoji dependency 📅 2024-12-15 ⛔ my-task
"""
    task_file.write_text(task_content, encoding="utf-8")

    return vault


@pytest.fixture
def vault_with_kanban(tmp_path):
    """Create a fixture vault with Kanban plugin format."""
    vault = tmp_path / "test_vault_kanban"
    vault.mkdir()

    # Create a kanban file
    kanban_file = vault / "board.md"
    kanban_content = """---
kanban-plugin: basic
title: "Project Board"
---

## TODO

- [ ] Setup development environment
- [ ] Review requirements 🔺 📅 2024-12-25
- [ ] Design architecture ⏫

## In Progress

- [ ] Implement feature A 📅 2024-12-20
- [ ] Write unit tests ⛔ feature-a-impl

## Done

- [ ] Project kickoff
- [ ] Initial planning 📅 2024-11-15
"""
    kanban_file.write_text(kanban_content, encoding="utf-8")

    return vault


@pytest.fixture
def vault_mixed(tmp_path):
    """Create a vault with both standard tasks and kanban files."""
    vault = tmp_path / "test_vault_mixed"
    vault.mkdir()

    # Add standard tasks file
    tasks_file = vault / "tasks.md"
    tasks_content = """---
title: "Regular Tasks"
---

# Tasks

- [ ] Task 1
- [x] Task 2 📅 2024-12-25
"""
    tasks_file.write_text(tasks_content, encoding="utf-8")

    # Add kanban file
    kanban_file = vault / "kanban.md"
    kanban_content = """---
kanban-plugin: basic
---

## TODO

- Task A 🔺

## Done

- Task B
"""
    kanban_file.write_text(kanban_content, encoding="utf-8")

    # Add nested directory with tasks
    nested_dir = vault / "nested"
    nested_dir.mkdir()
    nested_file = nested_dir / "nested_tasks.md"
    nested_content = """- [ ] Nested task 1
- [x] Nested task 2 ⏫
"""
    nested_file.write_text(nested_content, encoding="utf-8")

    return vault


@pytest.fixture
def minimal_vault(tmp_path):
    """Create a minimal vault with a single task."""
    vault = tmp_path / "minimal_vault"
    vault.mkdir()

    task_file = vault / "single.md"
    task_file.write_text("- [ ] Simple task\n", encoding="utf-8")

    return vault


@pytest.fixture
def empty_vault(tmp_path):
    """Create an empty vault."""
    vault = tmp_path / "empty_vault"
    vault.mkdir()
    return vault


class TestObsidianTasksAdapterProperties:
    """Tests for ObsidianTasksAdapter properties."""

    def test_adapter_id_deterministic(self, vault_with_standard_tasks):
        """adapter_id is deterministic for the same vault."""
        adapter1 = ObsidianTasksAdapter(vault_with_standard_tasks)
        adapter2 = ObsidianTasksAdapter(vault_with_standard_tasks)

        assert adapter1.adapter_id == adapter2.adapter_id

    def test_adapter_id_includes_path(self, vault_with_standard_tasks):
        """adapter_id includes the vault path."""
        adapter = ObsidianTasksAdapter(vault_with_standard_tasks)
        assert str(vault_with_standard_tasks.resolve()) in adapter.adapter_id
        assert "obsidian_tasks:" in adapter.adapter_id

    def test_adapter_domain_is_tasks(self, vault_with_standard_tasks):
        """domain property returns Domain.TASKS."""
        adapter = ObsidianTasksAdapter(vault_with_standard_tasks)
        assert adapter.domain == Domain.TASKS

    def test_normalizer_version(self, vault_with_standard_tasks):
        """normalizer_version returns correct version."""
        adapter = ObsidianTasksAdapter(vault_with_standard_tasks)
        assert adapter.normalizer_version == "1.0.0"

    def test_poll_strategy_pull_default(self, vault_with_standard_tasks):
        """Default poll strategy is PULL."""
        adapter = ObsidianTasksAdapter(vault_with_standard_tasks)
        assert adapter._poll_strategy == PollStrategy.PULL

    def test_poll_strategy_push(self, vault_with_standard_tasks):
        """Poll strategy can be set to PUSH."""
        adapter = ObsidianTasksAdapter(vault_with_standard_tasks, poll_strategy=PollStrategy.PUSH)
        assert adapter._poll_strategy == PollStrategy.PUSH
        assert adapter._watcher is not None

    def test_frontmatter_import_error(self):
        """ImportError is raised if frontmatter is not installed."""
        # This test will only work if frontmatter is mocked as unavailable
        # For now, we just verify the adapter requires it
        from context_library.adapters.obsidian_tasks import HAS_FRONTMATTER

        assert HAS_FRONTMATTER is True  # Should be available in test environment


class TestStandardTasksParsing:
    """Tests for parsing Obsidian Tasks checkbox syntax."""

    def test_fetch_discovers_all_tasks(self, vault_with_standard_tasks):
        """fetch() discovers all tasks in the vault."""
        adapter = ObsidianTasksAdapter(vault_with_standard_tasks)
        tasks = list(adapter.fetch(""))

        # The fixture has tasks.md with 10 tasks total
        assert len(tasks) == 10  # All tasks in the fixture

    def test_task_yields_normalized_content(self, vault_with_standard_tasks):
        """Each task yields a NormalizedContent instance."""
        adapter = ObsidianTasksAdapter(vault_with_standard_tasks)
        tasks = list(adapter.fetch(""))

        assert all(isinstance(t, NormalizedContent) for t in tasks)

    def test_open_status_mapping(self, vault_with_standard_tasks):
        """[ ] maps to 'open' status."""
        adapter = ObsidianTasksAdapter(vault_with_standard_tasks)
        tasks = list(adapter.fetch(""))

        # First task should be open
        assert tasks[0].structural_hints.extra_metadata["status"] == "open"

    def test_completed_status_mapping(self, vault_with_standard_tasks):
        """[x] maps to 'completed' status."""
        adapter = ObsidianTasksAdapter(vault_with_standard_tasks)
        tasks = list(adapter.fetch(""))

        # Should have completed task(s)
        completed_tasks = [
            t for t in tasks if t.structural_hints.extra_metadata["status"] == "completed"
        ]
        assert len(completed_tasks) >= 1

    def test_in_progress_status_mapping(self, vault_with_standard_tasks):
        """[/] maps to 'in-progress' status."""
        adapter = ObsidianTasksAdapter(vault_with_standard_tasks)
        tasks = list(adapter.fetch(""))

        in_progress = [
            t for t in tasks if t.structural_hints.extra_metadata["status"] == "in-progress"
        ]
        assert len(in_progress) >= 1

    def test_cancelled_status_mapping(self, vault_with_standard_tasks):
        """[-] maps to 'cancelled' status."""
        adapter = ObsidianTasksAdapter(vault_with_standard_tasks)
        tasks = list(adapter.fetch(""))

        cancelled = [
            t for t in tasks if t.structural_hints.extra_metadata["status"] == "cancelled"
        ]
        assert len(cancelled) >= 1

    def test_due_date_emoji_format(self, vault_with_standard_tasks):
        """Due date is extracted from emoji format 📅 YYYY-MM-DD."""
        adapter = ObsidianTasksAdapter(vault_with_standard_tasks)
        tasks = list(adapter.fetch(""))

        # Find task with due date (should be ISO 8601 format)
        task_with_date = next(
            (t for t in tasks if t.structural_hints.extra_metadata.get("due_date") == "2024-12-25T00:00:00Z"),
            None,
        )
        assert task_with_date is not None

    def test_due_date_dataview_format(self, vault_with_standard_tasks):
        """Due date is extracted from dataview format [due:: YYYY-MM-DD]."""
        adapter = ObsidianTasksAdapter(vault_with_standard_tasks)
        tasks = list(adapter.fetch(""))

        # Find task with dataview due date (should be ISO 8601 format)
        task_with_date = next(
            (t for t in tasks if t.structural_hints.extra_metadata.get("due_date") == "2024-12-31T00:00:00Z"),
            None,
        )
        assert task_with_date is not None

    def test_priority_emoji_highest(self, vault_with_standard_tasks):
        """🔺 emoji maps to priority 1 (highest)."""
        adapter = ObsidianTasksAdapter(vault_with_standard_tasks)
        tasks = list(adapter.fetch(""))

        # Find task with highest priority
        task_priority_1 = next(
            (t for t in tasks if t.structural_hints.extra_metadata.get("priority") == 1),
            None,
        )
        assert task_priority_1 is not None

    def test_priority_emoji_high(self, vault_with_standard_tasks):
        """⏫ emoji maps to priority 2 (high)."""
        adapter = ObsidianTasksAdapter(vault_with_standard_tasks)
        tasks = list(adapter.fetch(""))

        # Find task with priority 2
        task_priority_2 = next(
            (t for t in tasks if t.structural_hints.extra_metadata.get("priority") == 2),
            None,
        )
        assert task_priority_2 is not None

    def test_priority_emoji_medium(self, vault_with_standard_tasks):
        """🔼 emoji maps to priority 3 (medium)."""
        adapter = ObsidianTasksAdapter(vault_with_standard_tasks)
        tasks = list(adapter.fetch(""))

        # Find task with priority 3
        task_priority_3 = next(
            (t for t in tasks if t.structural_hints.extra_metadata.get("priority") == 3),
            None,
        )
        assert task_priority_3 is not None

    def test_priority_emoji_low(self, vault_with_standard_tasks):
        """🔽 emoji maps to priority 4 (low)."""
        from context_library.adapters.obsidian_tasks import _PRIORITY_MAP

        # Low priority not in fixture, but we can test the mapping
        assert _PRIORITY_MAP["🔽"] == 4

    def test_dependencies_emoji_format(self, vault_with_standard_tasks):
        """Dependencies are extracted from emoji format ⛔ task-id."""
        adapter = ObsidianTasksAdapter(vault_with_standard_tasks)
        tasks = list(adapter.fetch(""))

        # Find task with emoji dependency
        task_with_deps = next(
            (
                t
                for t in tasks
                if t.structural_hints.extra_metadata.get("dependencies")
                and "my-task" in t.structural_hints.extra_metadata["dependencies"]
            ),
            None,
        )
        assert task_with_deps is not None

    def test_dependencies_dataview_format(self, vault_with_standard_tasks):
        """Dependencies are extracted from dataview format [depends:: ...]."""
        adapter = ObsidianTasksAdapter(vault_with_standard_tasks)
        tasks = list(adapter.fetch(""))

        # Find task with dataview dependencies
        task_with_deps = next(
            (
                t
                for t in tasks
                if t.structural_hints.extra_metadata.get("dependencies")
                and ("dep1" in t.structural_hints.extra_metadata["dependencies"]
                     or "dep2" in t.structural_hints.extra_metadata["dependencies"])
            ),
            None,
        )
        assert task_with_deps is not None

    def test_source_id_includes_file_and_line(self, vault_with_standard_tasks):
        """source_id includes relative file path and line number."""
        adapter = ObsidianTasksAdapter(vault_with_standard_tasks)
        tasks = list(adapter.fetch(""))

        for task in tasks:
            # source_id should be like "tasks.md/1"
            assert "/" in task.source_id
            parts = task.source_id.rsplit("/", 1)
            assert len(parts) == 2
            assert parts[0].endswith(".md")
            assert parts[1].isdigit()

    def test_task_metadata_validation(self, vault_with_standard_tasks):
        """extra_metadata validates as TaskMetadata."""
        adapter = ObsidianTasksAdapter(vault_with_standard_tasks)
        tasks = list(adapter.fetch(""))

        for task in tasks:
            meta = task.structural_hints.extra_metadata
            # Should not raise validation error
            TaskMetadata.model_validate(meta)


class TestKanbanParsing:
    """Tests for parsing Kanban plugin format."""

    def test_fetch_discovers_kanban_tasks(self, vault_with_kanban):
        """fetch() discovers tasks in kanban format."""
        adapter = ObsidianTasksAdapter(vault_with_kanban)
        tasks = list(adapter.fetch(""))

        assert len(tasks) > 0

    def test_kanban_lane_to_status_mapping_done(self, vault_with_kanban):
        """'Done' lane maps to 'completed' status."""
        adapter = ObsidianTasksAdapter(vault_with_kanban)
        tasks = list(adapter.fetch(""))

        completed_tasks = [
            t for t in tasks if t.structural_hints.extra_metadata["status"] == "completed"
        ]
        # Should have tasks from the Done column
        assert len(completed_tasks) > 0

    def test_kanban_lane_to_status_mapping_in_progress(self, vault_with_kanban):
        """'In Progress' lane maps to 'in-progress' status."""
        adapter = ObsidianTasksAdapter(vault_with_kanban)
        tasks = list(adapter.fetch(""))

        in_progress_tasks = [
            t for t in tasks if t.structural_hints.extra_metadata["status"] == "in-progress"
        ]
        # Should have tasks from the In Progress column
        assert len(in_progress_tasks) > 0

    def test_kanban_lane_to_status_mapping_todo(self, vault_with_kanban):
        """'TODO' lane (not mapped) defaults to 'open' status."""
        adapter = ObsidianTasksAdapter(vault_with_kanban)
        tasks = list(adapter.fetch(""))

        open_tasks = [t for t in tasks if t.structural_hints.extra_metadata["status"] == "open"]
        # Should have tasks from the TODO column
        assert len(open_tasks) > 0

    def test_kanban_inherits_metadata_extraction(self, vault_with_kanban):
        """Kanban tasks inherit metadata extraction (due date, priority, deps)."""
        adapter = ObsidianTasksAdapter(vault_with_kanban)
        tasks = list(adapter.fetch(""))

        # Find task with priority
        task_with_priority = next(
            (t for t in tasks if t.structural_hints.extra_metadata.get("priority")),
            None,
        )
        assert task_with_priority is not None

        # Find task with due date
        task_with_date = next(
            (t for t in tasks if t.structural_hints.extra_metadata.get("due_date")),
            None,
        )
        assert task_with_date is not None

    def test_kanban_task_count(self, vault_with_kanban):
        """Kanban file yields correct number of tasks."""
        adapter = ObsidianTasksAdapter(vault_with_kanban)
        tasks = list(adapter.fetch(""))

        # Should have 7 tasks in the kanban file
        assert len(tasks) == 7


class TestMixedVault:
    """Tests for vaults with both standard and kanban files."""

    def test_mixed_vault_discovers_all_formats(self, vault_mixed):
        """Vault with mixed formats discovers tasks from both types."""
        adapter = ObsidianTasksAdapter(vault_mixed)
        tasks = list(adapter.fetch(""))

        assert len(tasks) > 0

    def test_mixed_vault_includes_nested(self, vault_mixed):
        """Mixed vault includes tasks from nested directories."""
        adapter = ObsidianTasksAdapter(vault_mixed)
        tasks = list(adapter.fetch(""))

        # Check for nested tasks
        nested_tasks = [t for t in tasks if "nested" in t.source_id]
        assert len(nested_tasks) > 0


class TestEdgeCases:
    """Tests for edge cases and error handling."""

    def test_empty_vault(self, empty_vault):
        """Empty vault yields no tasks."""
        adapter = ObsidianTasksAdapter(empty_vault)
        tasks = list(adapter.fetch(""))

        assert len(tasks) == 0

    def test_minimal_vault(self, minimal_vault):
        """Minimal vault with single task works correctly."""
        adapter = ObsidianTasksAdapter(minimal_vault)
        tasks = list(adapter.fetch(""))

        assert len(tasks) == 1
        assert tasks[0].structural_hints.extra_metadata["title"] == "Simple task"
        assert tasks[0].structural_hints.extra_metadata["status"] == "open"

    def test_nonexistent_vault_raises_error(self, tmp_path):
        """Nonexistent vault raises FileNotFoundError."""
        nonexistent = tmp_path / "does_not_exist"
        adapter = ObsidianTasksAdapter(nonexistent)

        with pytest.raises(FileNotFoundError):
            list(adapter.fetch(""))

    def test_file_instead_of_directory_raises_error(self, tmp_path):
        """File path instead of directory raises NotADirectoryError."""
        file_path = tmp_path / "not_a_dir.txt"
        file_path.write_text("content")

        adapter = ObsidianTasksAdapter(file_path)

        with pytest.raises(NotADirectoryError):
            list(adapter.fetch(""))

    def test_file_with_no_tasks(self, tmp_path):
        """File without tasks is skipped."""
        vault = tmp_path / "vault"
        vault.mkdir()

        empty_file = vault / "empty.md"
        empty_file.write_text("# Title\n\nJust some content, no tasks.\n")

        adapter = ObsidianTasksAdapter(vault)
        tasks = list(adapter.fetch(""))

        assert len(tasks) == 0

    def test_malformed_frontmatter_handled(self, tmp_path):
        """Malformed frontmatter is handled gracefully."""
        vault = tmp_path / "vault"
        vault.mkdir()

        bad_fm = vault / "bad.md"
        bad_fm.write_text("---\ninvalid: [\nbroken\n---\n\n- [ ] Task\n")

        adapter = ObsidianTasksAdapter(vault)
        tasks = list(adapter.fetch(""))

        # Should still find the task despite bad frontmatter
        assert len(tasks) >= 1

    def test_empty_task_title_skipped(self, tmp_path):
        """Tasks with empty titles are skipped."""
        vault = tmp_path / "vault"
        vault.mkdir()

        task_file = vault / "tasks.md"
        task_file.write_text("- [ ] \n- [ ] Valid task\n")

        adapter = ObsidianTasksAdapter(vault)
        tasks = list(adapter.fetch(""))

        # Only the valid task should be yielded
        assert len(tasks) == 1
        assert tasks[0].structural_hints.extra_metadata["title"] == "Valid task"

    def test_task_extra_metadata_structure(self, minimal_vault):
        """Task extra_metadata has all required fields."""
        adapter = ObsidianTasksAdapter(minimal_vault)
        tasks = list(adapter.fetch(""))

        task = tasks[0]
        meta = task.structural_hints.extra_metadata

        required_fields = [
            "task_id",
            "title",
            "status",
            "due_date",
            "priority",
            "dependencies",
            "collaborators",
            "date_first_observed",
            "source_type",
        ]

        for field in required_fields:
            assert field in meta, f"Missing field: {field}"

    def test_date_first_observed_is_iso8601(self, minimal_vault):
        """date_first_observed is in ISO 8601 format."""
        adapter = ObsidianTasksAdapter(minimal_vault)
        tasks = list(adapter.fetch(""))

        date_str = tasks[0].structural_hints.extra_metadata["date_first_observed"]
        # Should be parseable as ISO 8601
        try:
            datetime.fromisoformat(date_str)
        except ValueError:
            pytest.fail(f"date_first_observed is not ISO 8601: {date_str}")

    def test_structural_hints_default_values(self, minimal_vault):
        """Structural hints have correct default values for tasks."""
        adapter = ObsidianTasksAdapter(minimal_vault)
        tasks = list(adapter.fetch(""))

        hints = tasks[0].structural_hints
        assert hints.has_headings is False
        assert hints.has_lists is False
        assert hints.has_tables is False
        assert hints.natural_boundaries == ()


class TestPushMode:
    """Tests for push mode (filesystem watcher)."""

    def test_push_mode_initializes_watcher(self, vault_with_standard_tasks):
        """Push mode initializes a FileSystemWatcher."""
        adapter = ObsidianTasksAdapter(
            vault_with_standard_tasks, poll_strategy=PollStrategy.PUSH
        )

        assert adapter._watcher is not None

    def test_push_mode_watcher_scoped_to_md(self, vault_with_standard_tasks):
        """Watcher in push mode is scoped to .md files."""
        adapter = ObsidianTasksAdapter(
            vault_with_standard_tasks, poll_strategy=PollStrategy.PUSH
        )

        assert adapter._watcher._extensions == {".md"}


class TestIntegration:
    """Integration tests."""

    def test_full_workflow_standard_tasks(self, vault_with_standard_tasks):
        """Full workflow: init, fetch, validate tasks."""
        adapter = ObsidianTasksAdapter(vault_with_standard_tasks)

        # Verify adapter properties
        assert adapter.adapter_id.startswith("obsidian_tasks:")
        assert adapter.domain == Domain.TASKS
        assert adapter.normalizer_version == "1.0.0"

        # Fetch all tasks
        tasks = list(adapter.fetch(""))
        assert len(tasks) > 0

        # Verify each task
        for task in tasks:
            # Should be NormalizedContent
            assert isinstance(task, NormalizedContent)

            # Should have valid source_id
            assert task.source_id
            assert "/" in task.source_id

            # Should have valid extra_metadata
            meta = task.structural_hints.extra_metadata
            assert meta

            # Should validate as TaskMetadata
            TaskMetadata.model_validate(meta)

    def test_full_workflow_kanban(self, vault_with_kanban):
        """Full workflow with kanban files."""
        adapter = ObsidianTasksAdapter(vault_with_kanban)

        tasks = list(adapter.fetch(""))
        assert len(tasks) > 0

        # All tasks should be valid
        for task in tasks:
            assert isinstance(task, NormalizedContent)
            TaskMetadata.model_validate(task.structural_hints.extra_metadata)
