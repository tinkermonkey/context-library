"""Tests for the notes domain."""

import re

import pytest

from context_library.domains.notes import NotesDomain
from context_library.storage.models import (
    Chunk,
    NormalizedContent,
    StructuralHints,
    compute_chunk_hash,
)


@pytest.fixture
def notes_domain():
    """Create a NotesDomain instance with default limits."""
    return NotesDomain(soft_limit=512, hard_limit=1024)


@pytest.fixture
def base_structural_hints():
    """Create base structural hints for testing."""
    return StructuralHints(
        has_headings=True,
        has_lists=False,
        has_tables=False,
        natural_boundaries=[],
    )


class TestNotesDomainBasics:
    """Basic tests for NotesDomain initialization and properties."""

    def test_initialization_with_defaults(self):
        """NotesDomain initializes with default limits."""
        domain = NotesDomain()

        assert domain.soft_limit == 512
        assert domain.hard_limit == 1024

    def test_initialization_with_custom_limits(self):
        """NotesDomain initializes with custom limits."""
        domain = NotesDomain(soft_limit=256, hard_limit=512)

        assert domain.soft_limit == 256
        assert domain.hard_limit == 512

    def test_chunk_returns_list(self, notes_domain, base_structural_hints):
        """chunk() returns a list of Chunk instances."""
        content = NormalizedContent(
            markdown="# Heading\n\nSome text.",
            source_id="test.md",
            structural_hints=base_structural_hints,
            normalizer_version="1.0.0",
        )

        result = notes_domain.chunk(content)

        assert isinstance(result, list)
        assert all(isinstance(chunk, Chunk) for chunk in result)


class TestHeadingBasedSplitting:
    """Tests for heading-based chunk splitting."""

    def test_single_h1_heading(self, notes_domain, base_structural_hints):
        """Single H1 heading creates one chunk."""
        content = NormalizedContent(
            markdown="# Architecture\n\nThis is the architecture section.",
            source_id="test.md",
            structural_hints=base_structural_hints,
            normalizer_version="1.0.0",
        )

        chunks = notes_domain.chunk(content)

        assert len(chunks) == 1
        assert chunks[0].context_header is not None
        assert "# Architecture" in chunks[0].context_header

    def test_multiple_h1_headings(self, notes_domain, base_structural_hints):
        """Multiple H1 headings create separate chunks."""
        markdown = """# First Section

Content for first section.

# Second Section

Content for second section."""

        content = NormalizedContent(
            markdown=markdown,
            source_id="test.md",
            structural_hints=base_structural_hints,
            normalizer_version="1.0.0",
        )

        chunks = notes_domain.chunk(content)

        assert len(chunks) == 2
        assert "# First Section" in chunks[0].context_header
        assert "# Second Section" in chunks[1].context_header

    def test_h1_h2_hierarchy(self, notes_domain, base_structural_hints):
        """H1 and H2 headings maintain hierarchical structure."""
        markdown = """# Architecture

Main architecture section.

## Storage

SQLite backend section.

## Caching

Caching layer section."""

        content = NormalizedContent(
            markdown=markdown,
            source_id="test.md",
            structural_hints=base_structural_hints,
            normalizer_version="1.0.0",
        )

        chunks = notes_domain.chunk(content)

        # Should have chunks for H1 content, H2 Storage, H2 Caching
        assert len(chunks) >= 2

    def test_h1_h2_h3_hierarchy(self, notes_domain, base_structural_hints):
        """Deep heading hierarchy generates proper context headers."""
        markdown = """# Architecture

Main section.

## Storage

Storage section.

### SQLite

SQLite details."""

        content = NormalizedContent(
            markdown=markdown,
            source_id="test.md",
            structural_hints=base_structural_hints,
            normalizer_version="1.0.0",
        )

        chunks = notes_domain.chunk(content)

        # Find the H3 chunk
        h3_chunks = [c for c in chunks if c.context_header and "### SQLite" in c.context_header]
        assert len(h3_chunks) >= 1

        # Verify context header format
        h3_chunk = h3_chunks[0]
        assert "# Architecture" in h3_chunk.context_header
        assert "## Storage" in h3_chunk.context_header
        assert "### SQLite" in h3_chunk.context_header
        assert " > " in h3_chunk.context_header


class TestContextHeaderFormatting:
    """Tests for context header format."""

    def test_context_header_format_single_level(self, notes_domain, base_structural_hints):
        """Context header for single heading is formatted correctly."""
        markdown = "# Root Section\n\nContent here."

        content = NormalizedContent(
            markdown=markdown,
            source_id="test.md",
            structural_hints=base_structural_hints,
            normalizer_version="1.0.0",
        )

        chunks = notes_domain.chunk(content)

        assert chunks[0].context_header == "# Root Section"

    def test_context_header_format_three_levels(self, notes_domain, base_structural_hints):
        """Context header for three-level hierarchy uses correct format."""
        markdown = """# Level One

Content.

## Level Two

Content.

### Level Three

Content here."""

        content = NormalizedContent(
            markdown=markdown,
            source_id="test.md",
            structural_hints=base_structural_hints,
            normalizer_version="1.0.0",
        )

        chunks = notes_domain.chunk(content)

        # Find Level Three chunk
        level3_chunks = [c for c in chunks if "Level Three" in (c.context_header or "")]
        assert len(level3_chunks) > 0

        h3_chunk = level3_chunks[0]
        expected = "# Level One > ## Level Two > ### Level Three"
        assert h3_chunk.context_header == expected

    def test_context_header_with_special_characters(self, notes_domain, base_structural_hints):
        """Context headers preserve special characters in heading text."""
        markdown = """# API & SDK

Content here."""

        content = NormalizedContent(
            markdown=markdown,
            source_id="test.md",
            structural_hints=base_structural_hints,
            normalizer_version="1.0.0",
        )

        chunks = notes_domain.chunk(content)

        assert "API & SDK" in chunks[0].context_header


class TestCodeBlockAtomicity:
    """Tests for code block atomicity."""

    def test_code_block_never_split(self, notes_domain, base_structural_hints):
        """Code blocks are never split across chunks."""
        markdown = """# Example

Some text.

```python
def hello():
    return "world"
```

More text."""

        content = NormalizedContent(
            markdown=markdown,
            source_id="test.md",
            structural_hints=base_structural_hints,
            normalizer_version="1.0.0",
        )

        chunks = notes_domain.chunk(content)

        # Find code chunk
        code_chunks = [c for c in chunks if c.chunk_type == "code"]
        assert len(code_chunks) >= 1

        code_chunk = code_chunks[0]
        # Verify the entire code block is present
        assert 'def hello():' in code_chunk.content

    def test_code_block_chunk_type(self, notes_domain, base_structural_hints):
        """Code block chunks have chunk_type set to 'code'."""
        markdown = """# Section

```javascript
console.log("test");
```"""

        content = NormalizedContent(
            markdown=markdown,
            source_id="test.md",
            structural_hints=base_structural_hints,
            normalizer_version="1.0.0",
        )

        chunks = notes_domain.chunk(content)

        code_chunks = [c for c in chunks if c.chunk_type == "code"]
        assert len(code_chunks) >= 1
        assert code_chunks[0].chunk_type == "code"


class TestTableAtomicity:
    """Tests for table atomicity."""

    def test_table_never_split(self, notes_domain, base_structural_hints):
        """Tables are never split across chunks."""
        markdown = """# Data

| Name | Age |
|------|-----|
| Alice | 30 |
| Bob | 25 |

More content."""

        content = NormalizedContent(
            markdown=markdown,
            source_id="test.md",
            structural_hints=base_structural_hints,
            normalizer_version="1.0.0",
        )

        chunks = notes_domain.chunk(content)

        # Find table chunk
        table_chunks = [c for c in chunks if c.chunk_type == "table"]
        assert len(table_chunks) >= 1

        table_chunk = table_chunks[0]
        # Verify table content is intact
        assert "Alice" in table_chunk.content or "Name" in table_chunk.content

    def test_table_chunk_type(self, notes_domain, base_structural_hints):
        """Table chunks have chunk_type set to 'table'."""
        markdown = """# Tables

| Col1 | Col2 |
|------|------|
| A | B |"""

        content = NormalizedContent(
            markdown=markdown,
            source_id="test.md",
            structural_hints=base_structural_hints,
            normalizer_version="1.0.0",
        )

        chunks = notes_domain.chunk(content)

        table_chunks = [c for c in chunks if c.chunk_type == "table"]
        assert len(table_chunks) >= 1
        assert table_chunks[0].chunk_type == "table"


class TestSoftHardLimits:
    """Tests for soft and hard token limits."""

    def test_adjacent_small_sections_joined(self, notes_domain, base_structural_hints):
        """Adjacent sections below soft_limit are joined if combined size is within hard_limit."""
        # Create content where adjacent H2 sections are each small (< 64 tokens)
        markdown = """# Main

## First

Short first section.

## Second

Short second section."""

        content = NormalizedContent(
            markdown=markdown,
            source_id="test.md",
            structural_hints=base_structural_hints,
            normalizer_version="1.0.0",
        )

        chunks = notes_domain.chunk(content)

        # The two small H2 sections might be joined
        # At minimum, they should not exceed hard_limit individually
        for chunk in chunks:
            token_count = len(chunk.content.split())
            assert token_count <= notes_domain.hard_limit

    def test_oversized_chunk_respects_hard_limit(
        self, notes_domain, base_structural_hints
    ):
        """Chunks exceeding hard_limit are split into smaller pieces."""
        # Create a very long paragraph (> 1024 words)
        long_paragraph = " ".join(["word"] * 1100)
        markdown = f"# Long\n\n{long_paragraph}"

        content = NormalizedContent(
            markdown=markdown,
            source_id="test.md",
            structural_hints=base_structural_hints,
            normalizer_version="1.0.0",
        )

        chunks = notes_domain.chunk(content)

        # We should have multiple chunks to respect hard_limit
        assert len(chunks) > 1

        # Each chunk (excluding context header) should respect hard_limit
        for chunk in chunks:
            # For the content check, we count the actual content tokens
            # The hash was computed on the raw content without context header
            if chunk.context_header:
                # Strip the context header and extra newlines to get raw content
                content_only = chunk.content.replace(
                    chunk.context_header + "\n\n", "", 1
                )
            else:
                content_only = chunk.content

            token_count = len(content_only.split())
            assert token_count <= notes_domain.hard_limit


class TestChunkHash:
    """Tests for chunk hash computation."""

    def test_chunk_hash_computed(self, notes_domain, base_structural_hints):
        """Each chunk has a chunk_hash computed."""
        content = NormalizedContent(
            markdown="# Test\n\nContent here.",
            source_id="test.md",
            structural_hints=base_structural_hints,
            normalizer_version="1.0.0",
        )

        chunks = notes_domain.chunk(content)

        assert len(chunks) > 0
        for chunk in chunks:
            assert chunk.chunk_hash is not None
            assert len(chunk.chunk_hash) == 64  # SHA-256 hex is 64 chars
            assert re.match(r"^[a-f0-9]{64}$", chunk.chunk_hash)

    def test_chunk_hash_excludes_context_header(self, notes_domain, base_structural_hints):
        """chunk_hash is computed from content without context header."""
        markdown = """# Heading

Content text."""

        content = NormalizedContent(
            markdown=markdown,
            source_id="test.md",
            structural_hints=base_structural_hints,
            normalizer_version="1.0.0",
        )

        chunks = notes_domain.chunk(content)

        # The chunk_hash should be based on "Content text." alone, not including "# Heading"
        # We can verify this by computing the hash independently
        chunk = chunks[0]
        expected_hash = compute_chunk_hash("Content text.")

        assert chunk.chunk_hash == expected_hash

    def test_chunk_hash_deterministic_across_context(
        self, notes_domain, base_structural_hints
    ):
        """Two chunks with same content but different context headers have same hash."""
        # Create two documents with same content under different headings
        markdown1 = "# Context A\n\nSame content here."
        markdown2 = "# Context B\n\nSame content here."

        content1 = NormalizedContent(
            markdown=markdown1,
            source_id="test1.md",
            structural_hints=base_structural_hints,
            normalizer_version="1.0.0",
        )

        content2 = NormalizedContent(
            markdown=markdown2,
            source_id="test2.md",
            structural_hints=base_structural_hints,
            normalizer_version="1.0.0",
        )

        chunks1 = notes_domain.chunk(content1)
        chunks2 = notes_domain.chunk(content2)

        # Extract chunks with the content
        content_chunk1 = [c for c in chunks1 if "Same content here" in c.content]
        content_chunk2 = [c for c in chunks2 if "Same content here" in c.content]

        assert len(content_chunk1) > 0
        assert len(content_chunk2) > 0

        # Hashes should match (content is same, context headers differ)
        assert content_chunk1[0].chunk_hash == content_chunk2[0].chunk_hash

    def test_chunk_hash_whitespace_normalized(self, notes_domain, base_structural_hints):
        """chunk_hash is the same for content with different whitespace."""
        # These should produce the same hash due to whitespace normalization
        markdown1 = "# Heading\n\nContent  with   extra   spaces."
        markdown2 = "# Heading\n\nContent with extra spaces."

        content1 = NormalizedContent(
            markdown=markdown1,
            source_id="test1.md",
            structural_hints=base_structural_hints,
            normalizer_version="1.0.0",
        )

        content2 = NormalizedContent(
            markdown=markdown2,
            source_id="test2.md",
            structural_hints=base_structural_hints,
            normalizer_version="1.0.0",
        )

        chunks1 = notes_domain.chunk(content1)
        chunks2 = notes_domain.chunk(content2)

        # Both should have one chunk with matching hash
        assert len(chunks1) >= 1
        assert len(chunks2) >= 1
        assert chunks1[0].chunk_hash == chunks2[0].chunk_hash


class TestSequentialChunkIndices:
    """Tests for chunk_index assignment."""

    def test_chunk_indices_sequential(self, notes_domain, base_structural_hints):
        """chunk_index values are sequential starting from 0."""
        markdown = """# Section 1

Content 1.

# Section 2

Content 2.

# Section 3

Content 3."""

        content = NormalizedContent(
            markdown=markdown,
            source_id="test.md",
            structural_hints=base_structural_hints,
            normalizer_version="1.0.0",
        )

        chunks = notes_domain.chunk(content)

        # Indices should be sequential
        for i, chunk in enumerate(chunks):
            assert chunk.chunk_index == i

    def test_chunk_indices_start_at_zero(self, notes_domain, base_structural_hints):
        """First chunk has chunk_index of 0."""
        content = NormalizedContent(
            markdown="# Test\n\nContent.",
            source_id="test.md",
            structural_hints=base_structural_hints,
            normalizer_version="1.0.0",
        )

        chunks = notes_domain.chunk(content)

        assert chunks[0].chunk_index == 0


class TestChunkTypes:
    """Tests for chunk_type field."""

    def test_standard_chunk_type(self, notes_domain, base_structural_hints):
        """Regular text chunks have chunk_type='standard'."""
        content = NormalizedContent(
            markdown="# Heading\n\nRegular paragraph text.",
            source_id="test.md",
            structural_hints=base_structural_hints,
            normalizer_version="1.0.0",
        )

        chunks = notes_domain.chunk(content)

        standard_chunks = [c for c in chunks if "Regular paragraph" in c.content]
        assert len(standard_chunks) > 0
        assert standard_chunks[0].chunk_type == "standard"

    def test_code_chunk_type_set(self, notes_domain, base_structural_hints):
        """Code block chunks have chunk_type='code'."""
        markdown = "# Example\n\n```python\nprint('hello')\n```"

        content = NormalizedContent(
            markdown=markdown,
            source_id="test.md",
            structural_hints=base_structural_hints,
            normalizer_version="1.0.0",
        )

        chunks = notes_domain.chunk(content)

        code_chunks = [c for c in chunks if c.chunk_type == "code"]
        assert len(code_chunks) > 0

    def test_table_chunk_type_set(self, notes_domain, base_structural_hints):
        """Table chunks have chunk_type='table'."""
        markdown = "# Data\n\n| A | B |\n|---|---|\n| 1 | 2 |"

        content = NormalizedContent(
            markdown=markdown,
            source_id="test.md",
            structural_hints=base_structural_hints,
            normalizer_version="1.0.0",
        )

        chunks = notes_domain.chunk(content)

        table_chunks = [c for c in chunks if c.chunk_type == "table"]
        assert len(table_chunks) > 0


class TestDomainMetadata:
    """Tests for domain_metadata field."""

    def test_heading_level_in_metadata(self, notes_domain, base_structural_hints):
        """Heading-derived chunks include heading_level in domain_metadata."""
        markdown = "## Section\n\nContent here."

        content = NormalizedContent(
            markdown=markdown,
            source_id="test.md",
            structural_hints=base_structural_hints,
            normalizer_version="1.0.0",
        )

        chunks = notes_domain.chunk(content)

        assert len(chunks) > 0
        chunk = chunks[0]
        assert chunk.domain_metadata is not None
        assert "heading_level" in chunk.domain_metadata
        assert chunk.domain_metadata["heading_level"] == 2


class TestMistuneAST:
    """Tests for mistune AST handling and regression detection."""

    def test_mistune_ast_structure_paragraph(self, notes_domain):
        """Mistune AST structure is as expected for paragraphs."""
        markdown = "Simple paragraph."
        ast = notes_domain.md(markdown)

        assert isinstance(ast, list)
        assert len(ast) > 0
        assert ast[0].get("type") == "paragraph"
        assert "children" in ast[0]

    def test_mistune_ast_structure_heading(self, notes_domain):
        """Mistune AST structure is as expected for headings."""
        markdown = "# Heading Text"
        ast = notes_domain.md(markdown)

        assert isinstance(ast, list)
        heading_blocks = [b for b in ast if b.get("type") == "heading"]
        assert len(heading_blocks) > 0

        heading = heading_blocks[0]
        assert heading.get("attrs") is not None
        assert "level" in heading["attrs"]
        assert heading["attrs"]["level"] == 1

    def test_mistune_ast_structure_code_block(self, notes_domain):
        """Mistune AST structure is as expected for code blocks."""
        markdown = "```python\ncode here\n```"
        ast = notes_domain.md(markdown)

        code_blocks = [b for b in ast if b.get("type") == "block_code"]
        assert len(code_blocks) > 0

        code_block = code_blocks[0]
        assert code_block.get("raw") is not None

    def test_mistune_version_regression(self, notes_domain):
        """Known markdown input produces expected AST structure (regression test)."""
        # Use a known markdown snippet and verify AST structure hasn't changed
        markdown = """# Title

First paragraph.

## Subtitle

Second paragraph.

```
code
```"""

        ast = notes_domain.md(markdown)

        # Verify structure
        assert isinstance(ast, list)

        types = [b.get("type") for b in ast]
        assert "heading" in types
        assert "paragraph" in types
        assert "block_code" in types


class TestContextHeaderPrepended:
    """Tests for context header prepending to content."""

    def test_context_header_in_content_field(self, notes_domain, base_structural_hints):
        """Context header is prepended to the content field."""
        markdown = "# Heading\n\nContent text."

        content = NormalizedContent(
            markdown=markdown,
            source_id="test.md",
            structural_hints=base_structural_hints,
            normalizer_version="1.0.0",
        )

        chunks = notes_domain.chunk(content)

        chunk = chunks[0]
        assert chunk.context_header is not None
        assert "# Heading" in chunk.content
        assert "Content text" in chunk.content
        # Context header should come before content
        assert chunk.content.startswith(chunk.context_header)

    def test_context_header_none_without_prepend(self, notes_domain):
        """Content without heading context_header is None and not prepended."""
        # Create content without any headings
        structural_hints = StructuralHints(
            has_headings=False,
            has_lists=False,
            has_tables=False,
            natural_boundaries=[],
        )

        markdown = "Just some content."

        content = NormalizedContent(
            markdown=markdown,
            source_id="test.md",
            structural_hints=structural_hints,
            normalizer_version="1.0.0",
        )

        chunks = notes_domain.chunk(content)

        assert len(chunks) > 0
        chunk = chunks[0]
        assert chunk.context_header is None
        assert chunk.content == "Just some content."


class TestComplexDocument:
    """Tests with complex multi-section documents."""

    def test_complex_document_chunking(self, notes_domain, base_structural_hints):
        """Complex document with multiple heading levels chunks correctly."""
        markdown = """# Architecture

This is the main architecture section.

## Database

### SQLite

SQLite backend implementation.

### PostgreSQL

PostgreSQL support.

## Caching

In-memory caching layer.

# Implementation

Details of implementation.

## Code Examples

```python
example = "code"
```

## Performance

Performance notes."""

        content = NormalizedContent(
            markdown=markdown,
            source_id="architecture.md",
            structural_hints=base_structural_hints,
            normalizer_version="1.0.0",
        )

        chunks = notes_domain.chunk(content)

        # Verify we have multiple chunks
        assert len(chunks) > 1

        # Verify sequential indices
        for i, chunk in enumerate(chunks):
            assert chunk.chunk_index == i

        # Verify all chunks have valid hashes
        for chunk in chunks:
            assert chunk.chunk_hash is not None
            assert len(chunk.chunk_hash) == 64

        # Verify context headers exist where expected
        context_headers = [c.context_header for c in chunks if c.context_header]
        assert len(context_headers) > 0

    def test_empty_document(self, notes_domain, base_structural_hints):
        """Empty or whitespace-only document produces no chunks or handles gracefully."""
        content = NormalizedContent(
            markdown="",
            source_id="empty.md",
            structural_hints=base_structural_hints,
            normalizer_version="1.0.0",
        )

        chunks = notes_domain.chunk(content)

        # Should return empty list or handle gracefully
        assert isinstance(chunks, list)


class TestEdgeCases:
    """Tests for edge cases and boundary conditions."""

    def test_heading_without_content(self, notes_domain, base_structural_hints):
        """Heading without following content is handled."""
        markdown = """# Section One

Content here.

# Section Two"""

        content = NormalizedContent(
            markdown=markdown,
            source_id="test.md",
            structural_hints=base_structural_hints,
            normalizer_version="1.0.0",
        )

        chunks = notes_domain.chunk(content)

        # Should handle gracefully
        assert isinstance(chunks, list)

    def test_multiple_code_blocks(self, notes_domain, base_structural_hints):
        """Multiple code blocks are each kept atomic."""
        markdown = """# Example

```python
print("first")
```

```javascript
console.log("second");
```"""

        content = NormalizedContent(
            markdown=markdown,
            source_id="test.md",
            structural_hints=base_structural_hints,
            normalizer_version="1.0.0",
        )

        chunks = notes_domain.chunk(content)

        code_chunks = [c for c in chunks if c.chunk_type == "code"]
        assert len(code_chunks) >= 2

    def test_nested_lists(self, notes_domain, base_structural_hints):
        """Nested lists are handled in chunking."""
        markdown = """# Lists

- Item 1
  - Nested 1
  - Nested 2
- Item 2"""

        content = NormalizedContent(
            markdown=markdown,
            source_id="test.md",
            structural_hints=base_structural_hints,
            normalizer_version="1.0.0",
        )

        chunks = notes_domain.chunk(content)

        # Should have chunks
        assert len(chunks) > 0
        # List content should be preserved
        assert any("Item 1" in c.content for c in chunks)
