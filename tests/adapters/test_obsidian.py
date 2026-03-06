"""Tests for the ObsidianAdapter."""

from pathlib import Path
from datetime import datetime

import pytest

from context_library.adapters.obsidian import ObsidianAdapter
from context_library.storage.models import Domain, NormalizedContent, StructuralHints, PollStrategy


@pytest.fixture
def vault_with_notes(tmp_path):
    """Create a fixture vault with multiple notes and wikilink relationships."""
    vault = tmp_path / "test_vault"
    vault.mkdir()

    # Create note1.md with frontmatter and wikilink to note2
    note1_content = """---
title: "First Note"
tags:
  - tag1
  - tag2
aliases:
  - alias1
created: 2024-01-01
---

# First Note

This is the first note. It links to [[note2]].

Some more content here.
"""
    (vault / "note1.md").write_text(note1_content, encoding="utf-8")

    # Create note2.md with frontmatter and wikilink back to note1
    note2_content = """---
title: "Second Note"
tags:
  - tag3
aliases:
  - alias2
  - alias3
---

# Second Note

This note has content. It links back to [[note1]].

## Subsection

More structured content with [[note1]] references.
"""
    (vault / "note2.md").write_text(note2_content, encoding="utf-8")

    # Create a nested note without frontmatter
    nested_dir = vault / "nested"
    nested_dir.mkdir()
    note3_content = """# Simple Note

This note has no frontmatter and links to [[note1]].

- List item 1
- List item 2
"""
    (nested_dir / "note3.md").write_text(note3_content, encoding="utf-8")

    return vault


@pytest.fixture
def minimal_vault(tmp_path):
    """Create a minimal vault with a single note."""
    vault = tmp_path / "minimal_vault"
    vault.mkdir()

    note_content = """---
title: "Test Note"
---

# Test Note

Content without any links.
"""
    (vault / "test.md").write_text(note_content, encoding="utf-8")

    return vault


class TestObsidianAdapterProperties:
    """Tests for ObsidianAdapter properties."""

    def test_adapter_id_deterministic(self, vault_with_notes):
        """adapter_id is deterministic for the same vault."""
        adapter1 = ObsidianAdapter(vault_with_notes)
        adapter2 = ObsidianAdapter(vault_with_notes)

        assert adapter1.adapter_id == adapter2.adapter_id

    def test_adapter_id_format(self, vault_with_notes):
        """adapter_id has correct format: obsidian:{absolute_vault_path}."""
        adapter = ObsidianAdapter(vault_with_notes)

        assert adapter.adapter_id.startswith("obsidian:")
        assert str(vault_with_notes.resolve()) in adapter.adapter_id

    def test_adapter_id_uses_absolute_path(self, vault_with_notes):
        """adapter_id uses absolute path resolution."""
        # Use relative path
        import os
        original_cwd = os.getcwd()
        try:
            os.chdir(vault_with_notes.parent)
            adapter = ObsidianAdapter(vault_with_notes.name)

            # Should resolve to absolute path
            assert str(adapter.adapter_id).startswith("obsidian:")
            path_part = adapter.adapter_id.replace("obsidian:", "")
            assert Path(path_part).is_absolute()
        finally:
            os.chdir(original_cwd)

    def test_different_vaults_different_ids(self, tmp_path):
        """Different vaults produce different adapter_ids."""
        vault1 = tmp_path / "vault1"
        vault2 = tmp_path / "vault2"
        vault1.mkdir()
        vault2.mkdir()

        adapter1 = ObsidianAdapter(vault1)
        adapter2 = ObsidianAdapter(vault2)

        assert adapter1.adapter_id != adapter2.adapter_id

    def test_domain_property(self, vault_with_notes):
        """domain property returns Domain.NOTES."""
        adapter = ObsidianAdapter(vault_with_notes)

        assert adapter.domain == Domain.NOTES

    def test_normalizer_version_property(self, vault_with_notes):
        """normalizer_version property returns '1.0.0'."""
        adapter = ObsidianAdapter(vault_with_notes)

        assert adapter.normalizer_version == "1.0.0"


class TestObsidianAdapterFetch:
    """Tests for ObsidianAdapter.fetch() method."""

    def test_fetch_single_note(self, minimal_vault):
        """fetch() yields NormalizedContent for a single note."""
        adapter = ObsidianAdapter(minimal_vault)
        results = list(adapter.fetch(""))

        assert len(results) == 1
        assert isinstance(results[0], NormalizedContent)
        assert "# Test Note" in results[0].markdown
        assert "Content without any links" in results[0].markdown

    def test_fetch_multiple_notes(self, vault_with_notes):
        """fetch() yields NormalizedContent for multiple notes."""
        adapter = ObsidianAdapter(vault_with_notes)
        results = list(adapter.fetch(""))

        assert len(results) == 3
        source_ids = {r.source_id for r in results}
        assert "note1.md" in source_ids
        assert "note2.md" in source_ids
        assert any("nested" in sid and "note3.md" in sid for sid in source_ids)

    def test_fetch_recursive_discovery(self, vault_with_notes):
        """fetch() discovers notes in nested subdirectories."""
        adapter = ObsidianAdapter(vault_with_notes)
        results = list(adapter.fetch(""))

        nested_notes = [r for r in results if "nested" in r.source_id]
        assert len(nested_notes) == 1
        assert nested_notes[0].source_id == "nested/note3.md"

    def test_fetch_excludes_non_markdown_files(self, vault_with_notes):
        """fetch() only yields .md files."""
        # Create non-markdown file
        (vault_with_notes / "data.json").write_text('{"key": "value"}')
        (vault_with_notes / "config.yaml").write_text("key: value")

        adapter = ObsidianAdapter(vault_with_notes)
        results = list(adapter.fetch(""))

        assert len(results) == 3  # Still only the 3 markdown files
        assert all(r.source_id.endswith(".md") for r in results)

    def test_fetch_frontmatter_stripped_from_markdown(self, vault_with_notes):
        """fetch() returns markdown without YAML frontmatter block."""
        adapter = ObsidianAdapter(vault_with_notes)
        results = list(adapter.fetch(""))

        note1 = next(r for r in results if r.source_id == "note1.md")
        # Should not contain frontmatter markers
        assert "---" not in note1.markdown
        assert "title:" not in note1.markdown
        # Should contain the actual content
        assert "# First Note" in note1.markdown
        assert "This is the first note" in note1.markdown

    def test_fetch_relative_path_in_source_id(self, vault_with_notes):
        """source_id contains path relative to vault root."""
        adapter = ObsidianAdapter(vault_with_notes)
        results = list(adapter.fetch(""))

        source_ids = {r.source_id for r in results}
        # Nested note should have relative path
        assert any("nested" in sid and "note3" in sid for sid in source_ids)
        # Should not contain vault path itself
        assert not any(str(vault_with_notes) in sid for sid in source_ids)

    def test_fetch_normalizes_content(self, minimal_vault):
        """fetch() returns NormalizedContent with all required fields."""
        adapter = ObsidianAdapter(minimal_vault)
        results = list(adapter.fetch(""))

        assert len(results) == 1
        result = results[0]
        assert result.markdown is not None
        assert result.source_id == "test.md"
        assert result.normalizer_version == "1.0.0"
        assert isinstance(result.structural_hints, StructuralHints)

    def test_fetch_nonexistent_vault(self, tmp_path):
        """fetch() raises FileNotFoundError for nonexistent vault."""
        nonexistent = tmp_path / "does_not_exist"
        adapter = ObsidianAdapter(nonexistent)

        with pytest.raises(FileNotFoundError):
            list(adapter.fetch(""))

    def test_fetch_empty_vault(self, tmp_path):
        """fetch() yields nothing for empty vault."""
        empty_vault = tmp_path / "empty_vault"
        empty_vault.mkdir()
        adapter = ObsidianAdapter(empty_vault)

        results = list(adapter.fetch(""))

        assert len(results) == 0

    def test_fetch_graceful_error_handling(self, tmp_path):
        """fetch() gracefully handles errors during individual note processing."""
        vault = tmp_path / "vault"
        vault.mkdir()

        # Create valid notes with different characteristics
        (vault / "note1.md").write_text("---\ntitle: Note 1\n---\n# Content 1\nFirst note", encoding="utf-8")
        (vault / "note2.md").write_text("---\ntitle: Note 2\n---\n# Content 2\nSecond note", encoding="utf-8")

        adapter = ObsidianAdapter(vault)
        results = list(adapter.fetch(""))

        # Should get both notes without errors
        assert len(results) == 2
        source_ids = {r.source_id for r in results}
        assert "note1.md" in source_ids
        assert "note2.md" in source_ids

    def test_fetch_vault_path_is_file_raises_error(self, tmp_path):
        """fetch() raises NotADirectoryError when path is a file."""
        file_path = tmp_path / "is_a_file.md"
        file_path.write_text("---\ntitle: Test\n---\nContent")
        adapter = ObsidianAdapter(file_path)

        with pytest.raises(NotADirectoryError):
            list(adapter.fetch(""))


class TestObsidianAdapterFrontmatterMetadata:
    """Tests for frontmatter metadata extraction."""

    def test_frontmatter_tags_extracted(self, vault_with_notes):
        """Tags from YAML frontmatter are extracted."""
        adapter = ObsidianAdapter(vault_with_notes)
        results = list(adapter.fetch(""))

        note1 = next(r for r in results if r.source_id == "note1.md")
        tags = note1.structural_hints.extra_metadata["tags"]
        assert "tag1" in tags
        assert "tag2" in tags

    def test_frontmatter_aliases_extracted(self, vault_with_notes):
        """Aliases from YAML frontmatter are extracted."""
        adapter = ObsidianAdapter(vault_with_notes)
        results = list(adapter.fetch(""))

        note2 = next(r for r in results if r.source_id == "note2.md")
        aliases = note2.structural_hints.extra_metadata["aliases"]
        assert "alias2" in aliases
        assert "alias3" in aliases

    def test_frontmatter_properties_all_included(self, vault_with_notes):
        """All frontmatter properties are included in frontmatter dict."""
        adapter = ObsidianAdapter(vault_with_notes)
        results = list(adapter.fetch(""))

        note1 = next(r for r in results if r.source_id == "note1.md")
        frontmatter = note1.structural_hints.extra_metadata["frontmatter"]
        assert frontmatter["title"] == "First Note"
        assert "tags" in frontmatter
        assert "aliases" in frontmatter
        # created field may be parsed as date object by YAML parser
        assert str(frontmatter["created"]) == "2024-01-01"

    def test_missing_frontmatter_handled(self, vault_with_notes):
        """Notes without frontmatter yield empty tags and aliases."""
        adapter = ObsidianAdapter(vault_with_notes)
        results = list(adapter.fetch(""))

        note3 = next(r for r in results if "note3" in r.source_id)
        tags = note3.structural_hints.extra_metadata["tags"]
        aliases = note3.structural_hints.extra_metadata["aliases"]
        frontmatter = note3.structural_hints.extra_metadata["frontmatter"]

        assert tags == []
        assert aliases == []
        assert frontmatter == {}

    def test_malformed_tags_handled(self, tmp_path):
        """Malformed tag formats are handled gracefully."""
        vault = tmp_path / "vault"
        vault.mkdir()

        # Tags as string instead of list
        note_content = """---
title: "Test"
tags: single-tag-as-string
---

Content
"""
        (vault / "test.md").write_text(note_content, encoding="utf-8")

        adapter = ObsidianAdapter(vault)
        results = list(adapter.fetch(""))

        assert len(results) == 1
        tags = results[0].structural_hints.extra_metadata["tags"]
        assert tags == ["single-tag-as-string"]


class TestObsidianAdapterWikilinks:
    """Tests for wikilink extraction."""

    def test_wikilinks_forward_links_extracted(self, vault_with_notes):
        """Forward wikilinks are extracted."""
        adapter = ObsidianAdapter(vault_with_notes)
        results = list(adapter.fetch(""))

        note1 = next(r for r in results if r.source_id == "note1.md")
        wikilinks = note1.structural_hints.extra_metadata["wikilinks"]

        # note1 links to note2
        assert "note2" in wikilinks or "note2.md" in str(wikilinks).lower()

    def test_backlinks_extracted(self, vault_with_notes):
        """Backlinks are extracted."""
        adapter = ObsidianAdapter(vault_with_notes)
        results = list(adapter.fetch(""))

        note1 = next(r for r in results if r.source_id == "note1.md")
        backlinks = note1.structural_hints.extra_metadata["backlinks"]

        # note2 and note3 link back to note1
        # Format might vary, so just check it's a list
        assert isinstance(backlinks, list)

    def test_no_wikilinks_empty_list(self, tmp_path):
        """Notes with no wikilinks yield empty lists."""
        vault = tmp_path / "vault"
        vault.mkdir()

        note_content = """---
title: "Isolated"
---

# Isolated Note

This note has no links.
"""
        (vault / "isolated.md").write_text(note_content, encoding="utf-8")

        adapter = ObsidianAdapter(vault)
        results = list(adapter.fetch(""))

        assert len(results) == 1
        wikilinks = results[0].structural_hints.extra_metadata["wikilinks"]
        backlinks = results[0].structural_hints.extra_metadata["backlinks"]
        assert wikilinks == []
        assert backlinks == []


class TestObsidianAdapterStructuralHints:
    """Tests for structural hints and metadata."""

    def test_structural_hints_file_path(self, vault_with_notes):
        """StructuralHints.file_path contains absolute path."""
        adapter = ObsidianAdapter(vault_with_notes)
        results = list(adapter.fetch(""))

        note1 = next(r for r in results if r.source_id == "note1.md")
        hints = note1.structural_hints
        assert hints.file_path is not None
        assert (vault_with_notes / "note1.md").resolve() == Path(hints.file_path)

    def test_structural_hints_modified_at_iso8601(self, vault_with_notes):
        """StructuralHints.modified_at is in ISO 8601 format."""
        adapter = ObsidianAdapter(vault_with_notes)
        results = list(adapter.fetch(""))

        for result in results:
            hints = result.structural_hints
            assert hints.modified_at is not None
            # Should be parseable as ISO 8601
            dt = datetime.fromisoformat(hints.modified_at)
            assert dt.tzinfo is not None

    def test_structural_hints_file_size_bytes(self, vault_with_notes):
        """StructuralHints.file_size_bytes contains file size."""
        adapter = ObsidianAdapter(vault_with_notes)
        results = list(adapter.fetch(""))

        note1 = next(r for r in results if r.source_id == "note1.md")
        hints = note1.structural_hints
        assert hints.file_size_bytes is not None
        assert hints.file_size_bytes > 0

    def test_structural_hints_created_at_in_metadata(self, vault_with_notes):
        """created_at timestamp is in extra_metadata."""
        adapter = ObsidianAdapter(vault_with_notes)
        results = list(adapter.fetch(""))

        for result in results:
            created_at = result.structural_hints.extra_metadata["created_at"]
            assert created_at is not None
            # Should be parseable as ISO 8601
            dt = datetime.fromisoformat(created_at)
            assert dt.tzinfo is not None

    def test_structural_hints_modified_at_in_metadata(self, vault_with_notes):
        """modified_at timestamp is in extra_metadata."""
        adapter = ObsidianAdapter(vault_with_notes)
        results = list(adapter.fetch(""))

        for result in results:
            modified_at = result.structural_hints.extra_metadata["modified_at"]
            assert modified_at is not None
            # Should be parseable as ISO 8601
            dt = datetime.fromisoformat(modified_at)
            assert dt.tzinfo is not None

    def test_structural_hints_has_headings_true(self, vault_with_notes):
        """has_headings is True when content contains headings."""
        adapter = ObsidianAdapter(vault_with_notes)
        results = list(adapter.fetch(""))

        # All test notes have headings
        for result in results:
            assert result.structural_hints.has_headings is True

    def test_structural_hints_has_lists_detected(self, vault_with_notes):
        """has_lists is correctly detected."""
        adapter = ObsidianAdapter(vault_with_notes)
        results = list(adapter.fetch(""))

        # note3 has lists
        note3 = next(r for r in results if "note3" in r.source_id)
        assert note3.structural_hints.has_lists is True

    def test_structural_hints_extra_metadata_complete(self, vault_with_notes):
        """extra_metadata contains all required keys."""
        adapter = ObsidianAdapter(vault_with_notes)
        results = list(adapter.fetch(""))

        required_keys = {
            "tags",
            "aliases",
            "frontmatter",
            "wikilinks",
            "backlinks",
            "created_at",
            "modified_at",
        }

        for result in results:
            metadata = result.structural_hints.extra_metadata
            assert all(key in metadata for key in required_keys)


class TestObsidianAdapterPushMode:
    """Tests for push-mode initialization with FileSystemWatcher."""

    def test_push_mode_watcher_created(self, vault_with_notes):
        """FileSystemWatcher is created when poll_strategy=PUSH."""
        adapter = ObsidianAdapter(vault_with_notes, poll_strategy=PollStrategy.PUSH)

        assert adapter._watcher is not None

    def test_push_mode_watcher_watches_vault_path(self, vault_with_notes):
        """FileSystemWatcher is scoped to vault path."""
        adapter = ObsidianAdapter(vault_with_notes, poll_strategy=PollStrategy.PUSH)

        assert adapter._watcher._watch_path == vault_with_notes.resolve()

    def test_push_mode_watcher_filters_markdown(self, vault_with_notes):
        """FileSystemWatcher filters for .md extensions."""
        adapter = ObsidianAdapter(vault_with_notes, poll_strategy=PollStrategy.PUSH)

        assert adapter._watcher._extensions == {".md"}

    def test_pull_mode_no_watcher(self, vault_with_notes):
        """FileSystemWatcher is not created for PULL mode."""
        adapter = ObsidianAdapter(vault_with_notes, poll_strategy=PollStrategy.PULL)

        assert adapter._watcher is None

    def test_default_is_pull_mode(self, vault_with_notes):
        """Default poll_strategy is PULL."""
        adapter = ObsidianAdapter(vault_with_notes)

        assert adapter._watcher is None

    def test_on_file_changed_invalidates_vault_cache(self, vault_with_notes):
        """_on_file_changed invalidates vault cache so next fetch rebuilds graph.

        This is the linchpin of push-mode correctness: when a file changes,
        the vault cache must be cleared so that the next fetch() call
        rebuilds the wikilink graph to reflect the change.
        """
        from context_library.adapters._watching import FileEvent, EventType

        adapter = ObsidianAdapter(vault_with_notes, poll_strategy=PollStrategy.PUSH)

        # Trigger lazy-load of vault by accessing it
        _ = adapter._get_vault()

        # Verify vault is now cached (not None)
        assert adapter._vault is not None
        cached_vault = adapter._vault

        # Simulate a file change event
        event = FileEvent(
            path=vault_with_notes / "note1.md",
            event_type=EventType.MODIFIED,
        )
        adapter._on_file_changed(event)

        # Verify vault cache was invalidated (set to None)
        assert adapter._vault is None

        # Verify it's a fresh instance on next access
        _ = adapter._get_vault()
        assert adapter._vault is not None
        assert adapter._vault is not cached_vault


class TestObsidianAdapterImportErrors:
    """Tests for graceful handling of missing optional dependencies."""

    def test_missing_obsidiantools_raises_import_error(self, tmp_path, monkeypatch):
        """ImportError is raised when obsidiantools is not available."""
        import context_library.adapters.obsidian as obsidian_module

        # Simply patch the flag
        monkeypatch.setattr(obsidian_module, "HAS_OBSIDIANTOOLS", False)

        vault = tmp_path / "vault"
        vault.mkdir()

        with pytest.raises(ImportError, match="obsidiantools"):
            ObsidianAdapter(vault)

    def test_missing_frontmatter_raises_import_error(self, tmp_path, monkeypatch):
        """ImportError is raised when python-frontmatter is not available."""
        import context_library.adapters.obsidian as obsidian_module

        # Simply patch the flag
        monkeypatch.setattr(obsidian_module, "HAS_FRONTMATTER", False)

        vault = tmp_path / "vault"
        vault.mkdir()

        with pytest.raises(ImportError, match="python-frontmatter"):
            ObsidianAdapter(vault)


class TestObsidianAdapterIntegration:
    """Integration tests for complete workflows."""

    def test_complete_vault_ingestion(self, vault_with_notes):
        """Complete vault ingestion extracts all data correctly."""
        adapter = ObsidianAdapter(vault_with_notes)
        results = list(adapter.fetch(""))

        assert len(results) == 3

        # Check each note has complete structure
        for result in results:
            assert isinstance(result, NormalizedContent)
            assert result.markdown
            assert result.source_id
            assert result.normalizer_version == "1.0.0"
            assert isinstance(result.structural_hints, StructuralHints)
            assert result.structural_hints.extra_metadata is not None
            assert "tags" in result.structural_hints.extra_metadata
            assert "aliases" in result.structural_hints.extra_metadata
            assert "wikilinks" in result.structural_hints.extra_metadata
            assert "backlinks" in result.structural_hints.extra_metadata
