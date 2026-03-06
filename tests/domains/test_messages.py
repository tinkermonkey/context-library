"""Tests for the messages domain."""

import pytest

from context_library.domains.messages import MessagesDomain, _strip_quoted_content
from context_library.storage.models import (
    Chunk,
    ChunkType,
    MessageMetadata,
    NormalizedContent,
    StructuralHints,
    compute_chunk_hash,
)


@pytest.fixture
def messages_domain():
    """Create a MessagesDomain instance with default limits."""
    return MessagesDomain(hard_limit=1024)


@pytest.fixture
def sample_message_metadata():
    """Create sample MessageMetadata for testing."""
    return MessageMetadata(
        thread_id="thread-001",
        message_id="msg-001",
        sender="alice@example.com",
        recipients=["bob@example.com"],
        timestamp="2025-01-15T10:30:00Z",
        in_reply_to=None,
        subject="Meeting Notes",
        is_thread_root=True,
    )


@pytest.fixture
def base_structural_hints():
    """Create base structural hints for testing."""
    return StructuralHints(
        has_headings=False,
        has_lists=False,
        has_tables=False,
        natural_boundaries=[],
    )


class TestMessagesDomainBasics:
    """Basic tests for MessagesDomain initialization and properties."""

    def test_initialization_with_defaults(self):
        """MessagesDomain initializes with default hard_limit."""
        domain = MessagesDomain()

        assert domain.hard_limit == 1024

    def test_initialization_with_custom_limit(self):
        """MessagesDomain initializes with custom hard_limit."""
        domain = MessagesDomain(hard_limit=512)

        assert domain.hard_limit == 512

    def test_chunk_returns_list_of_chunks(
        self, messages_domain, sample_message_metadata, base_structural_hints
    ):
        """chunk() returns a list of Chunk instances."""
        hints = StructuralHints(
            has_headings=False,
            has_lists=False,
            has_tables=False,
            natural_boundaries=[],
            extra_metadata=sample_message_metadata.model_dump(),
        )

        content = NormalizedContent(
            markdown="This is a simple message.",
            source_id="msg-001",
            structural_hints=hints,
            normalizer_version="1.0.0",
        )

        result = messages_domain.chunk(content)

        assert isinstance(result, list)
        assert all(isinstance(chunk, Chunk) for chunk in result)
        assert len(result) >= 1

    def test_chunk_raises_without_extra_metadata(
        self, messages_domain, base_structural_hints
    ):
        """chunk() raises ValueError if extra_metadata is missing."""
        content = NormalizedContent(
            markdown="Test message",
            source_id="msg-001",
            structural_hints=base_structural_hints,
            normalizer_version="1.0.0",
        )

        with pytest.raises(ValueError, match="extra_metadata"):
            messages_domain.chunk(content)


class TestSingleMessageChunk:
    """Tests for chunking single messages."""

    def test_single_short_message_creates_one_chunk(
        self, messages_domain, sample_message_metadata
    ):
        """A short message creates exactly one chunk."""
        hints = StructuralHints(
            has_headings=False,
            has_lists=False,
            has_tables=False,
            natural_boundaries=[],
            extra_metadata=sample_message_metadata.model_dump(),
        )

        content = NormalizedContent(
            markdown="This is a short message.",
            source_id="msg-001",
            structural_hints=hints,
            normalizer_version="1.0.0",
        )

        chunks = messages_domain.chunk(content)

        assert len(chunks) == 1
        assert chunks[0].content == "This is a short message."
        assert chunks[0].chunk_index == 0

    def test_chunk_has_correct_context_header(
        self, messages_domain, sample_message_metadata
    ):
        """chunk() sets context_header to '{subject} — {sender}'."""
        hints = StructuralHints(
            has_headings=False,
            has_lists=False,
            has_tables=False,
            natural_boundaries=[],
            extra_metadata=sample_message_metadata.model_dump(),
        )

        content = NormalizedContent(
            markdown="Message content.",
            source_id="msg-001",
            structural_hints=hints,
            normalizer_version="1.0.0",
        )

        chunks = messages_domain.chunk(content)

        assert chunks[0].context_header == "Meeting Notes — alice@example.com"

    def test_chunk_has_correct_context_header_with_no_subject(self, messages_domain):
        """chunk() handles missing subject by using '(no subject)'."""
        meta = MessageMetadata(
            thread_id="thread-001",
            message_id="msg-001",
            sender="alice@example.com",
            recipients=["bob@example.com"],
            timestamp="2025-01-15T10:30:00Z",
            in_reply_to=None,
            subject=None,
            is_thread_root=True,
        )

        hints = StructuralHints(
            has_headings=False,
            has_lists=False,
            has_tables=False,
            natural_boundaries=[],
            extra_metadata=meta.model_dump(),
        )

        content = NormalizedContent(
            markdown="Message content.",
            source_id="msg-001",
            structural_hints=hints,
            normalizer_version="1.0.0",
        )

        chunks = messages_domain.chunk(content)

        assert chunks[0].context_header == "(no subject) — alice@example.com"

    def test_chunk_has_domain_metadata(
        self, messages_domain, sample_message_metadata
    ):
        """chunk() populates domain_metadata with all MessageMetadata fields."""
        hints = StructuralHints(
            has_headings=False,
            has_lists=False,
            has_tables=False,
            natural_boundaries=[],
            extra_metadata=sample_message_metadata.model_dump(),
        )

        content = NormalizedContent(
            markdown="Message content.",
            source_id="msg-001",
            structural_hints=hints,
            normalizer_version="1.0.0",
        )

        chunks = messages_domain.chunk(content)

        assert chunks[0].domain_metadata is not None
        assert chunks[0].domain_metadata["thread_id"] == "thread-001"
        assert chunks[0].domain_metadata["message_id"] == "msg-001"
        assert chunks[0].domain_metadata["sender"] == "alice@example.com"
        assert chunks[0].domain_metadata["recipients"] == ("bob@example.com",)
        assert chunks[0].domain_metadata["timestamp"] == "2025-01-15T10:30:00Z"
        assert chunks[0].domain_metadata["in_reply_to"] is None
        assert chunks[0].domain_metadata["subject"] == "Meeting Notes"
        assert chunks[0].domain_metadata["is_thread_root"] is True

    def test_chunk_type_is_standard(self, messages_domain, sample_message_metadata):
        """All chunks have chunk_type = ChunkType.STANDARD."""
        hints = StructuralHints(
            has_headings=False,
            has_lists=False,
            has_tables=False,
            natural_boundaries=[],
            extra_metadata=sample_message_metadata.model_dump(),
        )

        content = NormalizedContent(
            markdown="Message content.",
            source_id="msg-001",
            structural_hints=hints,
            normalizer_version="1.0.0",
        )

        chunks = messages_domain.chunk(content)

        assert all(chunk.chunk_type == ChunkType.STANDARD for chunk in chunks)


class TestQuotedContentStripping:
    """Tests for stripping quoted reply content."""

    def test_strip_quoted_content_removes_quoted_lines(self):
        """_strip_quoted_content removes lines starting with '>'."""
        text = """This is my reply.

> On Mon, Jan 15, 2025 at 10:30 AM alice@example.com wrote:
> This is the original message.
> It spans multiple lines."""

        result = _strip_quoted_content(text)

        assert "This is my reply." in result
        assert ">" not in result
        assert "original message" not in result

    def test_strip_quoted_content_removes_attribution_lines(self):
        """_strip_quoted_content removes lines matching 'On ... wrote:'."""
        text = """My response.

On Mon, Jan 15, 2025 at 10:30 AM alice@example.com wrote:
> Original message here."""

        result = _strip_quoted_content(text)

        assert "My response." in result
        # The attribution line "On Mon, Jan 15, 2025 at 10:30 AM alice@example.com wrote:" should be gone
        assert "alice@example.com wrote:" not in result

    def test_strip_quoted_content_preserves_normal_text(self):
        """_strip_quoted_content preserves regular message content."""
        text = """Here is my full reply.

This paragraph explains my thoughts.
And this one adds more detail."""

        result = _strip_quoted_content(text)

        assert result == text

    def test_strip_quoted_content_preserves_wrote_in_prose(self):
        """_strip_quoted_content preserves 'wrote:' within prose context."""
        text = "I discussed what Einstein wrote: the theory was groundbreaking."

        result = _strip_quoted_content(text)

        # The line should be preserved because it doesn't match "On ... wrote:"
        assert "Einstein wrote:" in result

    def test_strip_quoted_content_handles_all_quoted_content(self):
        """_strip_quoted_content returns empty string when all content is quoted."""
        text = """> Original message line 1
> Original message line 2
> Original message line 3"""

        result = _strip_quoted_content(text)

        assert result == ""

    def test_chunk_with_quoted_content_strips_quotes(
        self, messages_domain, sample_message_metadata
    ):
        """chunk() removes quoted content from chunks."""
        hints = StructuralHints(
            has_headings=False,
            has_lists=False,
            has_tables=False,
            natural_boundaries=[],
            extra_metadata=sample_message_metadata.model_dump(),
        )

        markdown = """Here is my response.

> On Mon, Jan 15 alice wrote:
> This was the original message.
> It had useful information."""

        content = NormalizedContent(
            markdown=markdown,
            source_id="msg-001",
            structural_hints=hints,
            normalizer_version="1.0.0",
        )

        chunks = messages_domain.chunk(content)

        assert ">" not in chunks[0].content
        assert "original message" not in chunks[0].content
        assert "Here is my response." in chunks[0].content

    def test_chunk_with_only_quoted_content_returns_empty_list(
        self, messages_domain, sample_message_metadata
    ):
        """chunk() returns empty list when message is entirely quoted."""
        hints = StructuralHints(
            has_headings=False,
            has_lists=False,
            has_tables=False,
            natural_boundaries=[],
            extra_metadata=sample_message_metadata.model_dump(),
        )

        # Message with only quoted content (forwarded email with no new text)
        markdown = """> Original message from alice
> Second line of original
> Third line of original"""

        content = NormalizedContent(
            markdown=markdown,
            source_id="msg-001",
            structural_hints=hints,
            normalizer_version="1.0.0",
        )

        chunks = messages_domain.chunk(content)

        # Should return empty list, not a chunk with empty content
        assert chunks == []


class TestLongMessageSplitting:
    """Tests for splitting oversized messages."""

    def test_short_message_not_split(self, messages_domain, sample_message_metadata):
        """Messages under hard_limit are not split."""
        hints = StructuralHints(
            has_headings=False,
            has_lists=False,
            has_tables=False,
            natural_boundaries=[],
            extra_metadata=sample_message_metadata.model_dump(),
        )

        # Create a message with ~500 tokens (under 1024)
        short_message = " ".join(["word"] * 500)

        content = NormalizedContent(
            markdown=short_message,
            source_id="msg-001",
            structural_hints=hints,
            normalizer_version="1.0.0",
        )

        chunks = messages_domain.chunk(content)

        assert len(chunks) == 1

    def test_long_message_split_at_sentence_boundaries(
        self, messages_domain, sample_message_metadata
    ):
        """Messages exceeding hard_limit are split at sentence boundaries."""
        domain = MessagesDomain(hard_limit=30)  # Small limit for testing

        hints = StructuralHints(
            has_headings=False,
            has_lists=False,
            has_tables=False,
            natural_boundaries=[],
            extra_metadata=sample_message_metadata.model_dump(),
        )

        # Create a message with multiple sentences totaling ~70 tokens
        markdown = (
            "First sentence with some content and additional details here. "
            "Second sentence also with some content and more information. "
            "Third sentence continues the message with even more details. "
            "Fourth sentence adds more information to the discussion. "
            "Fifth sentence wraps up the thought about this topic."
        )

        content = NormalizedContent(
            markdown=markdown,
            source_id="msg-001",
            structural_hints=hints,
            normalizer_version="1.0.0",
        )

        chunks = domain.chunk(content)

        assert len(chunks) > 1
        # All chunks should have content and be under hard_limit
        for chunk in chunks:
            assert len(chunk.content.split()) <= 30

    def test_long_message_chunks_have_sequential_indices(
        self, messages_domain, sample_message_metadata
    ):
        """Split messages have sequential chunk_index values."""
        MessagesDomain(hard_limit=30)

        hints = StructuralHints(
            has_headings=False,
            has_lists=False,
            has_tables=False,
            natural_boundaries=[],
            extra_metadata=sample_message_metadata.model_dump(),
        )

        markdown = "word " * 100  # 100 words total

        content = NormalizedContent(
            markdown=markdown,
            source_id="msg-001",
            structural_hints=hints,
            normalizer_version="1.0.0",
        )

        chunks = messages_domain.chunk(content)

        for i, chunk in enumerate(chunks):
            assert chunk.chunk_index == i

    def test_oversized_sentence_split_at_word_boundaries(
        self, messages_domain, sample_message_metadata
    ):
        """Sentences exceeding hard_limit are split at word boundaries."""
        domain = MessagesDomain(hard_limit=20)

        hints = StructuralHints(
            has_headings=False,
            has_lists=False,
            has_tables=False,
            natural_boundaries=[],
            extra_metadata=sample_message_metadata.model_dump(),
        )

        # Create a single long sentence (40 words)
        markdown = "word " * 40

        content = NormalizedContent(
            markdown=markdown,
            source_id="msg-001",
            structural_hints=hints,
            normalizer_version="1.0.0",
        )

        chunks = domain.chunk(content)

        # Should be split into multiple chunks
        assert len(chunks) > 1
        # All chunks should be under hard_limit
        for chunk in chunks:
            assert len(chunk.content.split()) <= 20


class TestChunkHash:
    """Tests for chunk hash computation."""

    def test_chunk_hash_computed_from_content_only(
        self, messages_domain, sample_message_metadata
    ):
        """chunk_hash is computed from content, not context_header."""
        hints = StructuralHints(
            has_headings=False,
            has_lists=False,
            has_tables=False,
            natural_boundaries=[],
            extra_metadata=sample_message_metadata.model_dump(),
        )

        content = NormalizedContent(
            markdown="The message content.",
            source_id="msg-001",
            structural_hints=hints,
            normalizer_version="1.0.0",
        )

        chunks = messages_domain.chunk(content)

        # Compute expected hash from content only
        expected_hash = compute_chunk_hash("The message content.")

        assert chunks[0].chunk_hash == expected_hash

    def test_chunk_hash_same_regardless_of_context_header(
        self, messages_domain, sample_message_metadata
    ):
        """Changing context_header does not change chunk_hash."""
        hints1 = StructuralHints(
            has_headings=False,
            has_lists=False,
            has_tables=False,
            natural_boundaries=[],
            extra_metadata=sample_message_metadata.model_dump(),
        )

        meta2 = MessageMetadata(
            thread_id="thread-001",
            message_id="msg-001",
            sender="charlie@example.com",  # Different sender
            recipients=["bob@example.com"],
            timestamp="2025-01-15T10:30:00Z",
            in_reply_to=None,
            subject="Different Subject",  # Different subject
            is_thread_root=True,
        )

        hints2 = StructuralHints(
            has_headings=False,
            has_lists=False,
            has_tables=False,
            natural_boundaries=[],
            extra_metadata=meta2.model_dump(),
        )

        content1 = NormalizedContent(
            markdown="The message content.",
            source_id="msg-001",
            structural_hints=hints1,
            normalizer_version="1.0.0",
        )

        content2 = NormalizedContent(
            markdown="The message content.",
            source_id="msg-001",
            structural_hints=hints2,
            normalizer_version="1.0.0",
        )

        chunks1 = messages_domain.chunk(content1)
        chunks2 = messages_domain.chunk(content2)

        # Same content => same hash, even with different context headers
        assert chunks1[0].chunk_hash == chunks2[0].chunk_hash


class TestThreadMetadataPreservation:
    """Tests for preserving thread context in domain_metadata."""

    def test_chunk_preserves_thread_id(self, messages_domain, sample_message_metadata):
        """chunk() preserves thread_id in domain_metadata."""
        hints = StructuralHints(
            has_headings=False,
            has_lists=False,
            has_tables=False,
            natural_boundaries=[],
            extra_metadata=sample_message_metadata.model_dump(),
        )

        content = NormalizedContent(
            markdown="Message content.",
            source_id="msg-001",
            structural_hints=hints,
            normalizer_version="1.0.0",
        )

        chunks = messages_domain.chunk(content)

        assert chunks[0].domain_metadata["thread_id"] == "thread-001"

    def test_chunk_preserves_in_reply_to(self, messages_domain):
        """chunk() preserves in_reply_to for threaded messages."""
        meta = MessageMetadata(
            thread_id="thread-001",
            message_id="msg-002",
            sender="bob@example.com",
            recipients=["alice@example.com"],
            timestamp="2025-01-15T11:00:00Z",
            in_reply_to="msg-001",  # Reply to first message
            subject="Re: Meeting Notes",
            is_thread_root=False,
        )

        hints = StructuralHints(
            has_headings=False,
            has_lists=False,
            has_tables=False,
            natural_boundaries=[],
            extra_metadata=meta.model_dump(),
        )

        content = NormalizedContent(
            markdown="This is a reply.",
            source_id="msg-002",
            structural_hints=hints,
            normalizer_version="1.0.0",
        )

        chunks = messages_domain.chunk(content)

        assert chunks[0].domain_metadata["in_reply_to"] == "msg-001"
        assert chunks[0].domain_metadata["is_thread_root"] is False
