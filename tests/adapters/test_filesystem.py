"""Tests for the FilesystemAdapter."""

from pathlib import Path
from datetime import datetime

import pytest

from context_library.adapters.filesystem import FilesystemAdapter
from context_library.storage.models import Domain, NormalizedContent, StructuralHints


class TestFilesystemAdapterProperties:
    """Tests for FilesystemAdapter properties."""

    def test_adapter_id_deterministic(self, tmp_path):
        """adapter_id is deterministic for the same directory."""
        adapter1 = FilesystemAdapter(tmp_path)
        adapter2 = FilesystemAdapter(tmp_path)

        assert adapter1.adapter_id == adapter2.adapter_id

    def test_adapter_id_format(self, tmp_path):
        """adapter_id has correct format: filesystem:{absolute_path}."""
        adapter = FilesystemAdapter(tmp_path)

        assert adapter.adapter_id.startswith("filesystem:")
        assert str(tmp_path.resolve()) in adapter.adapter_id

    def test_adapter_id_uses_absolute_path(self, tmp_path):
        """adapter_id uses absolute path resolution."""
        # Create relative path
        relative_path = Path(".")
        adapter = FilesystemAdapter(relative_path)

        # Should resolve to absolute path
        assert str(adapter.adapter_id).startswith("filesystem:")
        # The path part should be absolute
        path_part = adapter.adapter_id.replace("filesystem:", "")
        assert Path(path_part).is_absolute()

    def test_different_directories_different_ids(self, tmp_path):
        """Different directories produce different adapter_ids."""
        dir1 = tmp_path / "dir1"
        dir2 = tmp_path / "dir2"
        dir1.mkdir()
        dir2.mkdir()

        adapter1 = FilesystemAdapter(dir1)
        adapter2 = FilesystemAdapter(dir2)

        assert adapter1.adapter_id != adapter2.adapter_id

    def test_domain_property(self, tmp_path):
        """domain property returns Domain.NOTES."""
        adapter = FilesystemAdapter(tmp_path)

        assert adapter.domain == Domain.NOTES

    def test_normalizer_version_property(self, tmp_path):
        """normalizer_version property returns '1.0.0'."""
        adapter = FilesystemAdapter(tmp_path)

        assert adapter.normalizer_version == "1.0.0"


class TestFilesystemAdapterFetch:
    """Tests for FilesystemAdapter.fetch() method."""

    def test_fetch_single_markdown_file(self, tmp_path):
        """fetch() yields NormalizedContent for a single .md file."""
        md_file = tmp_path / "test.md"
        md_file.write_text("# Hello\n\nThis is content.", encoding="utf-8")

        adapter = FilesystemAdapter(tmp_path)
        results = list(adapter.fetch("unused"))

        assert len(results) == 1
        assert isinstance(results[0], NormalizedContent)
        assert results[0].markdown == "# Hello\n\nThis is content."
        assert results[0].source_id == "test.md"

    def test_fetch_multiple_markdown_files(self, tmp_path):
        """fetch() yields NormalizedContent for multiple .md files."""
        (tmp_path / "file1.md").write_text("Content 1", encoding="utf-8")
        (tmp_path / "file2.md").write_text("Content 2", encoding="utf-8")
        (tmp_path / "file3.md").write_text("Content 3", encoding="utf-8")

        adapter = FilesystemAdapter(tmp_path)
        results = list(adapter.fetch("unused"))

        assert len(results) == 3
        source_ids = {r.source_id for r in results}
        assert source_ids == {"file1.md", "file2.md", "file3.md"}

    def test_fetch_recursive_discovery(self, tmp_path):
        """fetch() discovers .md files in nested subdirectories."""
        (tmp_path / "file1.md").write_text("Top level", encoding="utf-8")
        (tmp_path / "subdir").mkdir()
        (tmp_path / "subdir" / "file2.md").write_text("Nested 1", encoding="utf-8")
        (tmp_path / "subdir" / "nested").mkdir()
        (tmp_path / "subdir" / "nested" / "file3.md").write_text(
            "Nested 2", encoding="utf-8"
        )

        adapter = FilesystemAdapter(tmp_path)
        results = list(adapter.fetch("unused"))

        assert len(results) == 3
        source_ids = {r.source_id for r in results}
        # Source IDs should be relative paths with forward slashes
        assert "file1.md" in source_ids
        assert any("subdir" in sid for sid in source_ids)
        assert any("nested" in sid for sid in source_ids)

    def test_fetch_excludes_non_markdown_files(self, tmp_path):
        """fetch() does not yield non-.md files."""
        (tmp_path / "file.md").write_text("Markdown", encoding="utf-8")
        (tmp_path / "file.txt").write_text("Text", encoding="utf-8")
        (tmp_path / "file.py").write_text("Python", encoding="utf-8")
        (tmp_path / "README").write_text("No extension", encoding="utf-8")

        adapter = FilesystemAdapter(tmp_path)
        results = list(adapter.fetch("unused"))

        assert len(results) == 1
        assert results[0].source_id == "file.md"

    def test_fetch_relative_path_in_source_id(self, tmp_path):
        """source_id contains relative path from base directory."""
        subdir = tmp_path / "notes" / "work"
        subdir.mkdir(parents=True)
        (subdir / "meeting.md").write_text("Meeting notes", encoding="utf-8")

        adapter = FilesystemAdapter(tmp_path)
        results = list(adapter.fetch("unused"))

        assert len(results) == 1
        # Should be relative path with proper separators
        assert "notes" in results[0].source_id
        assert "meeting.md" in results[0].source_id

    def test_fetch_normalizes_content(self, tmp_path):
        """fetch() returns NormalizedContent with all required fields."""
        md_file = tmp_path / "test.md"
        content = "# Header\n\nSome text"
        md_file.write_text(content, encoding="utf-8")

        adapter = FilesystemAdapter(tmp_path)
        results = list(adapter.fetch("unused"))

        result = results[0]
        assert result.markdown == content
        assert result.source_id == "test.md"
        assert result.normalizer_version == "1.0.0"
        assert isinstance(result.structural_hints, StructuralHints)

    def test_fetch_nonexistent_directory(self, tmp_path):
        """fetch() raises FileNotFoundError for nonexistent directory."""
        nonexistent = tmp_path / "does_not_exist"
        adapter = FilesystemAdapter(nonexistent)

        with pytest.raises(FileNotFoundError):
            list(adapter.fetch("unused"))

    def test_fetch_empty_directory(self, tmp_path):
        """fetch() yields nothing for empty directory."""
        adapter = FilesystemAdapter(tmp_path)

        results = list(adapter.fetch("unused"))

        assert len(results) == 0

    def test_fetch_invalid_utf8_file_skipped(self, tmp_path):
        """fetch() skips files that cannot be decoded as UTF-8."""
        md_file = tmp_path / "valid.md"
        md_file.write_text("Valid content", encoding="utf-8")

        # Create a file with invalid UTF-8
        invalid_file = tmp_path / "invalid.md"
        invalid_file.write_bytes(b"Invalid \xff\xfe UTF-8")

        adapter = FilesystemAdapter(tmp_path)
        results = list(adapter.fetch("unused"))

        # Should only get the valid file
        assert len(results) == 1
        assert results[0].source_id == "valid.md"

    def test_fetch_path_is_file_raises_error(self, tmp_path):
        """fetch() raises NotADirectoryError when path is a file."""
        file_path = tmp_path / "is_a_file.txt"
        file_path.write_text("I am a file")
        adapter = FilesystemAdapter(file_path)

        with pytest.raises(NotADirectoryError):
            list(adapter.fetch("unused"))


class TestFilesystemAdapterStructuralHints:
    """Tests for structural hints population in NormalizedContent."""

    def test_structural_hints_has_file_path(self, tmp_path):
        """StructuralHints.file_path contains absolute path."""
        md_file = tmp_path / "test.md"
        md_file.write_text("Content", encoding="utf-8")

        adapter = FilesystemAdapter(tmp_path)
        results = list(adapter.fetch("unused"))

        hints = results[0].structural_hints
        assert hints.file_path is not None
        assert hints.file_path == str(md_file.resolve())

    def test_structural_hints_has_modified_at(self, tmp_path):
        """StructuralHints.modified_at is in ISO 8601 format."""
        md_file = tmp_path / "test.md"
        md_file.write_text("Content", encoding="utf-8")

        adapter = FilesystemAdapter(tmp_path)
        results = list(adapter.fetch("unused"))

        hints = results[0].structural_hints
        assert hints.modified_at is not None
        # Should be parseable as ISO 8601
        dt = datetime.fromisoformat(hints.modified_at)
        assert dt.tzinfo is not None

    def test_structural_hints_has_file_size_bytes(self, tmp_path):
        """StructuralHints.file_size_bytes contains file size."""
        md_file = tmp_path / "test.md"
        content = "Hello World!"
        md_file.write_text(content, encoding="utf-8")

        adapter = FilesystemAdapter(tmp_path)
        results = list(adapter.fetch("unused"))

        hints = results[0].structural_hints
        assert hints.file_size_bytes is not None
        assert hints.file_size_bytes == len(content.encode("utf-8"))

    def test_structural_hints_has_headings_true(self, tmp_path):
        """has_headings is True when content contains '#'."""
        md_file = tmp_path / "test.md"
        md_file.write_text("# Header\n\nContent", encoding="utf-8")

        adapter = FilesystemAdapter(tmp_path)
        results = list(adapter.fetch("unused"))

        assert results[0].structural_hints.has_headings is True

    def test_structural_hints_has_headings_false(self, tmp_path):
        """has_headings is False when content lacks '#'."""
        md_file = tmp_path / "test.md"
        md_file.write_text("Just plain text\n\nNo headers", encoding="utf-8")

        adapter = FilesystemAdapter(tmp_path)
        results = list(adapter.fetch("unused"))

        assert results[0].structural_hints.has_headings is False

    def test_structural_hints_has_lists_true(self, tmp_path):
        """has_lists is True when content contains list markers."""
        # Test with dash
        md_file = tmp_path / "test1.md"
        md_file.write_text("- Item 1\n- Item 2", encoding="utf-8")

        adapter = FilesystemAdapter(tmp_path)
        results = list(adapter.fetch("unused"))

        assert results[0].structural_hints.has_lists is True

    def test_structural_hints_has_lists_with_asterisk(self, tmp_path):
        """has_lists is True with asterisk list markers."""
        md_file = tmp_path / "test.md"
        md_file.write_text("* Item 1\n* Item 2", encoding="utf-8")

        adapter = FilesystemAdapter(tmp_path)
        results = list(adapter.fetch("unused"))

        assert results[0].structural_hints.has_lists is True

    def test_structural_hints_has_lists_with_plus(self, tmp_path):
        """has_lists is True with plus list markers."""
        md_file = tmp_path / "test.md"
        md_file.write_text("+ Item 1\n+ Item 2", encoding="utf-8")

        adapter = FilesystemAdapter(tmp_path)
        results = list(adapter.fetch("unused"))

        assert results[0].structural_hints.has_lists is True

    def test_structural_hints_has_lists_with_ordered_list(self, tmp_path):
        """has_lists is True with ordered list markers."""
        md_file = tmp_path / "test.md"
        md_file.write_text("1. Item 1\n2. Item 2\n3. Item 3", encoding="utf-8")

        adapter = FilesystemAdapter(tmp_path)
        results = list(adapter.fetch("unused"))

        assert results[0].structural_hints.has_lists is True

    def test_structural_hints_has_lists_with_ordered_list_double_digit(self, tmp_path):
        """has_lists is True with ordered lists using double-digit numbers."""
        md_file = tmp_path / "test.md"
        md_file.write_text("9. Item 9\n10. Item 10\n11. Item 11", encoding="utf-8")

        adapter = FilesystemAdapter(tmp_path)
        results = list(adapter.fetch("unused"))

        assert results[0].structural_hints.has_lists is True

    def test_structural_hints_has_lists_false(self, tmp_path):
        """has_lists is False without list markers."""
        md_file = tmp_path / "test.md"
        md_file.write_text("No lists here\nJust text", encoding="utf-8")

        adapter = FilesystemAdapter(tmp_path)
        results = list(adapter.fetch("unused"))

        assert results[0].structural_hints.has_lists is False

    def test_structural_hints_has_tables_true(self, tmp_path):
        """has_tables is True when content contains '|'."""
        md_file = tmp_path / "test.md"
        md_file.write_text("| Col1 | Col2 |\n|------|------|\n| A | B |", encoding="utf-8")

        adapter = FilesystemAdapter(tmp_path)
        results = list(adapter.fetch("unused"))

        assert results[0].structural_hints.has_tables is True

    def test_structural_hints_has_tables_false(self, tmp_path):
        """has_tables is False without pipe character."""
        md_file = tmp_path / "test.md"
        md_file.write_text("No tables here", encoding="utf-8")

        adapter = FilesystemAdapter(tmp_path)
        results = list(adapter.fetch("unused"))

        assert results[0].structural_hints.has_tables is False

    def test_structural_hints_has_headings_no_false_positive_hash_in_code(self, tmp_path):
        """has_headings is False when # is in code blocks or inline code."""
        md_file = tmp_path / "test.md"
        # Hash in code block and inline code should not match
        md_file.write_text(
            "Some text\n\n`#hashtag`\n\n```\n#define SOMETHING\n```\n\nEnd",
            encoding="utf-8"
        )

        adapter = FilesystemAdapter(tmp_path)
        results = list(adapter.fetch("unused"))

        assert results[0].structural_hints.has_headings is False

    def test_structural_hints_has_headings_no_false_positive_hash_in_issue_ref(self, tmp_path):
        """has_headings is False when # is in issue references like #123."""
        md_file = tmp_path / "test.md"
        md_file.write_text(
            "This fixes #123 and references #456\n\nNo actual headings here",
            encoding="utf-8"
        )

        adapter = FilesystemAdapter(tmp_path)
        results = list(adapter.fetch("unused"))

        assert results[0].structural_hints.has_headings is False

    def test_structural_hints_has_headings_no_false_positive_csharp_mention(self, tmp_path):
        """has_headings is False when # is in C# mention."""
        md_file = tmp_path / "test.md"
        md_file.write_text(
            "This is about C# programming language\n\nNo markdown headings",
            encoding="utf-8"
        )

        adapter = FilesystemAdapter(tmp_path)
        results = list(adapter.fetch("unused"))

        assert results[0].structural_hints.has_headings is False

    def test_structural_hints_has_tables_no_false_positive_pipe_in_code(self, tmp_path):
        """has_tables is False when pipes are in code blocks."""
        md_file = tmp_path / "test.md"
        # Pipes in code block should not match
        md_file.write_text(
            "Some text\n\n```\necho 'pipe | grep something'\n```\n\nEnd",
            encoding="utf-8"
        )

        adapter = FilesystemAdapter(tmp_path)
        results = list(adapter.fetch("unused"))

        assert results[0].structural_hints.has_tables is False

    def test_structural_hints_has_tables_no_false_positive_pipe_in_shell_command(self, tmp_path):
        """has_tables is False when pipes are in shell commands."""
        md_file = tmp_path / "test.md"
        # Pipes in inline code should not match
        md_file.write_text(
            "Run `cat file | grep pattern` to filter\n\nNo tables here",
            encoding="utf-8"
        )

        adapter = FilesystemAdapter(tmp_path)
        results = list(adapter.fetch("unused"))

        assert results[0].structural_hints.has_tables is False

    def test_structural_hints_natural_boundaries_empty(self, tmp_path):
        """natural_boundaries is an empty list."""
        md_file = tmp_path / "test.md"
        md_file.write_text("Content", encoding="utf-8")

        adapter = FilesystemAdapter(tmp_path)
        results = list(adapter.fetch("unused"))

        assert results[0].structural_hints.natural_boundaries == ()


class TestFilesystemAdapterErrorHandling:
    """Tests for specific error handling in FilesystemAdapter."""

    def test_fetch_permission_error_skips_file(self, tmp_path, monkeypatch):
        """fetch() skips files with permission errors and continues."""
        valid_file = tmp_path / "valid.md"
        valid_file.write_text("Valid content", encoding="utf-8")

        problem_file = tmp_path / "problem.md"
        problem_file.write_text("Problem content", encoding="utf-8")

        adapter = FilesystemAdapter(tmp_path)

        # Mock read_text to raise PermissionError on problem_file
        original_read_text = Path.read_text

        def mock_read_text(self, encoding="utf-8"):
            if self.name == "problem.md":
                raise PermissionError(f"Permission denied: {self}")
            return original_read_text(self, encoding=encoding)

        monkeypatch.setattr(Path, "read_text", mock_read_text)

        results = list(adapter.fetch("unused"))

        # Should only get the valid file, skipping the one with permission error
        assert len(results) == 1
        assert results[0].source_id == "valid.md"

    def test_fetch_file_deleted_during_iteration(self, tmp_path, monkeypatch):
        """fetch() handles FileNotFoundError during read gracefully."""
        valid_file = tmp_path / "valid.md"
        valid_file.write_text("Valid content", encoding="utf-8")

        problem_file = tmp_path / "problem.md"
        problem_file.write_text("Problem content", encoding="utf-8")

        adapter = FilesystemAdapter(tmp_path)

        # Mock read_text to simulate file deletion during read
        original_read_text = Path.read_text

        def mock_read_text(self, encoding="utf-8"):
            if self.name == "problem.md":
                raise FileNotFoundError(f"File deleted: {self}")
            return original_read_text(self, encoding=encoding)

        monkeypatch.setattr(Path, "read_text", mock_read_text)

        results = list(adapter.fetch("unused"))

        # Should get valid file, skip problem.md (deleted during iteration)
        assert len(results) == 1
        assert results[0].source_id == "valid.md"


class TestFilesystemAdapterIntegration:
    """Integration tests for FilesystemAdapter."""

    def test_complex_directory_structure(self, tmp_path):
        """fetch() works with complex nested directory structure."""
        # Create complex structure
        (tmp_path / "notes").mkdir()
        (tmp_path / "notes" / "personal.md").write_text("Personal", encoding="utf-8")
        (tmp_path / "notes" / "work").mkdir()
        (tmp_path / "notes" / "work" / "projects.md").write_text(
            "Projects", encoding="utf-8"
        )
        (tmp_path / "notes" / "work" / "archive").mkdir()
        (tmp_path / "notes" / "work" / "archive" / "2024.md").write_text(
            "Archive", encoding="utf-8"
        )
        (tmp_path / "README.md").write_text("Readme", encoding="utf-8")
        (tmp_path / "setup.py").write_text("Setup", encoding="utf-8")

        adapter = FilesystemAdapter(tmp_path)
        results = list(adapter.fetch("unused"))

        assert len(results) == 4
        source_ids = {r.source_id for r in results}
        assert "README.md" in source_ids
        assert "personal.md" in source_ids or any("personal" in s for s in source_ids)

    def test_fetch_with_various_encodings(self, tmp_path):
        """fetch() handles UTF-8 files correctly."""
        md_file = tmp_path / "unicode.md"
        # UTF-8 with special characters
        content = "# 你好世界 (Hello World)\n\nEmoji: 🚀 ✨"
        md_file.write_text(content, encoding="utf-8")

        adapter = FilesystemAdapter(tmp_path)
        results = list(adapter.fetch("unused"))

        assert len(results) == 1
        assert results[0].markdown == content

    def test_fetch_iterator_behavior(self, tmp_path):
        """fetch() returns an iterator that can be consumed incrementally."""
        (tmp_path / "file1.md").write_text("Content 1", encoding="utf-8")
        (tmp_path / "file2.md").write_text("Content 2", encoding="utf-8")

        adapter = FilesystemAdapter(tmp_path)
        iterator = adapter.fetch("unused")

        # Check it's an iterator
        assert hasattr(iterator, "__iter__")
        assert hasattr(iterator, "__next__")

        # Can consume incrementally
        first = next(iterator)
        assert isinstance(first, NormalizedContent)

        second = next(iterator)
        assert isinstance(second, NormalizedContent)
