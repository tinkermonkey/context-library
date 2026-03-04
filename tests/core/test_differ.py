"""Tests for the differ module."""


from context_library.core.differ import Differ


class TestDifferFirstIngest:
    """Test first ingest scenario (prev_markdown is None)."""

    def test_first_ingest_returns_all_added(self):
        """First ingest should return all curr_chunk_hashes as added."""
        differ = Differ()
        chunk_hashes = {
            "abc123def456abc123def456abc123def456abc123def456abc123def456abc0",
            "1234567890abcdef1234567890abcdef1234567890abcdef1234567890abcdef",
        }

        result = differ.diff(
            prev_markdown=None,
            curr_markdown="# Document\n\nContent here.",
            prev_chunk_hashes=None,
            curr_chunk_hashes=chunk_hashes,
        )

        assert result.changed is True
        assert result.added_hashes == chunk_hashes
        assert result.removed_hashes == set()
        assert result.unchanged_hashes == set()
        assert result.prev_hash is None
        assert result.curr_hash is not None
        assert len(result.curr_hash) == 64  # SHA-256 hex digest length


class TestDifferUnchangedDocument:
    """Test unchanged document detection."""

    def test_identical_content_returns_unchanged(self):
        """Identical content (after normalization) should return changed=False."""
        differ = Differ()
        markdown = "# Document\n\nContent here."
        chunk_hashes = {
            "abc123def456abc123def456abc123def456abc123def456abc123def456abc0",
        }

        result = differ.diff(
            prev_markdown=markdown,
            curr_markdown=markdown,
            prev_chunk_hashes=chunk_hashes,
            curr_chunk_hashes=chunk_hashes,
        )

        assert result.changed is False
        assert result.added_hashes == set()
        assert result.removed_hashes == set()
        assert result.unchanged_hashes == chunk_hashes
        assert result.prev_hash == result.curr_hash

    def test_whitespace_only_change_treated_as_unchanged(self):
        """Trailing whitespace changes should be ignored."""
        differ = Differ()
        prev_markdown = "# Document\n\nContent here."
        # Add trailing spaces (but preserve blank line structure)
        curr_markdown = "# Document  \n\nContent here.  "
        chunk_hashes = {
            "abc123def456abc123def456abc123def456abc123def456abc123def456abc0",
        }

        result = differ.diff(
            prev_markdown=prev_markdown,
            curr_markdown=curr_markdown,
            prev_chunk_hashes=chunk_hashes,
            curr_chunk_hashes=chunk_hashes,
        )

        assert result.changed is False
        assert result.unchanged_hashes == chunk_hashes

    def test_normalize_strips_leading_trailing_whitespace(self):
        """Text with leading/trailing whitespace should normalize correctly."""
        differ = Differ()
        prev_markdown = "   # Document\n\nContent   "
        curr_markdown = "# Document\n\nContent"
        chunk_hashes = {
            "abc123def456abc123def456abc123def456abc123def456abc123def456abc0",
        }

        result = differ.diff(
            prev_markdown=prev_markdown,
            curr_markdown=curr_markdown,
            prev_chunk_hashes=chunk_hashes,
            curr_chunk_hashes=chunk_hashes,
        )

        assert result.changed is False


class TestDifferModifiedChunk:
    """Test modified chunk detection."""

    def test_modified_chunk_appears_in_added_and_removed(self):
        """Modified chunk should appear in both added and removed hashes."""
        differ = Differ()
        old_hash = "abc123def456abc123def456abc123def456abc123def456abc123def456abc0"
        new_hash = "1234567890abcdef1234567890abcdef1234567890abcdef1234567890abcdef"
        unchanged_hash = "1111111111111111111111111111111111111111111111111111111111111110"

        prev_markdown = "# Document\n\nOld content."
        curr_markdown = "# Document\n\nNew content."

        prev_chunk_hashes = {old_hash, unchanged_hash}
        curr_chunk_hashes = {new_hash, unchanged_hash}

        result = differ.diff(
            prev_markdown=prev_markdown,
            curr_markdown=curr_markdown,
            prev_chunk_hashes=prev_chunk_hashes,
            curr_chunk_hashes=curr_chunk_hashes,
        )

        assert result.changed is True
        assert result.added_hashes == {new_hash}
        assert result.removed_hashes == {old_hash}
        assert result.unchanged_hashes == {unchanged_hash}


class TestDifferAddedChunk:
    """Test added chunk detection."""

    def test_new_chunk_appears_in_added_only(self):
        """New chunk should appear in added_hashes only."""
        differ = Differ()
        old_hash = "abc123def456abc123def456abc123def456abc123def456abc123def456abc0"
        new_hash = "1234567890abcdef1234567890abcdef1234567890abcdef1234567890abcdef"

        prev_markdown = "# Document\n\nContent."
        curr_markdown = "# Document\n\nContent.\n\nMore content."

        prev_chunk_hashes = {old_hash}
        curr_chunk_hashes = {old_hash, new_hash}

        result = differ.diff(
            prev_markdown=prev_markdown,
            curr_markdown=curr_markdown,
            prev_chunk_hashes=prev_chunk_hashes,
            curr_chunk_hashes=curr_chunk_hashes,
        )

        assert result.changed is True
        assert result.added_hashes == {new_hash}
        assert result.removed_hashes == set()
        assert result.unchanged_hashes == {old_hash}


class TestDifferRemovedChunk:
    """Test removed chunk detection."""

    def test_removed_chunk_appears_in_removed_only(self):
        """Removed chunk should appear in removed_hashes only."""
        differ = Differ()
        old_hash = "abc123def456abc123def456abc123def456abc123def456abc123def456abc0"
        remaining_hash = "fedcba0987654321fedcba0987654321fedcba0987654321fedcba0987654321"

        prev_markdown = "# Document\n\nContent.\n\nExtra content."
        curr_markdown = "# Document\n\nContent."

        prev_chunk_hashes = {old_hash, remaining_hash}
        curr_chunk_hashes = {remaining_hash}

        result = differ.diff(
            prev_markdown=prev_markdown,
            curr_markdown=curr_markdown,
            prev_chunk_hashes=prev_chunk_hashes,
            curr_chunk_hashes=curr_chunk_hashes,
        )

        assert result.changed is True
        assert result.added_hashes == set()
        assert result.removed_hashes == {old_hash}
        assert result.unchanged_hashes == {remaining_hash}


class TestDifferWhitespaceNormalization:
    """Test whitespace normalization behavior."""

    def test_normalize_collapses_spaces_and_tabs(self):
        """Multiple spaces and tabs should collapse to single space."""
        differ = Differ()
        prev = "hello    world\t\ttest"
        curr = "hello world test"
        chunk_hashes = {
            "abc123def456abc123def456abc123def456abc123def456abc123def456abc0",
        }

        result = differ.diff(
            prev_markdown=prev,
            curr_markdown=curr,
            prev_chunk_hashes=chunk_hashes,
            curr_chunk_hashes=chunk_hashes,
        )

        assert result.changed is False

    def test_normalize_strips_line_trailing_whitespace(self):
        """Trailing whitespace on lines should be stripped."""
        differ = Differ()
        prev = "line one   \nline two\t"
        curr = "line one\nline two"
        chunk_hashes = {
            "abc123def456abc123def456abc123def456abc123def456abc123def456abc0",
        }

        result = differ.diff(
            prev_markdown=prev,
            curr_markdown=curr,
            prev_chunk_hashes=chunk_hashes,
            curr_chunk_hashes=chunk_hashes,
        )

        assert result.changed is False

    def test_normalize_handles_blank_lines(self):
        """Blank lines with trailing whitespace should be normalized."""
        differ = Differ()
        prev = "line one\n  \nline two"
        curr = "line one\n\nline two"
        chunk_hashes = {
            "abc123def456abc123def456abc123def456abc123def456abc123def456abc0",
        }

        result = differ.diff(
            prev_markdown=prev,
            curr_markdown=curr,
            prev_chunk_hashes=chunk_hashes,
            curr_chunk_hashes=chunk_hashes,
        )

        assert result.changed is False


class TestDifferHashConsistency:
    """Test hash computation consistency."""

    def test_prev_and_curr_hash_are_sha256(self):
        """Hashes should be valid SHA-256 hex digests."""
        differ = Differ()
        result = differ.diff(
            prev_markdown="content",
            curr_markdown="content",
            prev_chunk_hashes={"abc123def456abc123def456abc123def456abc123def456abc123def456abc0"},
            curr_chunk_hashes={"abc123def456abc123def456abc123def456abc123def456abc123def456abc0"},
        )

        # SHA-256 hex digests are 64 characters
        assert len(result.prev_hash) == 64
        assert len(result.curr_hash) == 64
        assert all(c in "0123456789abcdef" for c in result.prev_hash)
        assert all(c in "0123456789abcdef" for c in result.curr_hash)

    def test_different_content_produces_different_hashes(self):
        """Different content should produce different hashes."""
        differ = Differ()
        result = differ.diff(
            prev_markdown="content one",
            curr_markdown="content two",
            prev_chunk_hashes={"abc123def456abc123def456abc123def456abc123def456abc123def456abc0"},
            curr_chunk_hashes={"1234567890abcdef1234567890abcdef1234567890abcdef1234567890abcdef"},
        )

        assert result.prev_hash != result.curr_hash


class TestDifferEdgeCases:
    """Test edge cases and boundary conditions."""

    def test_empty_chunk_hashes(self):
        """First ingest with empty chunk set should work."""
        differ = Differ()
        result = differ.diff(
            prev_markdown=None,
            curr_markdown="content",
            prev_chunk_hashes=None,
            curr_chunk_hashes=set(),
        )

        assert result.changed is True
        assert result.added_hashes == set()
        assert result.removed_hashes == set()

    def test_large_content(self):
        """Large document content should be handled correctly."""
        differ = Differ()
        large_content = "# Header\n\n" + "Content line.\n" * 10000
        chunk_hashes = {
            "abc123def456abc123def456abc123def456abc123def456abc123def456abc0",
        }

        result = differ.diff(
            prev_markdown=large_content,
            curr_markdown=large_content,
            prev_chunk_hashes=chunk_hashes,
            curr_chunk_hashes=chunk_hashes,
        )

        assert result.changed is False

    def test_many_chunks(self):
        """Large number of chunks should be handled correctly."""
        differ = Differ()
        # Create 1000 unique hashes
        chunk_hashes = {
            f"{i:064x}" for i in range(1000)
        }
        # Remove 100 hashes for removed chunks
        prev_chunk_hashes = chunk_hashes | {
            f"{i+1000:064x}" for i in range(100)
        }

        result = differ.diff(
            prev_markdown="content one",
            curr_markdown="content two",
            prev_chunk_hashes=prev_chunk_hashes,
            curr_chunk_hashes=chunk_hashes,
        )

        assert result.changed is True
        assert len(result.unchanged_hashes) == 1000
        assert len(result.removed_hashes) == 100
        assert len(result.added_hashes) == 0
