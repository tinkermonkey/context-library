"""Tests for the RichFilesystemAdapter."""

import subprocess
from pathlib import Path
from datetime import datetime
from unittest.mock import patch, MagicMock

import pytest

from context_library.adapters.filesystem_rich import (
    RichFilesystemAdapter,
    _convert_with_markitdown,
    _convert_with_pandoc,
)
from context_library.storage.models import (
    Domain,
    NormalizedContent,
    PollStrategy,
)


class TestRichFilesystemAdapterProperties:
    """Tests for RichFilesystemAdapter properties."""

    def test_adapter_id_deterministic(self, tmp_path):
        """adapter_id is deterministic for the same directory."""
        adapter1 = RichFilesystemAdapter(tmp_path)
        adapter2 = RichFilesystemAdapter(tmp_path)

        assert adapter1.adapter_id == adapter2.adapter_id

    def test_adapter_id_format(self, tmp_path):
        """adapter_id has correct format: filesystem_rich:{absolute_path}."""
        adapter = RichFilesystemAdapter(tmp_path)

        assert adapter.adapter_id.startswith("filesystem_rich:")
        assert str(tmp_path.resolve()) in adapter.adapter_id

    def test_adapter_id_differs_from_filesystem_adapter(self, tmp_path):
        """RichFilesystemAdapter has different adapter_id from FilesystemAdapter."""
        from context_library.adapters.filesystem import FilesystemAdapter

        rich_adapter = RichFilesystemAdapter(tmp_path)
        regular_adapter = FilesystemAdapter(tmp_path)

        assert rich_adapter.adapter_id != regular_adapter.adapter_id
        assert rich_adapter.adapter_id.startswith("filesystem_rich:")
        assert regular_adapter.adapter_id.startswith("filesystem:")

    def test_different_directories_different_ids(self, tmp_path):
        """Different directories produce different adapter_ids."""
        dir1 = tmp_path / "dir1"
        dir2 = tmp_path / "dir2"
        dir1.mkdir()
        dir2.mkdir()

        adapter1 = RichFilesystemAdapter(dir1)
        adapter2 = RichFilesystemAdapter(dir2)

        assert adapter1.adapter_id != adapter2.adapter_id

    def test_domain_property(self, tmp_path):
        """domain property returns Domain.NOTES."""
        adapter = RichFilesystemAdapter(tmp_path)

        assert adapter.domain == Domain.NOTES

    def test_normalizer_version_property(self, tmp_path):
        """normalizer_version property returns '1.0.0'."""
        adapter = RichFilesystemAdapter(tmp_path)

        assert adapter.normalizer_version == "1.0.0"


class TestRichFilesystemAdapterFetch:
    """Tests for RichFilesystemAdapter.fetch() method."""

    def test_fetch_skips_markdown_files(self, tmp_path):
        """fetch() skips .md files (those are handled by FilesystemAdapter)."""
        (tmp_path / "test.md").write_text("# Markdown File", encoding="utf-8")
        (tmp_path / "test.html").write_text("<h1>HTML File</h1>", encoding="utf-8")

        adapter = RichFilesystemAdapter(tmp_path)

        with patch("context_library.adapters.filesystem_rich._convert_with_markitdown") as mock_md:
            mock_md.return_value = "<h1>HTML File</h1>"
            with patch("context_library.adapters.filesystem_rich._convert_with_pandoc") as mock_pandoc:
                mock_pandoc.return_value = None
                results = list(adapter.fetch("unused"))

        # Should only get the HTML file, not the markdown file
        assert len(results) == 1
        assert results[0].source_id == "test.html"

    def test_fetch_non_markdown_file_with_conversion(self, tmp_path):
        """fetch() converts non-markdown files to markdown."""
        html_file = tmp_path / "test.html"
        html_file.write_text("<h1>Title</h1><p>Content</p>", encoding="utf-8")

        adapter = RichFilesystemAdapter(tmp_path)

        with patch("context_library.adapters.filesystem_rich._convert_with_markitdown") as mock_md:
            mock_md.return_value = "# Title\n\nContent"
            results = list(adapter.fetch("unused"))

        assert len(results) == 1
        assert isinstance(results[0], NormalizedContent)
        assert results[0].markdown == "# Title\n\nContent"
        assert results[0].source_id == "test.html"

    def test_fetch_pandoc_fallback(self, tmp_path):
        """fetch() falls back to Pandoc when MarkItDown fails."""
        latex_file = tmp_path / "test.tex"
        latex_file.write_text(r"\documentclass{article}\begin{document}Hello\end{document}")

        adapter = RichFilesystemAdapter(tmp_path)

        with patch("context_library.adapters.filesystem_rich._convert_with_markitdown") as mock_md:
            mock_md.return_value = None  # MarkItDown fails
            with patch("context_library.adapters.filesystem_rich._convert_with_pandoc") as mock_pandoc:
                mock_pandoc.return_value = "# Hello"
                results = list(adapter.fetch("unused"))

        assert len(results) == 1
        assert results[0].markdown == "# Hello"
        mock_pandoc.assert_called_once()

    def test_fetch_skips_files_when_both_converters_fail(self, tmp_path):
        """fetch() skips file with warning when both converters fail."""
        unknown_file = tmp_path / "test.xyz"
        unknown_file.write_text("Unknown format", encoding="utf-8")

        adapter = RichFilesystemAdapter(tmp_path)

        with patch("context_library.adapters.filesystem_rich._convert_with_markitdown") as mock_md:
            mock_md.return_value = None
            with patch("context_library.adapters.filesystem_rich._convert_with_pandoc") as mock_pandoc:
                mock_pandoc.return_value = None
                with patch("context_library.adapters.filesystem_rich.logger") as mock_logger:
                    results = list(adapter.fetch("unused"))

        assert len(results) == 0
        mock_logger.warning.assert_called_once()
        assert "Could not convert file to markdown" in str(mock_logger.warning.call_args)

    def test_fetch_recursive_discovery(self, tmp_path):
        """fetch() discovers non-markdown files in nested subdirectories."""
        (tmp_path / "file1.html").write_text("<h1>Top</h1>", encoding="utf-8")
        (tmp_path / "subdir").mkdir()
        (tmp_path / "subdir" / "file2.pdf").write_text("PDF content", encoding="utf-8")
        (tmp_path / "subdir" / "nested").mkdir()
        (tmp_path / "subdir" / "nested" / "file3.docx").write_text("DOCX content", encoding="utf-8")

        adapter = RichFilesystemAdapter(tmp_path)

        with patch("context_library.adapters.filesystem_rich._convert_with_markitdown") as mock_md:
            mock_md.return_value = "Converted"
            results = list(adapter.fetch("unused"))

        assert len(results) == 3
        source_ids = {r.source_id for r in results}
        assert "file1.html" in source_ids
        assert "subdir/file2.pdf" in source_ids or "subdir\\file2.pdf" in source_ids
        assert "subdir/nested/file3.docx" in source_ids or "subdir\\nested\\file3.docx" in source_ids

    def test_fetch_extension_filtering(self, tmp_path):
        """fetch() filters by extension when configured."""
        (tmp_path / "file1.html").write_text("<h1>HTML</h1>", encoding="utf-8")
        (tmp_path / "file2.pdf").write_text("PDF", encoding="utf-8")
        (tmp_path / "file3.txt").write_text("Text", encoding="utf-8")

        adapter = RichFilesystemAdapter(tmp_path, extensions={".pdf"})

        with patch("context_library.adapters.filesystem_rich._convert_with_markitdown") as mock_md:
            mock_md.return_value = "Converted"
            results = list(adapter.fetch("unused"))

        assert len(results) == 1
        assert results[0].source_id == "file2.pdf"

    def test_fetch_structural_hints_mime_type(self, tmp_path):
        """fetch() includes MIME type in structural_hints.extra_metadata."""
        html_file = tmp_path / "test.html"
        html_file.write_text("<h1>Title</h1>", encoding="utf-8")

        adapter = RichFilesystemAdapter(tmp_path)

        with patch("context_library.adapters.filesystem_rich._convert_with_markitdown") as mock_md:
            mock_md.return_value = "# Title"
            results = list(adapter.fetch("unused"))

        assert len(results) == 1
        assert results[0].structural_hints.extra_metadata is not None
        assert "mime_type" in results[0].structural_hints.extra_metadata
        assert results[0].structural_hints.extra_metadata["mime_type"] == "text/html"

    def test_fetch_structural_hints_file_size(self, tmp_path):
        """fetch() populates file_size_bytes in structural_hints."""
        html_file = tmp_path / "test.html"
        content = "<h1>Title</h1>"
        html_file.write_text(content, encoding="utf-8")

        adapter = RichFilesystemAdapter(tmp_path)

        with patch("context_library.adapters.filesystem_rich._convert_with_markitdown") as mock_md:
            mock_md.return_value = "# Title"
            results = list(adapter.fetch("unused"))

        assert len(results) == 1
        assert results[0].structural_hints.file_size_bytes == len(content.encode("utf-8"))

    def test_fetch_structural_hints_modified_at(self, tmp_path):
        """fetch() populates modified_at in ISO 8601 format."""
        html_file = tmp_path / "test.html"
        html_file.write_text("<h1>Title</h1>", encoding="utf-8")

        adapter = RichFilesystemAdapter(tmp_path)

        with patch("context_library.adapters.filesystem_rich._convert_with_markitdown") as mock_md:
            mock_md.return_value = "# Title"
            results = list(adapter.fetch("unused"))

        assert len(results) == 1
        modified_at = results[0].structural_hints.modified_at
        assert modified_at is not None
        # Should be valid ISO 8601
        datetime.fromisoformat(modified_at)

    def test_fetch_structural_hints_directory_hierarchy(self, tmp_path):
        """fetch() includes directory hierarchy in extra_metadata."""
        (tmp_path / "level1").mkdir()
        (tmp_path / "level1" / "level2").mkdir()
        file_path = tmp_path / "level1" / "level2" / "test.html"
        file_path.write_text("<h1>Title</h1>", encoding="utf-8")

        adapter = RichFilesystemAdapter(tmp_path)

        with patch("context_library.adapters.filesystem_rich._convert_with_markitdown") as mock_md:
            mock_md.return_value = "# Title"
            results = list(adapter.fetch("unused"))

        assert len(results) == 1
        extra_metadata = results[0].structural_hints.extra_metadata
        assert "directory_hierarchy" in extra_metadata
        # Should have ["level1", "level2"] on Unix or similar on Windows
        hierarchy = extra_metadata["directory_hierarchy"]
        assert len(hierarchy) == 2
        assert "level1" in hierarchy
        assert "level2" in hierarchy

    def test_fetch_detects_headings(self, tmp_path):
        """fetch() detects headings in converted content."""
        html_file = tmp_path / "test.html"
        html_file.write_text("<h1>Title</h1>", encoding="utf-8")

        adapter = RichFilesystemAdapter(tmp_path)

        with patch("context_library.adapters.filesystem_rich._convert_with_markitdown") as mock_md:
            mock_md.return_value = "# Title\n\nContent"
            results = list(adapter.fetch("unused"))

        assert len(results) == 1
        assert results[0].structural_hints.has_headings is True

    def test_fetch_detects_lists(self, tmp_path):
        """fetch() detects lists in converted content."""
        html_file = tmp_path / "test.html"
        html_file.write_text("<ul><li>Item 1</li></ul>", encoding="utf-8")

        adapter = RichFilesystemAdapter(tmp_path)

        with patch("context_library.adapters.filesystem_rich._convert_with_markitdown") as mock_md:
            mock_md.return_value = "- Item 1\n- Item 2"
            results = list(adapter.fetch("unused"))

        assert len(results) == 1
        assert results[0].structural_hints.has_lists is True

    def test_fetch_detects_tables(self, tmp_path):
        """fetch() detects tables in converted content."""
        html_file = tmp_path / "test.html"
        html_file.write_text("<table><tr><td>Cell</td></tr></table>", encoding="utf-8")

        adapter = RichFilesystemAdapter(tmp_path)

        with patch("context_library.adapters.filesystem_rich._convert_with_markitdown") as mock_md:
            mock_md.return_value = "| Header 1 | Header 2 |\n|----------|----------|\n| Cell 1   | Cell 2   |"
            results = list(adapter.fetch("unused"))

        assert len(results) == 1
        assert results[0].structural_hints.has_tables is True

    def test_fetch_nonexistent_directory_raises_error(self, tmp_path):
        """fetch() raises FileNotFoundError for nonexistent directory."""
        nonexistent = tmp_path / "nonexistent"
        adapter = RichFilesystemAdapter(nonexistent)

        with pytest.raises(FileNotFoundError):
            list(adapter.fetch("unused"))

    def test_fetch_file_instead_of_directory_raises_error(self, tmp_path):
        """fetch() raises NotADirectoryError when given a file instead of directory."""
        file_path = tmp_path / "file.txt"
        file_path.write_text("Content", encoding="utf-8")
        adapter = RichFilesystemAdapter(file_path)

        with pytest.raises(NotADirectoryError):
            list(adapter.fetch("unused"))

    def test_fetch_handles_permission_error(self, tmp_path):
        """fetch() logs warning and continues on PermissionError."""
        file_path = tmp_path / "test.html"
        file_path.write_text("<h1>Title</h1>", encoding="utf-8")

        adapter = RichFilesystemAdapter(tmp_path)

        with patch("context_library.adapters.filesystem_rich._convert_with_markitdown") as mock_md:
            mock_md.side_effect = PermissionError("Access denied")
            with patch("context_library.adapters.filesystem_rich.logger") as mock_logger:
                results = list(adapter.fetch("unused"))

        assert len(results) == 0
        mock_logger.warning.assert_called()


class TestPushModeInitialization:
    """Tests for push-mode (FileSystemWatcher) initialization."""

    def test_pull_mode_does_not_create_watcher(self, tmp_path):
        """When poll_strategy=PULL (default), no watcher is created."""
        adapter = RichFilesystemAdapter(tmp_path, poll_strategy=PollStrategy.PULL)

        assert adapter._watcher is None

    @patch("context_library.adapters._watching.HAS_WATCHDOG", True)
    @patch("context_library.adapters._watching.HAS_WATCHFILES", False)
    def test_push_mode_creates_watcher(self, tmp_path):
        """When poll_strategy=PUSH, a FileSystemWatcher instance is created."""
        adapter = RichFilesystemAdapter(tmp_path, poll_strategy=PollStrategy.PUSH)

        assert adapter._watcher is not None

    @patch("context_library.adapters._watching.HAS_WATCHDOG", True)
    @patch("context_library.adapters._watching.HAS_WATCHFILES", False)
    def test_push_mode_watcher_configured_correctly(self, tmp_path):
        """Watcher is configured with correct path and callback."""
        adapter = RichFilesystemAdapter(tmp_path, poll_strategy=PollStrategy.PUSH)

        assert adapter._watcher is not None
        assert adapter._watcher._watch_path == tmp_path


class TestConversionFunctions:
    """Tests for file conversion utility functions."""

    def test_markitdown_conversion_returns_none_without_library(self):
        """_convert_with_markitdown returns None if MarkItDown is not available."""
        with patch("context_library.adapters.filesystem_rich.HAS_MARKITDOWN", False):
            result = _convert_with_markitdown(Path("dummy.pdf"))

        assert result is None

    def test_pandoc_conversion_handles_timeout(self, tmp_path):
        """_convert_with_pandoc returns None on timeout."""
        file_path = tmp_path / "test.tex"
        file_path.write_text(r"\documentclass{article}\begin{document}Hello\end{document}")

        with patch("context_library.adapters.filesystem_rich.subprocess.run") as mock_run:
            mock_run.side_effect = subprocess.TimeoutExpired("pandoc", 30)

            result = _convert_with_pandoc(file_path)

        assert result is None

    def test_pandoc_conversion_handles_missing_executable(self, tmp_path):
        """_convert_with_pandoc returns None when pandoc is not installed."""
        file_path = tmp_path / "test.tex"
        file_path.write_text(r"\documentclass{article}\begin{document}Hello\end{document}")

        with patch("context_library.adapters.filesystem_rich.subprocess.run") as mock_run:
            mock_run.side_effect = FileNotFoundError("pandoc not found")

            result = _convert_with_pandoc(file_path)

        assert result is None

    def test_pandoc_conversion_returns_none_on_nonzero_exit(self, tmp_path):
        """_convert_with_pandoc returns None if pandoc returns nonzero exit code."""
        file_path = tmp_path / "test.tex"
        file_path.write_text(r"\documentclass{article}\begin{document}Hello\end{document}")

        with patch("context_library.adapters.filesystem_rich.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=1, stdout="", stderr="Error")

            result = _convert_with_pandoc(file_path)

        assert result is None

    def test_pandoc_logs_stderr_on_nonzero_exit(self, tmp_path):
        """_convert_with_pandoc logs stderr when pandoc fails with nonzero exit."""
        file_path = tmp_path / "test.tex"
        file_path.write_text(r"\documentclass{article}\begin{document}Hello\end{document}")

        with patch("context_library.adapters.filesystem_rich.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=1, stdout="", stderr="Unsupported format")
            with patch("context_library.adapters.filesystem_rich.logger") as mock_logger:
                result = _convert_with_pandoc(file_path)

        assert result is None
        mock_logger.warning.assert_called_once()
        assert "Unsupported format" in str(mock_logger.warning.call_args)


class TestConversionErrorHandling:
    """Tests for error handling in conversion functions."""

    def test_markitdown_logs_traceback_on_error(self, tmp_path):
        """_convert_with_markitdown logs full traceback on conversion error."""
        file_path = tmp_path / "test.pdf"
        file_path.write_text("dummy pdf", encoding="utf-8")

        with patch("context_library.adapters.filesystem_rich.HAS_MARKITDOWN", True):
            with patch.object(
                __import__("context_library.adapters.filesystem_rich", fromlist=["MarkItDown"]),
                "MarkItDown",
                create=True,
            ) as mock_md_class:
                mock_md = MagicMock()
                mock_md_class.return_value = mock_md
                mock_md.convert.side_effect = ValueError("Corrupted PDF")
                with patch("context_library.adapters.filesystem_rich.logger") as mock_logger:
                    result = _convert_with_markitdown(file_path)

        assert result is None
        # Verify warning was called with exc_info=True
        mock_logger.warning.assert_called_once()
        call_kwargs = mock_logger.warning.call_args[1]
        assert call_kwargs.get("exc_info") is True
        assert "Corrupted PDF" in str(mock_logger.warning.call_args[0])

    def test_markitdown_catches_runtime_errors(self, tmp_path):
        """_convert_with_markitdown catches RuntimeError exceptions."""
        file_path = tmp_path / "test.pdf"
        file_path.write_text("dummy pdf", encoding="utf-8")

        with patch("context_library.adapters.filesystem_rich.HAS_MARKITDOWN", True):
            with patch.object(
                __import__("context_library.adapters.filesystem_rich", fromlist=["MarkItDown"]),
                "MarkItDown",
                create=True,
            ) as mock_md_class:
                mock_md = MagicMock()
                mock_md_class.return_value = mock_md
                mock_md.convert.side_effect = RuntimeError("Conversion timeout")
                with patch("context_library.adapters.filesystem_rich.logger") as mock_logger:
                    result = _convert_with_markitdown(file_path)

        assert result is None
        mock_logger.warning.assert_called_once()

    def test_markitdown_catches_os_errors(self, tmp_path):
        """_convert_with_markitdown catches OSError exceptions."""
        file_path = tmp_path / "test.pdf"
        file_path.write_text("dummy pdf", encoding="utf-8")

        with patch("context_library.adapters.filesystem_rich.HAS_MARKITDOWN", True):
            with patch.object(
                __import__("context_library.adapters.filesystem_rich", fromlist=["MarkItDown"]),
                "MarkItDown",
                create=True,
            ) as mock_md_class:
                mock_md = MagicMock()
                mock_md_class.return_value = mock_md
                mock_md.convert.side_effect = OSError("Disk full")
                with patch("context_library.adapters.filesystem_rich.logger") as mock_logger:
                    result = _convert_with_markitdown(file_path)

        assert result is None
        mock_logger.warning.assert_called_once()
