"""Tests for FilesystemAdapter conversion features (MarkItDown, Pandoc, extensions)."""

import subprocess
from pathlib import Path
from datetime import datetime
from unittest.mock import patch, MagicMock

import pytest

from context_library.adapters.filesystem import (
    FilesystemAdapter,
    _convert_with_markitdown,
    _convert_with_pandoc,
)
from context_library.storage.models import (
    Domain,
    NormalizedContent,
    PollStrategy,
)


class TestConversionFunctions:
    """Tests for _convert_with_markitdown and _convert_with_pandoc."""

    def test_markitdown_returns_none_without_library(self):
        """_convert_with_markitdown returns None if MarkItDown is not installed."""
        with patch("context_library.adapters.filesystem.HAS_MARKITDOWN", False):
            result = _convert_with_markitdown(Path("dummy.pdf"))

        assert result is None

    def test_markitdown_logs_traceback_on_error(self, tmp_path):
        """_convert_with_markitdown logs warning with exc_info on conversion error."""
        file_path = tmp_path / "test.pdf"
        file_path.write_text("dummy pdf", encoding="utf-8")

        with patch("context_library.adapters.filesystem.HAS_MARKITDOWN", True):
            with patch("context_library.adapters.filesystem.MarkItDown") as mock_class:
                mock_inst = MagicMock()
                mock_class.return_value = mock_inst
                mock_inst.convert.side_effect = ValueError("Corrupted PDF")
                with patch("context_library.adapters.filesystem.logger") as mock_logger:
                    result = _convert_with_markitdown(file_path)

        assert result is None
        mock_logger.warning.assert_called_once()
        call_kwargs = mock_logger.warning.call_args[1]
        assert call_kwargs.get("exc_info") is True

    def test_markitdown_catches_runtime_error(self, tmp_path):
        """_convert_with_markitdown catches RuntimeError."""
        file_path = tmp_path / "test.pdf"
        file_path.write_text("dummy", encoding="utf-8")

        with patch("context_library.adapters.filesystem.HAS_MARKITDOWN", True):
            with patch("context_library.adapters.filesystem.MarkItDown") as mock_class:
                mock_inst = MagicMock()
                mock_class.return_value = mock_inst
                mock_inst.convert.side_effect = RuntimeError("Timeout")
                result = _convert_with_markitdown(file_path)

        assert result is None

    def test_markitdown_catches_os_error(self, tmp_path):
        """_convert_with_markitdown catches OSError."""
        file_path = tmp_path / "test.pdf"
        file_path.write_text("dummy", encoding="utf-8")

        with patch("context_library.adapters.filesystem.HAS_MARKITDOWN", True):
            with patch("context_library.adapters.filesystem.MarkItDown") as mock_class:
                mock_inst = MagicMock()
                mock_class.return_value = mock_inst
                mock_inst.convert.side_effect = OSError("Disk full")
                result = _convert_with_markitdown(file_path)

        assert result is None

    def test_pandoc_returns_none_on_timeout(self, tmp_path):
        """_convert_with_pandoc returns None on subprocess timeout."""
        file_path = tmp_path / "test.tex"
        file_path.write_text(r"\documentclass{article}")

        with patch("context_library.adapters.filesystem.subprocess.run") as mock_run:
            mock_run.side_effect = subprocess.TimeoutExpired("pandoc", 30)
            result = _convert_with_pandoc(file_path)

        assert result is None

    def test_pandoc_returns_none_when_not_installed(self, tmp_path):
        """_convert_with_pandoc returns None when pandoc executable is missing."""
        file_path = tmp_path / "test.tex"
        file_path.write_text(r"\documentclass{article}")

        with patch("context_library.adapters.filesystem.subprocess.run") as mock_run:
            mock_run.side_effect = FileNotFoundError("pandoc not found")
            result = _convert_with_pandoc(file_path)

        assert result is None

    def test_pandoc_returns_none_on_nonzero_exit(self, tmp_path):
        """_convert_with_pandoc returns None when pandoc exits nonzero."""
        file_path = tmp_path / "test.tex"
        file_path.write_text(r"\documentclass{article}")

        with patch("context_library.adapters.filesystem.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=1, stdout="", stderr="Error")
            result = _convert_with_pandoc(file_path)

        assert result is None

    def test_pandoc_logs_stderr_on_nonzero_exit(self, tmp_path):
        """_convert_with_pandoc logs stderr content when pandoc fails."""
        file_path = tmp_path / "test.tex"
        file_path.write_text(r"\documentclass{article}")

        with patch("context_library.adapters.filesystem.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=1, stdout="", stderr="Unsupported format")
            with patch("context_library.adapters.filesystem.logger") as mock_logger:
                result = _convert_with_pandoc(file_path)

        assert result is None
        mock_logger.warning.assert_called_once()
        assert "Unsupported format" in str(mock_logger.warning.call_args)


class TestFetchConversion:
    """Tests for non-markdown file conversion in FilesystemAdapter.fetch()."""

    def test_fetch_converts_non_markdown_via_markitdown(self, tmp_path):
        """fetch() converts non-markdown files using MarkItDown."""
        html_file = tmp_path / "test.html"
        html_file.write_text("<h1>Title</h1><p>Content</p>", encoding="utf-8")

        adapter = FilesystemAdapter(tmp_path)

        with patch("context_library.adapters.filesystem._convert_with_markitdown", return_value="# Title\n\nContent"):
            results = list(adapter.fetch("unused"))

        assert len(results) == 1
        assert isinstance(results[0], NormalizedContent)
        assert results[0].markdown == "# Title\n\nContent"
        assert results[0].source_id == "test.html"

    def test_fetch_falls_back_to_pandoc_when_markitdown_fails(self, tmp_path):
        """fetch() falls back to Pandoc when MarkItDown returns None."""
        tex_file = tmp_path / "test.tex"
        tex_file.write_text(r"\documentclass{article}")

        adapter = FilesystemAdapter(tmp_path)

        with patch("context_library.adapters.filesystem._convert_with_markitdown", return_value=None), \
             patch("context_library.adapters.filesystem._convert_with_pandoc", return_value="# Hello") as mock_pandoc:
            results = list(adapter.fetch("unused"))

        assert len(results) == 1
        assert results[0].markdown == "# Hello"
        mock_pandoc.assert_called_once()

    def test_fetch_skips_file_when_both_converters_fail(self, tmp_path):
        """fetch() skips a file and logs a warning when both converters return None."""
        unknown_file = tmp_path / "test.xyz"
        unknown_file.write_text("Unknown format", encoding="utf-8")

        adapter = FilesystemAdapter(tmp_path)

        with patch("context_library.adapters.filesystem._convert_with_markitdown", return_value=None), \
             patch("context_library.adapters.filesystem._convert_with_pandoc", return_value=None), \
             patch("context_library.adapters.filesystem.logger") as mock_logger:
            results = list(adapter.fetch("unused"))

        assert len(results) == 0
        mock_logger.warning.assert_called()
        assert "Could not convert" in str(mock_logger.warning.call_args)

    def test_fetch_markdown_files_not_converted(self, tmp_path):
        """fetch() reads .md files directly without calling converters."""
        md_file = tmp_path / "test.md"
        md_file.write_text("# Direct read", encoding="utf-8")

        adapter = FilesystemAdapter(tmp_path)

        with patch("context_library.adapters.filesystem._convert_with_markitdown") as mock_md, \
             patch("context_library.adapters.filesystem._convert_with_pandoc") as mock_pandoc:
            results = list(adapter.fetch("unused"))

        assert len(results) == 1
        assert results[0].markdown == "# Direct read"
        mock_md.assert_not_called()
        mock_pandoc.assert_not_called()

    def test_fetch_mixed_files_processes_all(self, tmp_path):
        """fetch() processes both .md files (direct) and other files (converted)."""
        (tmp_path / "notes.md").write_text("# Notes", encoding="utf-8")
        (tmp_path / "report.html").write_text("<h1>Report</h1>", encoding="utf-8")

        adapter = FilesystemAdapter(tmp_path)

        with patch("context_library.adapters.filesystem._convert_with_markitdown", return_value="# Report"):
            results = list(adapter.fetch("unused"))

        assert len(results) == 2
        source_ids = {r.source_id for r in results}
        assert source_ids == {"notes.md", "report.html"}

    def test_fetch_recursive_non_markdown(self, tmp_path):
        """fetch() discovers non-markdown files in nested subdirectories."""
        (tmp_path / "sub").mkdir()
        (tmp_path / "file.html").write_text("<h1>Top</h1>", encoding="utf-8")
        (tmp_path / "sub" / "file.pdf").write_bytes(b"PDF")

        adapter = FilesystemAdapter(tmp_path)

        with patch("context_library.adapters.filesystem._convert_with_markitdown", return_value="Converted"):
            results = list(adapter.fetch("unused"))

        assert len(results) == 2
        source_ids = {r.source_id for r in results}
        assert "file.html" in source_ids
        assert "sub/file.pdf" in source_ids or "sub\\file.pdf" in source_ids


class TestExtensionFiltering:
    """Tests for the extensions parameter."""

    def test_extensions_filters_to_specified_types(self, tmp_path):
        """extensions parameter restricts which files are processed."""
        (tmp_path / "file.html").write_text("<h1>HTML</h1>", encoding="utf-8")
        (tmp_path / "file.pdf").write_bytes(b"PDF")
        (tmp_path / "file.txt").write_text("Text", encoding="utf-8")

        adapter = FilesystemAdapter(tmp_path, extensions={".pdf"})

        with patch("context_library.adapters.filesystem._convert_with_markitdown", return_value="Converted"):
            results = list(adapter.fetch("unused"))

        assert len(results) == 1
        assert results[0].source_id == "file.pdf"

    def test_extensions_includes_markdown_when_specified(self, tmp_path):
        """When .md is in extensions, markdown files are included."""
        (tmp_path / "notes.md").write_text("# Notes", encoding="utf-8")
        (tmp_path / "other.txt").write_text("Text", encoding="utf-8")

        adapter = FilesystemAdapter(tmp_path, extensions={".md"})
        results = list(adapter.fetch("unused"))

        assert len(results) == 1
        assert results[0].source_id == "notes.md"

    def test_none_extensions_processes_all_files(self, tmp_path):
        """None extensions (default) processes all file types."""
        (tmp_path / "file.md").write_text("Markdown", encoding="utf-8")
        (tmp_path / "file.html").write_text("<h1>HTML</h1>", encoding="utf-8")

        adapter = FilesystemAdapter(tmp_path, extensions=None)

        with patch("context_library.adapters.filesystem._convert_with_markitdown", return_value="# HTML"):
            results = list(adapter.fetch("unused"))

        assert len(results) == 2


class TestRichStructuralHints:
    """Tests for extra_metadata fields added from the conversion path."""

    def test_directory_hierarchy_in_extra_metadata(self, tmp_path):
        """extra_metadata includes directory_hierarchy for nested files."""
        (tmp_path / "level1" / "level2").mkdir(parents=True)
        file_path = tmp_path / "level1" / "level2" / "test.html"
        file_path.write_text("<h1>Title</h1>", encoding="utf-8")

        adapter = FilesystemAdapter(tmp_path)

        with patch("context_library.adapters.filesystem._convert_with_markitdown", return_value="# Title"):
            results = list(adapter.fetch("unused"))

        assert len(results) == 1
        hierarchy = results[0].structural_hints.extra_metadata["directory_hierarchy"]
        assert "level1" in hierarchy
        assert "level2" in hierarchy

    def test_directory_hierarchy_empty_for_root_files(self, tmp_path):
        """directory_hierarchy is empty for files at the root of the directory."""
        (tmp_path / "file.html").write_text("<h1>Title</h1>", encoding="utf-8")

        adapter = FilesystemAdapter(tmp_path)

        with patch("context_library.adapters.filesystem._convert_with_markitdown", return_value="# Title"):
            results = list(adapter.fetch("unused"))

        assert results[0].structural_hints.extra_metadata["directory_hierarchy"] == []

    def test_mime_type_in_extra_metadata_for_html(self, tmp_path):
        """extra_metadata includes document_type with the MIME type for HTML files."""
        (tmp_path / "test.html").write_text("<h1>Title</h1>", encoding="utf-8")

        adapter = FilesystemAdapter(tmp_path)

        with patch("context_library.adapters.filesystem._convert_with_markitdown", return_value="# Title"):
            results = list(adapter.fetch("unused"))

        assert results[0].structural_hints.extra_metadata["document_type"] == "text/html"

    def test_structure_detection_in_converted_content(self, tmp_path):
        """Headings, lists, and tables are detected in converted content."""
        (tmp_path / "test.html").write_text("<table>...</table>", encoding="utf-8")

        adapter = FilesystemAdapter(tmp_path)

        with patch(
            "context_library.adapters.filesystem._convert_with_markitdown",
            return_value="# Heading\n\n- item\n\n| A | B |\n|---|---|\n| 1 | 2 |",
        ):
            results = list(adapter.fetch("unused"))

        hints = results[0].structural_hints
        assert hints.has_headings is True
        assert hints.has_lists is True
        assert hints.has_tables is True


class TestPushModeInitialization:
    """Tests for PUSH mode filesystem watcher initialization."""

    def test_pull_mode_does_not_create_watcher(self, tmp_path):
        """PULL mode (default) does not create a FileSystemWatcher."""
        adapter = FilesystemAdapter(tmp_path, poll_strategy=PollStrategy.PULL)

        assert adapter._watcher is None

    @patch("context_library.adapters._watching.HAS_WATCHDOG", True)
    @patch("context_library.adapters._watching.HAS_WATCHFILES", False)
    def test_push_mode_creates_watcher(self, tmp_path):
        """PUSH mode creates a FileSystemWatcher instance."""
        adapter = FilesystemAdapter(tmp_path, poll_strategy=PollStrategy.PUSH)

        assert adapter._watcher is not None

    @patch("context_library.adapters._watching.HAS_WATCHDOG", True)
    @patch("context_library.adapters._watching.HAS_WATCHFILES", False)
    def test_push_mode_watcher_uses_correct_path(self, tmp_path):
        """Watcher is configured with the adapter's directory."""
        adapter = FilesystemAdapter(tmp_path, poll_strategy=PollStrategy.PUSH)

        assert adapter._watcher._watch_path == tmp_path
