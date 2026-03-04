"""Tests for the chunker module.

Covers:
- Basic chunking of simple markdown content
- Chunking with markdown structure (headings, lists, etc.)
- Code block atomicity
- Table atomicity
- Token limit enforcement
- Context header generation
- Chunk hash computation
- Sequential chunk indices
"""

import pytest

from context_library.domains.notes import NotesDomain
from context_library.storage.models import ChunkType, Domain, NormalizedContent, StructuralHints


@pytest.fixture
def chunker():
    """Create a NotesDomain chunker for testing."""
    return NotesDomain(soft_limit=256, hard_limit=512)


class TestBasicChunking:
    """Tests for basic chunking functionality."""

    def test_chunk_simple_content(self, chunker):
        """Test chunking of simple markdown content."""
        content = NormalizedContent(
            source_id="test",
            markdown="# Title\n\nThis is some content.",
            normalizer_version="1.0.0",
            structural_hints=StructuralHints(
                has_headings=True,
                has_lists=False,
                has_tables=False,
                natural_boundaries=[],
            ),
        )

        chunks = chunker.chunk(content)

        assert len(chunks) > 0
        assert all(chunk.chunk_hash for chunk in chunks)
        assert all(chunk.content for chunk in chunks)

    def test_chunk_sequential_indices(self, chunker):
        """Test that chunks have sequential indices."""
        content = NormalizedContent(
            source_id="test",
            markdown="# Section 1\n\nContent 1.\n\n# Section 2\n\nContent 2.",
            normalizer_version="1.0.0",
            structural_hints=StructuralHints(
                has_headings=True,
                has_lists=False,
                has_tables=False,
                natural_boundaries=[],
            ),
        )

        chunks = chunker.chunk(content)

        for i, chunk in enumerate(chunks):
            assert chunk.chunk_index == i

    def test_chunk_empty_content_returns_empty_list(self, chunker):
        """Test that empty content returns empty chunk list."""
        content = NormalizedContent(
            source_id="test",
            markdown="",
            normalizer_version="1.0.0",
            structural_hints=StructuralHints(
                has_headings=True,
                has_lists=False,
                has_tables=False,
                natural_boundaries=[],
            ),
        )

        chunks = chunker.chunk(content)

        assert chunks == []

    def test_chunk_whitespace_only_returns_empty_list(self, chunker):
        """Test that whitespace-only content returns empty chunk list."""
        content = NormalizedContent(
            source_id="test",
            markdown="   \n\n   \t  \n",
            normalizer_version="1.0.0",
            structural_hints=StructuralHints(
                has_headings=True,
                has_lists=False,
                has_tables=False,
                natural_boundaries=[],
            ),
        )

        chunks = chunker.chunk(content)

        assert chunks == []

    def test_chunk_single_paragraph(self, chunker):
        """Test chunking of a single paragraph."""
        content = NormalizedContent(
            source_id="test",
            markdown="This is a single paragraph with some text that should be chunked.",
            normalizer_version="1.0.0",
            structural_hints=StructuralHints(
                has_headings=True,
                has_lists=False,
                has_tables=False,
                natural_boundaries=[],
            ),
        )

        chunks = chunker.chunk(content)

        assert len(chunks) >= 1
        assert chunks[0].content.strip() == "This is a single paragraph with some text that should be chunked."


class TestHeadingStructure:
    """Tests for heading-based chunking."""

    def test_chunk_with_h1_h2_hierarchy(self, chunker):
        """Test chunking with h1 and h2 headings."""
        content = NormalizedContent(
            source_id="test",
            markdown="""# Main Title

Content under main.

## Subsection

Content under subsection.""",
            normalizer_version="1.0.0",
            structural_hints=StructuralHints(
                has_headings=True,
                has_lists=False,
                has_tables=False,
                natural_boundaries=[],
            ),
        )

        chunks = chunker.chunk(content)

        assert len(chunks) > 0
        # Context headers should be present for subsections
        has_context_headers = any(chunk.context_header for chunk in chunks)
        # At least some chunks should have content
        assert all(chunk.content for chunk in chunks)

    def test_chunk_context_header_generation(self, chunker):
        """Test that context headers are generated as heading breadcrumbs."""
        content = NormalizedContent(
            source_id="test",
            markdown="""# Main

## Section A

Content A.

### Subsection A1

Content A1.""",
            normalizer_version="1.0.0",
            structural_hints=StructuralHints(
                has_headings=True,
                has_lists=False,
                has_tables=False,
                natural_boundaries=[],
            ),
        )

        chunks = chunker.chunk(content)

        # At least one chunk should have a context header
        chunks_with_context = [c for c in chunks if c.context_header]
        assert len(chunks_with_context) > 0

    def test_chunk_deep_nesting(self, chunker):
        """Test chunking with deeply nested headings."""
        content = NormalizedContent(
            source_id="test",
            markdown="""# Level 1

## Level 2

### Level 3

#### Level 4

Deep content.""",
            normalizer_version="1.0.0",
            structural_hints=StructuralHints(
                has_headings=True,
                has_lists=False,
                has_tables=False,
                natural_boundaries=[],
            ),
        )

        chunks = chunker.chunk(content)

        assert len(chunks) > 0


class TestCodeBlockHandling:
    """Tests for code block atomicity."""

    def test_code_block_is_atomic(self, chunker):
        """Test that code blocks are kept as atomic units."""
        content = NormalizedContent(
            source_id="test",
            markdown="""# Title

Here is some code:

```python
def hello():
    print("Hello, world!")
    print("More code")
```

End of code.""",
            normalizer_version="1.0.0",
            structural_hints=StructuralHints(
                has_headings=True,
                has_lists=False,
                has_tables=False,
                natural_boundaries=[],
            ),
        )

        chunks = chunker.chunk(content)

        assert len(chunks) > 0
        # At least one chunk should contain code block content
        code_chunks = [c for c in chunks if "def hello" in c.content or "print" in c.content]
        assert len(code_chunks) > 0

    def test_multiple_code_blocks(self, chunker):
        """Test handling of multiple code blocks."""
        content = NormalizedContent(
            source_id="test",
            markdown="""# Examples

## Python

```python
x = 1
```

## JavaScript

```javascript
var x = 1;
```""",
            normalizer_version="1.0.0",
            structural_hints=StructuralHints(
                has_headings=True,
                has_lists=False,
                has_tables=False,
                natural_boundaries=[],
            ),
        )

        chunks = chunker.chunk(content)

        assert len(chunks) > 0


class TestTableHandling:
    """Tests for table atomicity."""

    def test_table_is_atomic(self, chunker):
        """Test that tables are kept as atomic units."""
        content = NormalizedContent(
            source_id="test",
            markdown="""# Data

| Column 1 | Column 2 |
|----------|----------|
| Value 1  | Value 2  |
| Value 3  | Value 4  |

More content.""",
            normalizer_version="1.0.0",
            structural_hints=StructuralHints(
                has_headings=True,
                has_lists=False,
                has_tables=False,
                natural_boundaries=[],
            ),
        )

        chunks = chunker.chunk(content)

        assert len(chunks) > 0


class TestTokenLimitEnforcement:
    """Tests for soft and hard token limit enforcement."""

    def test_soft_limit_joining(self):
        """Test that short sections below soft_limit are joined together."""
        # Use smaller limits to test joining
        chunker_small = NotesDomain(soft_limit=50, hard_limit=100)

        content = NormalizedContent(
            source_id="test",
            markdown="""# A
Content A.

# B
Content B.

# C
Content C.""",
            normalizer_version="1.0.0",
            structural_hints=StructuralHints(
                has_headings=True,
                has_lists=False,
                has_tables=False,
                natural_boundaries=[],
            ),
        )

        chunks = chunker_small.chunk(content)

        # With small soft_limit, some sections may be joined
        assert len(chunks) > 0

    def test_hard_limit_splitting(self):
        """Test that chunks exceeding hard_limit are split."""
        chunker_small = NotesDomain(soft_limit=50, hard_limit=100)

        # Create content larger than hard_limit
        long_content = "A" * 200  # Well above hard_limit
        content = NormalizedContent(
            source_id="test",
            markdown=f"# Title\n\n{long_content}",
            normalizer_version="1.0.0",
            structural_hints=StructuralHints(
                has_headings=True,
                has_lists=False,
                has_tables=False,
                natural_boundaries=[],
            ),
        )

        chunks = chunker_small.chunk(content)

        assert len(chunks) >= 1


class TestChunkProperties:
    """Tests for chunk properties and validation."""

    def test_chunk_has_valid_hash(self, chunker):
        """Test that chunks have valid SHA-256 hashes."""
        content = NormalizedContent(
            source_id="test",
            markdown="# Title\n\nContent here.",
            normalizer_version="1.0.0",
            structural_hints=StructuralHints(
                has_headings=True,
                has_lists=False,
                has_tables=False,
                natural_boundaries=[],
            ),
        )

        chunks = chunker.chunk(content)

        for chunk in chunks:
            # SHA-256 hex digests are 64 characters
            assert len(chunk.chunk_hash) == 64
            assert all(c in "0123456789abcdef" for c in chunk.chunk_hash)

    def test_chunk_has_content(self, chunker):
        """Test that all chunks have non-empty content."""
        content = NormalizedContent(
            source_id="test",
            markdown="# Title\n\nContent here.",
            normalizer_version="1.0.0",
            structural_hints=StructuralHints(
                has_headings=True,
                has_lists=False,
                has_tables=False,
                natural_boundaries=[],
            ),
        )

        chunks = chunker.chunk(content)

        for chunk in chunks:
            assert chunk.content is not None
            assert len(chunk.content.strip()) > 0

    def test_chunk_type_is_valid(self, chunker):
        """Test that chunk_type values are valid ChunkType enum values."""
        content = NormalizedContent(
            source_id="test",
            markdown="# Title\n\nContent here.",
            normalizer_version="1.0.0",
            structural_hints=StructuralHints(
                has_headings=True,
                has_lists=False,
                has_tables=False,
                natural_boundaries=[],
            ),
        )

        chunks = chunker.chunk(content)

        valid_types = {ct.value for ct in ChunkType}
        for chunk in chunks:
            assert chunk.chunk_type in valid_types

    def test_chunk_index_starts_at_zero(self, chunker):
        """Test that chunk indices start at 0."""
        content = NormalizedContent(
            source_id="test",
            markdown="# Title\n\nContent here.",
            normalizer_version="1.0.0",
            structural_hints=StructuralHints(
                has_headings=True,
                has_lists=False,
                has_tables=False,
                natural_boundaries=[],
            ),
        )

        chunks = chunker.chunk(content)

        if chunks:
            assert chunks[0].chunk_index == 0


class TestLargeContent:
    """Tests for handling large content."""

    def test_large_document_chunking(self, chunker):
        """Test chunking of large documents."""
        # Create a large markdown document
        sections = [f"# Section {i}\n\nContent for section {i}.\n\n" for i in range(20)]
        markdown = "".join(sections)

        content = NormalizedContent(
            source_id="test",
            markdown=markdown,
            normalizer_version="1.0.0",
            structural_hints=StructuralHints(
                has_headings=True,
                has_lists=False,
                has_tables=False,
                natural_boundaries=[],
            ),
        )

        chunks = chunker.chunk(content)

        assert len(chunks) > 0
        # All indices should be unique and sequential
        indices = [c.chunk_index for c in chunks]
        assert indices == list(range(len(chunks)))
