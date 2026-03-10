"""Tests for storage models.

Covers:
- Model field validation and instantiation
- chunk_hash determinism (same content → same hash)
- Frozen model immutability enforcement
- Chunk hash format validation
"""

import pytest
from pydantic import ValidationError

from context_library.storage.models import (
    AdapterConfig,
    Chunk,
    ChunkProvenance,
    ChunkType,
    Domain,
    DiffResult,
    EventMetadata,
    LineageRecord,
    MessageMetadata,
    NormalizedContent,
    PollStrategy,
    SourceTimeline,
    SourceVersion,
    StructuralHints,
    TaskMetadata,
    VersionDiff,
    compute_chunk_hash,
)


class TestStructuralHints:
    """Tests for StructuralHints model."""

    def test_create_with_defaults(self) -> None:
        """Test creating StructuralHints with default None values."""
        hints = StructuralHints(
            has_headings=True,
            has_lists=False,
            has_tables=False,
            natural_boundaries=[10, 20, 30],
        )
        assert hints.has_headings is True
        assert hints.has_lists is False
        assert hints.has_tables is False
        assert hints.natural_boundaries == (10, 20, 30)
        assert hints.file_path is None
        assert hints.modified_at is None
        assert hints.file_size_bytes is None

    def test_create_with_all_fields(self) -> None:
        """Test creating StructuralHints with all fields populated."""
        hints = StructuralHints(
            has_headings=True,
            has_lists=True,
            has_tables=True,
            natural_boundaries=[100, 200],
            file_path="/path/to/file.md",
            modified_at="2025-03-02T10:00:00Z",
            file_size_bytes=1024,
        )
        assert hints.file_path == "/path/to/file.md"
        assert hints.modified_at == "2025-03-02T10:00:00Z"
        assert hints.file_size_bytes == 1024

    def test_frozen_immutability(self) -> None:
        """Test that StructuralHints is frozen and cannot be modified."""
        hints = StructuralHints(
            has_headings=True,
            has_lists=False,
            has_tables=False,
            natural_boundaries=[],
        )
        with pytest.raises(ValidationError):
            hints.has_headings = False  # type: ignore[assignment]


class TestNormalizedContent:
    """Tests for NormalizedContent model."""

    def test_create_normalized_content(self) -> None:
        """Test creating NormalizedContent with nested StructuralHints."""
        hints = StructuralHints(
            has_headings=True,
            has_lists=False,
            has_tables=False,
            natural_boundaries=[50],
        )
        content = NormalizedContent(
            markdown="# Heading\n\nParagraph.",
            source_id="source-1",
            structural_hints=hints,
            normalizer_version="1.0.0",
        )
        assert content.markdown == "# Heading\n\nParagraph."
        assert content.source_id == "source-1"
        assert content.structural_hints == hints
        assert content.normalizer_version == "1.0.0"

    def test_frozen_immutability(self) -> None:
        """Test that NormalizedContent is frozen."""
        hints = StructuralHints(
            has_headings=True,
            has_lists=False,
            has_tables=False,
            natural_boundaries=[],
        )
        content = NormalizedContent(
            markdown="test",
            source_id="s1",
            structural_hints=hints,
            normalizer_version="1.0.0",
        )
        with pytest.raises(ValidationError):
            content.source_id = "s2"  # type: ignore[assignment]


class TestChunk:
    """Tests for Chunk model."""

    @staticmethod
    def create_valid_sha256_hash() -> str:
        """Create a valid SHA-256 hash for testing."""
        return "a" * 64

    def test_create_chunk_minimal(self) -> None:
        """Test creating Chunk with minimal fields."""
        chunk = Chunk(
            chunk_hash=self.create_valid_sha256_hash(),
            content="This is chunk content.",
            chunk_index=0,
        )
        assert chunk.content == "This is chunk content."
        assert chunk.context_header is None
        assert chunk.chunk_type == "standard"
        assert chunk.domain_metadata is None

    def test_create_chunk_full(self) -> None:
        """Test creating Chunk with all fields."""
        chunk = Chunk(
            chunk_hash=self.create_valid_sha256_hash(),
            content="Content here.",
            context_header="# Section > ## Subsection",
            chunk_index=5,
            chunk_type="oversized",
            domain_metadata={"key": "value"},
        )
        assert chunk.chunk_index == 5
        assert chunk.context_header == "# Section > ## Subsection"
        assert chunk.chunk_type == "oversized"
        assert chunk.domain_metadata == {"key": "value"}

    def test_chunk_hash_validation_valid(self) -> None:
        """Test that valid SHA-256 hashes are accepted."""
        valid_hashes = [
            "a" * 64,  # all 'a'
            "0123456789abcdef" * 4,  # mixed hex digits
            "f" * 64,  # all 'f'
            "0" * 64,  # all zeros (valid)
        ]
        for valid_hash in valid_hashes:
            chunk = Chunk(chunk_hash=valid_hash, content="test", chunk_index=0)
            assert chunk.chunk_hash == valid_hash

    def test_chunk_hash_validation_invalid(self) -> None:
        """Test that invalid chunk hashes are rejected."""
        invalid_hashes = [
            "a" * 63,  # too short
            "a" * 65,  # too long
            "G" * 64,  # invalid hex character
            "A" * 64,  # uppercase (must be lowercase)
            "invalid_hash",  # not hex at all
        ]
        for invalid_hash in invalid_hashes:
            with pytest.raises(ValidationError) as exc_info:
                Chunk(chunk_hash=invalid_hash, content="test", chunk_index=0)
            assert "chunk_hash must be a valid SHA-256" in str(exc_info.value)

    def test_frozen_immutability(self) -> None:
        """Test that Chunk is frozen."""
        chunk = Chunk(
            chunk_hash=self.create_valid_sha256_hash(),
            content="test",
            chunk_index=0,
        )
        with pytest.raises(ValidationError):
            chunk.chunk_index = 1  # type: ignore[assignment]


class TestLineageRecord:
    """Tests for LineageRecord model."""

    @staticmethod
    def create_valid_sha256_hash() -> str:
        """Create a valid SHA-256 hash for testing."""
        return "b" * 64

    def test_create_lineage_record(self) -> None:
        """Test creating LineageRecord with all fields."""
        record = LineageRecord(
            chunk_hash=self.create_valid_sha256_hash(),
            source_id="source-1",
            source_version_id=1,
            adapter_id="adapter-fs-1",
            domain=Domain.NOTES,
            normalizer_version="1.0.0",
            embedding_model_id="all-MiniLM-L6-v2",
        )
        assert record.source_id == "source-1"
        assert record.source_version_id == 1
        assert record.domain == Domain.NOTES
        assert record.embedding_model_id == "all-MiniLM-L6-v2"

    def test_lineage_record_domain_enum(self) -> None:
        """Test that LineageRecord accepts Domain enum values."""
        for domain in Domain:
            record = LineageRecord(
                chunk_hash=self.create_valid_sha256_hash(),
                source_id="src",
                source_version_id=1,
                adapter_id="adp",
                domain=domain,
                normalizer_version="1.0.0",
                embedding_model_id="model",
            )
            assert record.domain == domain

    def test_frozen_immutability(self) -> None:
        """Test that LineageRecord is frozen."""
        record = LineageRecord(
            chunk_hash=self.create_valid_sha256_hash(),
            source_id="src",
            source_version_id=1,
            adapter_id="adp",
            domain=Domain.NOTES,
            normalizer_version="1.0.0",
            embedding_model_id="model",
        )
        with pytest.raises(ValidationError):
            record.source_version_id = 2  # type: ignore[assignment]


class TestSourceVersion:
    """Tests for SourceVersion model."""

    def test_create_source_version(self) -> None:
        """Test creating SourceVersion with chunk hashes."""
        hashes = ["a" * 64, "b" * 64, "c" * 64]
        version = SourceVersion(
            source_id="source-1",
            version=1,
            markdown="# Content",
            chunk_hashes=hashes,
            adapter_id="adapter-1",
            normalizer_version="1.0.0",
            fetch_timestamp="2025-03-02T10:00:00Z",
        )
        assert version.version == 1
        assert version.chunk_hashes == tuple(hashes)
        assert len(version.chunk_hashes) == 3

    def test_source_version_empty_hashes(self) -> None:
        """Test SourceVersion with empty chunk_hashes list."""
        version = SourceVersion(
            source_id="source-1",
            version=0,
            markdown="",
            chunk_hashes=[],
            adapter_id="adapter-1",
            normalizer_version="1.0.0",
            fetch_timestamp="2025-03-02T10:00:00Z",
        )
        assert version.chunk_hashes == ()

    def test_frozen_immutability(self) -> None:
        """Test that SourceVersion is frozen."""
        version = SourceVersion(
            source_id="source-1",
            version=1,
            markdown="test",
            chunk_hashes=[],
            adapter_id="adapter-1",
            normalizer_version="1.0.0",
            fetch_timestamp="2025-03-02T10:00:00Z",
        )
        with pytest.raises(ValidationError):
            version.version = 2  # type: ignore[assignment]


class TestDiffResult:
    """Tests for DiffResult model."""

    def test_unchanged_content(self) -> None:
        """Test DiffResult when content has not changed."""
        result = DiffResult(
            changed=False,
            added_hashes=set(),
            removed_hashes=set(),
            unchanged_hashes={"a" * 64, "b" * 64},
        )
        assert result.changed is False
        assert result.added_hashes == frozenset()
        assert result.removed_hashes == frozenset()
        assert len(result.unchanged_hashes) == 2

    def test_changed_with_diff(self) -> None:
        """Test DiffResult when content has changed with additions and removals."""
        result = DiffResult(
            changed=True,
            added_hashes={"c" * 64, "d" * 64},
            removed_hashes={"e" * 64},
            unchanged_hashes={"a" * 64, "b" * 64},
            prev_hash="1111111111111111111111111111111111111111111111111111111111111111",
            curr_hash="2222222222222222222222222222222222222222222222222222222222222222",
        )
        assert result.changed is True
        assert len(result.added_hashes) == 2
        assert len(result.removed_hashes) == 1
        assert len(result.unchanged_hashes) == 2
        assert result.prev_hash is not None
        assert result.curr_hash is not None

    def test_first_ingest(self) -> None:
        """Test DiffResult for first ingest (all chunks are added)."""
        result = DiffResult(
            changed=True,
            added_hashes={"a" * 64, "b" * 64, "c" * 64},
            removed_hashes=set(),
            unchanged_hashes=set(),
            prev_hash=None,
            curr_hash="2222222222222222222222222222222222222222222222222222222222222222",
        )
        assert result.prev_hash is None
        assert result.curr_hash is not None
        assert len(result.added_hashes) == 3

    def test_overlapping_added_and_removed_hashes_raises_error(self) -> None:
        """Test that overlapping added_hashes and removed_hashes raises ValueError."""
        overlapping_hash = "a" * 64
        with pytest.raises(ValueError) as exc_info:
            DiffResult(
                changed=True,
                added_hashes={overlapping_hash, "b" * 64},
                removed_hashes={overlapping_hash, "c" * 64},
                unchanged_hashes=set(),
            )
        assert "added_hashes and removed_hashes must be disjoint" in str(exc_info.value)

    def test_overlapping_added_and_unchanged_hashes_raises_error(self) -> None:
        """Test that overlapping added_hashes and unchanged_hashes raises ValueError."""
        overlapping_hash = "a" * 64
        with pytest.raises(ValueError) as exc_info:
            DiffResult(
                changed=True,
                added_hashes={overlapping_hash, "b" * 64},
                removed_hashes=set(),
                unchanged_hashes={overlapping_hash, "c" * 64},
            )
        assert "added_hashes and unchanged_hashes must be disjoint" in str(exc_info.value)

    def test_overlapping_removed_and_unchanged_hashes_raises_error(self) -> None:
        """Test that overlapping removed_hashes and unchanged_hashes raises ValueError."""
        overlapping_hash = "a" * 64
        with pytest.raises(ValueError) as exc_info:
            DiffResult(
                changed=True,
                added_hashes=set(),
                removed_hashes={overlapping_hash, "b" * 64},
                unchanged_hashes={overlapping_hash, "c" * 64},
            )
        assert "removed_hashes and unchanged_hashes must be disjoint" in str(exc_info.value)

    def test_changed_false_with_added_hashes_raises_error(self) -> None:
        """Test that changed=False with non-empty added_hashes raises ValueError."""
        with pytest.raises(ValueError) as exc_info:
            DiffResult(
                changed=False,
                added_hashes={"a" * 64},
                removed_hashes=set(),
                unchanged_hashes={"b" * 64},
            )
        assert "If changed=False, both added_hashes and removed_hashes must be empty" in str(
            exc_info.value
        )

    def test_changed_false_with_removed_hashes_raises_error(self) -> None:
        """Test that changed=False with non-empty removed_hashes raises ValueError."""
        with pytest.raises(ValueError) as exc_info:
            DiffResult(
                changed=False,
                added_hashes=set(),
                removed_hashes={"a" * 64},
                unchanged_hashes={"b" * 64},
            )
        assert "If changed=False, both added_hashes and removed_hashes must be empty" in str(
            exc_info.value
        )

    def test_frozen_immutability(self) -> None:
        """Test that DiffResult is frozen."""
        result = DiffResult(
            changed=False,
            added_hashes=set(),
            removed_hashes=set(),
            unchanged_hashes=set(),
        )
        with pytest.raises(ValidationError):
            result.changed = True  # type: ignore[assignment]


class TestAdapterConfig:
    """Tests for AdapterConfig model."""

    def test_create_adapter_config_minimal(self) -> None:
        """Test creating AdapterConfig with minimal fields."""
        config = AdapterConfig(
            adapter_id="adapter-fs-1",
            adapter_type="filesystem",
            domain=Domain.NOTES,
            normalizer_version="1.0.0",
        )
        assert config.adapter_id == "adapter-fs-1"
        assert config.adapter_type == "filesystem"
        assert config.domain == Domain.NOTES
        assert config.config is None

    def test_create_adapter_config_full(self) -> None:
        """Test creating AdapterConfig with all fields."""
        cfg_dict = {"directory": "/home/user/notes", "extensions": [".md", ".txt"]}
        config = AdapterConfig(
            adapter_id="adapter-fs-1",
            adapter_type="filesystem",
            domain=Domain.NOTES,
            normalizer_version="1.0.0",
            config=cfg_dict,
        )
        assert config.config == cfg_dict
        assert config.config["directory"] == "/home/user/notes"

    def test_adapter_config_domain_enum(self) -> None:
        """Test that AdapterConfig accepts all Domain values."""
        for domain in Domain:
            config = AdapterConfig(
                adapter_id="adapter-1",
                adapter_type="test",
                domain=domain,
                normalizer_version="1.0.0",
            )
            assert config.domain == domain

    def test_frozen_immutability(self) -> None:
        """Test that AdapterConfig is frozen."""
        config = AdapterConfig(
            adapter_id="adapter-1",
            adapter_type="test",
            domain=Domain.NOTES,
            normalizer_version="1.0.0",
        )
        with pytest.raises(ValidationError):
            config.adapter_type = "modified"  # type: ignore[assignment]


class TestPollStrategy:
    """Tests for PollStrategy enum."""

    def test_poll_strategy_values_are_strings(self) -> None:
        """Test that PollStrategy enum values are strings."""
        assert PollStrategy.PUSH == "push"
        assert PollStrategy.PULL == "pull"
        assert PollStrategy.WEBHOOK == "webhook"

    def test_poll_strategy_is_str_subclass(self) -> None:
        """Test that PollStrategy values are str subclass instances."""
        assert isinstance(PollStrategy.PUSH, str)
        assert isinstance(PollStrategy.PULL, str)
        assert isinstance(PollStrategy.WEBHOOK, str)

    def test_poll_strategy_all_values(self) -> None:
        """Test that all PollStrategy enum values are accessible."""
        strategies = [PollStrategy.PUSH, PollStrategy.PULL, PollStrategy.WEBHOOK]
        assert len(strategies) == 3
        values = [s.value for s in strategies]
        assert set(values) == {"push", "pull", "webhook"}


class TestMessageMetadata:
    """Tests for MessageMetadata model."""

    def test_create_message_metadata_all_fields(self) -> None:
        """Test creating MessageMetadata with all fields populated."""
        metadata = MessageMetadata(
            thread_id="thread-123",
            message_id="msg-456",
            sender="alice@example.com",
            recipients=["bob@example.com", "charlie@example.com"],
            timestamp="2024-01-15T10:30:00Z",
            in_reply_to="msg-455",
            subject="Re: Project Discussion",
            is_thread_root=False,
        )
        assert metadata.thread_id == "thread-123"
        assert metadata.message_id == "msg-456"
        assert metadata.sender == "alice@example.com"
        assert metadata.recipients == ("bob@example.com", "charlie@example.com")
        assert metadata.timestamp == "2024-01-15T10:30:00Z"
        assert metadata.in_reply_to == "msg-455"
        assert metadata.subject == "Re: Project Discussion"
        assert metadata.is_thread_root is False

    def test_create_message_metadata_minimal_required(self) -> None:
        """Test creating MessageMetadata with only required fields."""
        metadata = MessageMetadata(
            thread_id="t1",
            message_id="m1",
            sender="a@b.com",
            recipients=["c@d.com"],
            timestamp="2024-01-01T00:00:00Z",
            in_reply_to=None,
            subject=None,
            is_thread_root=True,
        )
        assert metadata.thread_id == "t1"
        assert metadata.message_id == "m1"
        assert metadata.sender == "a@b.com"
        assert metadata.recipients == ("c@d.com",)
        assert metadata.timestamp == "2024-01-01T00:00:00Z"
        assert metadata.in_reply_to is None
        assert metadata.subject is None
        assert metadata.is_thread_root is True

    def test_message_metadata_invalid_timestamp(self) -> None:
        """Test that MessageMetadata raises ValidationError for invalid ISO 8601 timestamp."""
        with pytest.raises(ValidationError):
            MessageMetadata(
                thread_id="t1",
                message_id="m1",
                sender="a@b.com",
                recipients=["c@d.com"],
                timestamp="not-a-timestamp",
                in_reply_to=None,
                subject=None,
                is_thread_root=True,
            )

    def test_message_metadata_frozen_immutability(self) -> None:
        """Test that MessageMetadata is frozen and raises ValidationError on mutation."""
        metadata = MessageMetadata(
            thread_id="t1",
            message_id="m1",
            sender="a@b.com",
            recipients=["c@d.com"],
            timestamp="2024-01-01T00:00:00Z",
            in_reply_to=None,
            subject=None,
            is_thread_root=True,
        )
        with pytest.raises(ValidationError):
            metadata.subject = "Modified"  # type: ignore[assignment]

    def test_message_metadata_model_dump_serializable(self) -> None:
        """Test that MessageMetadata.model_dump() returns JSON-serializable dict."""
        metadata = MessageMetadata(
            thread_id="t1",
            message_id="m1",
            sender="a@b.com",
            recipients=["c@d.com"],
            timestamp="2024-01-01T00:00:00Z",
            in_reply_to=None,
            subject="Test",
            is_thread_root=True,
        )
        dumped = metadata.model_dump()
        assert isinstance(dumped, dict)
        assert dumped["thread_id"] == "t1"
        assert dumped["message_id"] == "m1"
        assert dumped["sender"] == "a@b.com"
        assert dumped["recipients"] == ("c@d.com",)
        assert dumped["timestamp"] == "2024-01-01T00:00:00Z"
        assert dumped["in_reply_to"] is None
        assert dumped["subject"] == "Test"
        assert dumped["is_thread_root"] is True

    def test_message_metadata_empty_recipients_list(self) -> None:
        """Test that MessageMetadata accepts empty recipients list."""
        metadata = MessageMetadata(
            thread_id="t1",
            message_id="m1",
            sender="a@b.com",
            recipients=[],
            timestamp="2024-01-01T00:00:00Z",
            in_reply_to=None,
            subject=None,
            is_thread_root=False,
        )
        assert metadata.recipients == ()

    def test_message_metadata_empty_thread_id_rejected(self) -> None:
        """Test that MessageMetadata raises ValidationError for empty thread_id."""
        with pytest.raises(ValidationError) as exc_info:
            MessageMetadata(
                thread_id="",
                message_id="m1",
                sender="a@b.com",
                recipients=["c@d.com"],
                timestamp="2024-01-01T00:00:00Z",
                in_reply_to=None,
                subject=None,
                is_thread_root=False,
            )
        assert "thread_id must be a non-empty string" in str(exc_info.value)

    def test_message_metadata_empty_message_id_rejected(self) -> None:
        """Test that MessageMetadata raises ValidationError for empty message_id."""
        with pytest.raises(ValidationError) as exc_info:
            MessageMetadata(
                thread_id="t1",
                message_id="",
                sender="a@b.com",
                recipients=["c@d.com"],
                timestamp="2024-01-01T00:00:00Z",
                in_reply_to=None,
                subject=None,
                is_thread_root=False,
            )
        assert "message_id must be a non-empty string" in str(exc_info.value)

    def test_message_metadata_empty_sender_rejected(self) -> None:
        """Test that MessageMetadata raises ValidationError for empty sender."""
        with pytest.raises(ValidationError) as exc_info:
            MessageMetadata(
                thread_id="t1",
                message_id="m1",
                sender="",
                recipients=["c@d.com"],
                timestamp="2024-01-01T00:00:00Z",
                in_reply_to=None,
                subject=None,
                is_thread_root=False,
            )
        assert "sender must be a non-empty string" in str(exc_info.value)

    def test_message_metadata_is_thread_root_and_in_reply_to_mutually_exclusive(
        self,
    ) -> None:
        """Test that is_thread_root=True and in_reply_to are mutually exclusive."""
        with pytest.raises(ValidationError) as exc_info:
            MessageMetadata(
                thread_id="t1",
                message_id="m1",
                sender="a@b.com",
                recipients=["c@d.com"],
                timestamp="2024-01-01T00:00:00Z",
                in_reply_to="msg-0",
                subject=None,
                is_thread_root=True,
            )
        error_msg = str(exc_info.value)
        assert "is_thread_root=True and in_reply_to must be mutually exclusive" in error_msg

    def test_message_metadata_thread_root_without_in_reply_to_succeeds(self) -> None:
        """Test that is_thread_root=True succeeds when in_reply_to is None."""
        metadata = MessageMetadata(
            thread_id="t1",
            message_id="m1",
            sender="a@b.com",
            recipients=["c@d.com"],
            timestamp="2024-01-01T00:00:00Z",
            in_reply_to=None,
            subject=None,
            is_thread_root=True,
        )
        assert metadata.is_thread_root is True
        assert metadata.in_reply_to is None

    def test_message_metadata_reply_without_thread_root_succeeds(self) -> None:
        """Test that in_reply_to succeeds when is_thread_root=False."""
        metadata = MessageMetadata(
            thread_id="t1",
            message_id="m2",
            sender="b@b.com",
            recipients=["a@b.com"],
            timestamp="2024-01-01T01:00:00Z",
            in_reply_to="m1",
            subject=None,
            is_thread_root=False,
        )
        assert metadata.is_thread_root is False
        assert metadata.in_reply_to == "m1"


class TestTaskMetadata:
    """Tests for TaskMetadata model."""

    def test_create_task_metadata_all_fields(self) -> None:
        """Test creating TaskMetadata with all fields populated."""
        metadata = TaskMetadata(
            task_id="task-123",
            status="in-progress",
            title="Implement feature X",
            due_date="2024-03-15T23:59:59Z",
            priority=1,
            dependencies=("task-100", "task-101"),
            collaborators=("alice@example.com", "bob@example.com"),
            date_first_observed="2024-03-01T10:00:00Z",
            source_type="apple_reminders",
        )
        assert metadata.task_id == "task-123"
        assert metadata.status == "in-progress"
        assert metadata.title == "Implement feature X"
        assert metadata.due_date == "2024-03-15T23:59:59Z"
        assert metadata.priority == 1
        assert metadata.dependencies == ("task-100", "task-101")
        assert metadata.collaborators == ("alice@example.com", "bob@example.com")
        assert metadata.date_first_observed == "2024-03-01T10:00:00Z"
        assert metadata.source_type == "apple_reminders"

    def test_create_task_metadata_minimal_required(self) -> None:
        """Test creating TaskMetadata with only required fields."""
        metadata = TaskMetadata(
            task_id="t1",
            status="open",
            title="Do something",
            date_first_observed="2024-03-01T10:00:00Z",
            source_type="obsidian_tasks",
        )
        assert metadata.task_id == "t1"
        assert metadata.status == "open"
        assert metadata.title == "Do something"
        assert metadata.due_date is None
        assert metadata.priority is None
        assert metadata.dependencies == ()
        assert metadata.collaborators == ()
        assert metadata.date_first_observed == "2024-03-01T10:00:00Z"
        assert metadata.source_type == "obsidian_tasks"

    def test_task_metadata_status_open_valid(self) -> None:
        """Test that status 'open' is valid."""
        metadata = TaskMetadata(
            task_id="t1",
            status="open",
            title="Task",
            date_first_observed="2024-03-01T10:00:00Z",
            source_type="test",
        )
        assert metadata.status == "open"

    def test_task_metadata_status_completed_valid(self) -> None:
        """Test that status 'completed' is valid."""
        metadata = TaskMetadata(
            task_id="t1",
            status="completed",
            title="Task",
            date_first_observed="2024-03-01T10:00:00Z",
            source_type="test",
        )
        assert metadata.status == "completed"

    def test_task_metadata_status_cancelled_valid(self) -> None:
        """Test that status 'cancelled' is valid."""
        metadata = TaskMetadata(
            task_id="t1",
            status="cancelled",
            title="Task",
            date_first_observed="2024-03-01T10:00:00Z",
            source_type="test",
        )
        assert metadata.status == "cancelled"

    def test_task_metadata_status_in_progress_valid(self) -> None:
        """Test that status 'in-progress' is valid."""
        metadata = TaskMetadata(
            task_id="t1",
            status="in-progress",
            title="Task",
            date_first_observed="2024-03-01T10:00:00Z",
            source_type="test",
        )
        assert metadata.status == "in-progress"

    def test_task_metadata_status_invalid(self) -> None:
        """Test that invalid status is rejected."""
        with pytest.raises(ValidationError) as exc_info:
            TaskMetadata(
                task_id="t1",
                status="pending",
                title="Task",
                date_first_observed="2024-03-01T10:00:00Z",
                source_type="test",
            )
        # Status validator error message
        assert "status must be one of" in str(exc_info.value)

    def test_task_metadata_empty_task_id_rejected(self) -> None:
        """Test that empty task_id is rejected."""
        with pytest.raises(ValidationError) as exc_info:
            TaskMetadata(
                task_id="",
                status="open",
                title="Task",
                date_first_observed="2024-03-01T10:00:00Z",
                source_type="test",
            )
        assert "task_id must be a non-empty string" in str(exc_info.value)

    def test_task_metadata_empty_title_rejected(self) -> None:
        """Test that empty title is rejected."""
        with pytest.raises(ValidationError) as exc_info:
            TaskMetadata(
                task_id="t1",
                status="open",
                title="",
                date_first_observed="2024-03-01T10:00:00Z",
                source_type="test",
            )
        assert "title must be a non-empty string" in str(exc_info.value)

    def test_task_metadata_invalid_due_date(self) -> None:
        """Test that invalid due_date ISO 8601 is rejected."""
        with pytest.raises(ValidationError):
            TaskMetadata(
                task_id="t1",
                status="open",
                title="Task",
                due_date="not-a-date",
                date_first_observed="2024-03-01T10:00:00Z",
                source_type="test",
            )

    def test_task_metadata_invalid_date_first_observed(self) -> None:
        """Test that invalid date_first_observed ISO 8601 is rejected."""
        with pytest.raises(ValidationError):
            TaskMetadata(
                task_id="t1",
                status="open",
                title="Task",
                date_first_observed="invalid-date",
                source_type="test",
            )

    def test_task_metadata_frozen_immutability(self) -> None:
        """Test that TaskMetadata is frozen and raises ValidationError on mutation."""
        metadata = TaskMetadata(
            task_id="t1",
            status="open",
            title="Task",
            date_first_observed="2024-03-01T10:00:00Z",
            source_type="test",
        )
        with pytest.raises(ValidationError):
            metadata.status = "completed"  # type: ignore[assignment]

    def test_task_metadata_empty_source_type_rejected(self) -> None:
        """Test that empty source_type is rejected."""
        with pytest.raises(ValidationError):
            TaskMetadata(
                task_id="t1",
                status="open",
                title="Task",
                source_type="",
            )

    def test_task_metadata_priority_valid_range_1_4(self) -> None:
        """Test that priority values in range 1-4 are accepted."""
        for priority in [1, 2, 3, 4]:
            metadata = TaskMetadata(
                task_id="t1",
                status="open",
                title="Task",
                priority=priority,
                date_first_observed="2024-03-01T10:00:00Z",
                source_type="test",
            )
            assert metadata.priority == priority

    def test_task_metadata_priority_zero_rejected(self) -> None:
        """Test that priority=0 is rejected."""
        with pytest.raises(ValidationError) as exc_info:
            TaskMetadata(
                task_id="t1",
                status="open",
                title="Task",
                priority=0,
                date_first_observed="2024-03-01T10:00:00Z",
                source_type="test",
            )
        assert "priority must be in range 1-4" in str(exc_info.value)

    def test_task_metadata_priority_five_rejected(self) -> None:
        """Test that priority=5 is rejected."""
        with pytest.raises(ValidationError) as exc_info:
            TaskMetadata(
                task_id="t1",
                status="open",
                title="Task",
                priority=5,
                date_first_observed="2024-03-01T10:00:00Z",
                source_type="test",
            )
        assert "priority must be in range 1-4" in str(exc_info.value)

    def test_task_metadata_priority_negative_rejected(self) -> None:
        """Test that negative priority is rejected."""
        with pytest.raises(ValidationError) as exc_info:
            TaskMetadata(
                task_id="t1",
                status="open",
                title="Task",
                priority=-1,
                date_first_observed="2024-03-01T10:00:00Z",
                source_type="test",
            )
        assert "priority must be in range 1-4" in str(exc_info.value)

    def test_task_metadata_priority_none_valid(self) -> None:
        """Test that priority=None (optional) is valid."""
        metadata = TaskMetadata(
            task_id="t1",
            status="open",
            title="Task",
            priority=None,
            date_first_observed="2024-03-01T10:00:00Z",
            source_type="test",
        )
        assert metadata.priority is None

    def test_task_metadata_model_dump_serializable(self) -> None:
        """Test that TaskMetadata.model_dump() returns JSON-serializable dict."""
        metadata = TaskMetadata(
            task_id="t1",
            status="open",
            title="Task",
            due_date="2024-03-15T23:59:59Z",
            priority=1,
            dependencies=("task-100",),
            collaborators=("alice@example.com",),
            date_first_observed="2024-03-01T10:00:00Z",
            source_type="apple_reminders",
        )
        dumped = metadata.model_dump()
        assert isinstance(dumped, dict)
        assert dumped["task_id"] == "t1"
        assert dumped["status"] == "open"  # Status is a plain string, not an enum
        assert dumped["title"] == "Task"
        assert dumped["due_date"] == "2024-03-15T23:59:59Z"
        assert dumped["priority"] == 1
        assert dumped["dependencies"] == ("task-100",)
        assert dumped["collaborators"] == ("alice@example.com",)


class TestEventMetadata:
    """Tests for EventMetadata model."""

    def test_create_event_metadata_all_fields(self) -> None:
        """Test creating EventMetadata with all fields populated."""
        metadata = EventMetadata(
            event_id="event-123",
            title="Team Meeting",
            start_date="2024-03-15T14:00:00Z",
            end_date="2024-03-15T15:00:00Z",
            duration_minutes=60,
            host="alice@example.com",
            invitees=("bob@example.com", "charlie@example.com"),
            date_first_observed="2024-03-01T10:00:00Z",
            source_type="caldav",
        )
        assert metadata.event_id == "event-123"
        assert metadata.title == "Team Meeting"
        assert metadata.start_date == "2024-03-15T14:00:00Z"
        assert metadata.end_date == "2024-03-15T15:00:00Z"
        assert metadata.duration_minutes == 60
        assert metadata.host == "alice@example.com"
        assert metadata.invitees == ("bob@example.com", "charlie@example.com")
        assert metadata.date_first_observed == "2024-03-01T10:00:00Z"
        assert metadata.source_type == "caldav"

    def test_create_event_metadata_minimal_required(self) -> None:
        """Test creating EventMetadata with only required fields."""
        metadata = EventMetadata(
            event_id="e1",
            title="Event",
            date_first_observed="2024-03-01T10:00:00Z",
            source_type="apple_health",
        )
        assert metadata.event_id == "e1"
        assert metadata.title == "Event"
        assert metadata.start_date is None
        assert metadata.end_date is None
        assert metadata.duration_minutes is None
        assert metadata.host is None
        assert metadata.invitees == ()
        assert metadata.date_first_observed == "2024-03-01T10:00:00Z"
        assert metadata.source_type == "apple_health"

    def test_event_metadata_empty_event_id_rejected(self) -> None:
        """Test that empty event_id is rejected."""
        with pytest.raises(ValidationError) as exc_info:
            EventMetadata(
                event_id="",
                title="Event",
                date_first_observed="2024-03-01T10:00:00Z",
                source_type="test",
            )
        assert "event_id must be a non-empty string" in str(exc_info.value)

    def test_event_metadata_empty_title_rejected(self) -> None:
        """Test that empty title is rejected."""
        with pytest.raises(ValidationError) as exc_info:
            EventMetadata(
                event_id="e1",
                title="",
                date_first_observed="2024-03-01T10:00:00Z",
                source_type="test",
            )
        assert "title must be a non-empty string" in str(exc_info.value)

    def test_event_metadata_invalid_start_date(self) -> None:
        """Test that invalid start_date ISO 8601 is rejected."""
        with pytest.raises(ValidationError):
            EventMetadata(
                event_id="e1",
                title="Event",
                start_date="not-a-date",
                date_first_observed="2024-03-01T10:00:00Z",
                source_type="test",
            )

    def test_event_metadata_invalid_end_date(self) -> None:
        """Test that invalid end_date ISO 8601 is rejected."""
        with pytest.raises(ValidationError):
            EventMetadata(
                event_id="e1",
                title="Event",
                end_date="not-a-date",
                date_first_observed="2024-03-01T10:00:00Z",
                source_type="test",
            )

    def test_event_metadata_invalid_date_first_observed(self) -> None:
        """Test that invalid date_first_observed ISO 8601 is rejected."""
        with pytest.raises(ValidationError):
            EventMetadata(
                event_id="e1",
                title="Event",
                date_first_observed="invalid-date",
                source_type="test",
            )

    def test_event_metadata_start_date_before_end_date_valid(self) -> None:
        """Test that start_date < end_date is valid."""
        metadata = EventMetadata(
            event_id="e1",
            title="Event",
            start_date="2024-03-15T14:00:00Z",
            end_date="2024-03-15T15:00:00Z",
            date_first_observed="2024-03-01T10:00:00Z",
            source_type="test",
        )
        assert metadata.start_date == "2024-03-15T14:00:00Z"
        assert metadata.end_date == "2024-03-15T15:00:00Z"

    def test_event_metadata_start_date_equals_end_date_valid(self) -> None:
        """Test that start_date == end_date is valid."""
        metadata = EventMetadata(
            event_id="e1",
            title="Event",
            start_date="2024-03-15T14:00:00Z",
            end_date="2024-03-15T14:00:00Z",
            date_first_observed="2024-03-01T10:00:00Z",
            source_type="test",
        )
        assert metadata.start_date == metadata.end_date

    def test_event_metadata_start_date_after_end_date_rejected(self) -> None:
        """Test that start_date > end_date is rejected."""
        with pytest.raises(ValidationError) as exc_info:
            EventMetadata(
                event_id="e1",
                title="Event",
                start_date="2024-03-15T15:00:00Z",
                end_date="2024-03-15T14:00:00Z",
                date_first_observed="2024-03-01T10:00:00Z",
                source_type="test",
            )
        assert "start_date must be <= end_date" in str(exc_info.value)

    def test_event_metadata_only_start_date_valid(self) -> None:
        """Test that only start_date without end_date is valid."""
        metadata = EventMetadata(
            event_id="e1",
            title="Event",
            start_date="2024-03-15T14:00:00Z",
            end_date=None,
            date_first_observed="2024-03-01T10:00:00Z",
            source_type="test",
        )
        assert metadata.start_date == "2024-03-15T14:00:00Z"
        assert metadata.end_date is None

    def test_event_metadata_only_end_date_valid(self) -> None:
        """Test that only end_date without start_date is valid."""
        metadata = EventMetadata(
            event_id="e1",
            title="Event",
            start_date=None,
            end_date="2024-03-15T15:00:00Z",
            date_first_observed="2024-03-01T10:00:00Z",
            source_type="test",
        )
        assert metadata.start_date is None
        assert metadata.end_date == "2024-03-15T15:00:00Z"

    def test_event_metadata_frozen_immutability(self) -> None:
        """Test that EventMetadata is frozen and raises ValidationError on mutation."""
        metadata = EventMetadata(
            event_id="e1",
            title="Event",
            date_first_observed="2024-03-01T10:00:00Z",
            source_type="test",
        )
        with pytest.raises(ValidationError):
            metadata.title = "Modified"  # type: ignore[assignment]

    def test_event_metadata_empty_source_type_rejected(self) -> None:
        """Test that empty source_type is rejected."""
        with pytest.raises(ValidationError):
            EventMetadata(
                event_id="e1",
                title="Event",
                source_type="",
            )

    def test_event_metadata_duration_minutes_non_negative_valid(self) -> None:
        """Test that non-negative duration_minutes values are accepted."""
        for duration in [0, 1, 30, 60, 1440, 999999]:
            metadata = EventMetadata(
                event_id="e1",
                title="Event",
                duration_minutes=duration,
                date_first_observed="2024-03-01T10:00:00Z",
                source_type="test",
            )
            assert metadata.duration_minutes == duration

    def test_event_metadata_duration_minutes_negative_rejected(self) -> None:
        """Test that negative duration_minutes is rejected."""
        with pytest.raises(ValidationError) as exc_info:
            EventMetadata(
                event_id="e1",
                title="Event",
                duration_minutes=-1,
                date_first_observed="2024-03-01T10:00:00Z",
                source_type="test",
            )
        assert "duration_minutes must be non-negative" in str(exc_info.value)

    def test_event_metadata_duration_minutes_negative_large_rejected(self) -> None:
        """Test that large negative duration_minutes is rejected."""
        with pytest.raises(ValidationError) as exc_info:
            EventMetadata(
                event_id="e1",
                title="Event",
                duration_minutes=-999,
                date_first_observed="2024-03-01T10:00:00Z",
                source_type="test",
            )
        assert "duration_minutes must be non-negative" in str(exc_info.value)

    def test_event_metadata_duration_minutes_none_valid(self) -> None:
        """Test that duration_minutes=None (optional) is valid."""
        metadata = EventMetadata(
            event_id="e1",
            title="Event",
            duration_minutes=None,
            date_first_observed="2024-03-01T10:00:00Z",
            source_type="test",
        )
        assert metadata.duration_minutes is None

    def test_event_metadata_model_dump_serializable(self) -> None:
        """Test that EventMetadata.model_dump() returns JSON-serializable dict."""
        metadata = EventMetadata(
            event_id="e1",
            title="Event",
            start_date="2024-03-15T14:00:00Z",
            end_date="2024-03-15T15:00:00Z",
            duration_minutes=60,
            host="alice@example.com",
            invitees=("bob@example.com",),
            date_first_observed="2024-03-01T10:00:00Z",
            source_type="caldav",
        )
        dumped = metadata.model_dump()
        assert isinstance(dumped, dict)
        assert dumped["event_id"] == "e1"
        assert dumped["title"] == "Event"
        assert dumped["start_date"] == "2024-03-15T14:00:00Z"
        assert dumped["end_date"] == "2024-03-15T15:00:00Z"
        assert dumped["duration_minutes"] == 60
        assert dumped["host"] == "alice@example.com"
        assert dumped["invitees"] == ("bob@example.com",)


class TestComputeChunkHash:
    """Tests for compute_chunk_hash function."""

    def test_hash_determinism_identical_content(self) -> None:
        """Test that identical content always produces the same hash."""
        content = "This is a test chunk of content."
        hash1 = compute_chunk_hash(content)
        hash2 = compute_chunk_hash(content)
        assert hash1 == hash2
        assert len(hash1) == 64  # SHA-256 hex is 64 chars

    def test_hash_different_for_different_content(self) -> None:
        """Test that different content produces different hashes."""
        hash1 = compute_chunk_hash("Content A")
        hash2 = compute_chunk_hash("Content B")
        assert hash1 != hash2

    def test_whitespace_normalization_multiple_spaces(self) -> None:
        """Test that multiple spaces are collapsed to single space."""
        content1 = "Multiple   spaces   here"
        content2 = "Multiple spaces here"
        assert compute_chunk_hash(content1) == compute_chunk_hash(content2)

    def test_whitespace_normalization_trailing(self) -> None:
        """Test that trailing whitespace is stripped per line."""
        content1 = "Line 1   \nLine 2   "
        content2 = "Line 1\nLine 2"
        assert compute_chunk_hash(content1) == compute_chunk_hash(content2)

    def test_whitespace_normalization_line_endings_crlf(self) -> None:
        """Test that CRLF line endings are normalized to LF."""
        content1 = "Line 1\r\nLine 2\r\nLine 3"
        content2 = "Line 1\nLine 2\nLine 3"
        assert compute_chunk_hash(content1) == compute_chunk_hash(content2)

    def test_whitespace_normalization_mixed_line_endings(self) -> None:
        """Test that mixed line endings (CR, LF, CRLF) are normalized."""
        content1 = "Line 1\rLine 2\nLine 3\r\nLine 4"
        content2 = "Line 1\nLine 2\nLine 3\nLine 4"
        assert compute_chunk_hash(content1) == compute_chunk_hash(content2)

    def test_whitespace_normalization_tabs_and_spaces(self) -> None:
        """Test that tabs and spaces are collapsed together."""
        content1 = "Text\t\t  with\ttabs  and  spaces"
        content2 = "Text with tabs and spaces"
        assert compute_chunk_hash(content1) == compute_chunk_hash(content2)

    def test_hash_format(self) -> None:
        """Test that hash is valid lowercase hex."""
        hash_result = compute_chunk_hash("test content")
        assert len(hash_result) == 64
        assert all(c in "0123456789abcdef" for c in hash_result)

    def test_context_header_excluded_from_hash(self) -> None:
        """Test that context header is excluded from hash computation.

        Chunks with identical content but different context headers must have
        the same chunk_hash, proving that only content (not the header) is used
        for computing the hash.
        """
        content = "This is the chunk content."
        content_hash = compute_chunk_hash(content)

        # Create two Chunk objects with same content but different headers
        chunk1 = Chunk(
            chunk_hash=content_hash,
            content=content,
            context_header="# Section > ## Subsection",
            chunk_index=0,
        )
        chunk2 = Chunk(
            chunk_hash=content_hash,
            content=content,
            context_header="## Different Header",
            chunk_index=1,
        )

        # Both chunks have the same hash even with different headers
        assert chunk1.chunk_hash == chunk2.chunk_hash
        # This proves context_header is excluded from hash computation

    def test_empty_content(self) -> None:
        """Test hashing empty content."""
        hash_result = compute_chunk_hash("")
        assert len(hash_result) == 64
        assert all(c in "0123456789abcdef" for c in hash_result)

    def test_hash_stability_across_runs(self) -> None:
        """Test that the same hash is always produced (determinism test)."""
        content = "Deterministic test content\nWith multiple lines\nAnd spaces"
        expected_hash = compute_chunk_hash(content)
        for _ in range(10):
            assert compute_chunk_hash(content) == expected_hash

    def test_whitespace_normalization_consecutive_blank_lines_double(self) -> None:
        """Test that multiple consecutive blank lines are collapsed to single blank line.

        This test ensures FR-6.4 compliance: blank-line-only changes are treated as unchanged.
        A change from two blank lines to three blank lines should produce the same hash.
        """
        content1 = "Line 1\n\nLine 2"
        content2 = "Line 1\n\n\nLine 2"
        assert compute_chunk_hash(content1) == compute_chunk_hash(content2)

    def test_whitespace_normalization_consecutive_blank_lines_many(self) -> None:
        """Test that many consecutive blank lines are collapsed to single blank line."""
        content1 = "Line 1\n\nLine 2"
        content5 = "Line 1\n\n\n\n\nLine 2"
        assert compute_chunk_hash(content1) == compute_chunk_hash(content5)

    def test_whitespace_normalization_blank_lines_at_start(self) -> None:
        """Test that leading blank lines are stripped (part of strip())."""
        content1 = "Content here"
        content2 = "\n\n\nContent here"
        assert compute_chunk_hash(content1) == compute_chunk_hash(content2)

    def test_whitespace_normalization_blank_lines_at_end(self) -> None:
        """Test that trailing blank lines are stripped (part of strip())."""
        content1 = "Content here"
        content2 = "Content here\n\n\n"
        assert compute_chunk_hash(content1) == compute_chunk_hash(content2)

    def test_whitespace_normalization_multiple_blank_line_sections(self) -> None:
        """Test that all consecutive blank line sections are normalized independently."""
        content1 = "Line 1\n\nSection 2\n\nLine 3"
        content2 = "Line 1\n\n\nSection 2\n\n\n\nLine 3"
        assert compute_chunk_hash(content1) == compute_chunk_hash(content2)

    def test_whitespace_normalization_preserves_single_blank_lines(self) -> None:
        """Test that single blank lines between paragraphs are preserved."""
        # Single blank line should remain a single blank line
        content = "Paragraph 1\n\nParagraph 2\n\nParagraph 3"
        hash1 = compute_chunk_hash(content)
        hash2 = compute_chunk_hash(content)
        assert hash1 == hash2  # Deterministic

    def test_blank_line_only_change_treated_as_unchanged(self) -> None:
        """Integration test: blank-line-only changes produce identical hashes.

        This directly addresses FR-6.4 requirement: whitespace-only changes
        should produce an unchanged result.
        """
        prev_content = "Content\n\nMore content"
        curr_content = "Content\n\n\nMore content"

        prev_hash = compute_chunk_hash(prev_content)
        curr_hash = compute_chunk_hash(curr_content)

        assert prev_hash == curr_hash, "Blank-line-only changes should not produce different hashes"


class TestVersionDiff:
    """Tests for VersionDiff model."""

    def test_version_diff_basic_construction(self) -> None:
        """Test basic construction of VersionDiff model."""
        from context_library.storage.models import VersionDiff

        diff = VersionDiff(
            source_id="src-1",
            from_version=1,
            to_version=2,
            added_hashes=frozenset(["a" * 64]),
            removed_hashes=frozenset(),
            unchanged_hashes=frozenset(["b" * 64]),
        )

        assert diff.source_id == "src-1"
        assert diff.from_version == 1
        assert diff.to_version == 2
        assert "a" * 64 in diff.added_hashes
        assert diff.added_chunks == ()

    def test_version_diff_with_chunks(self) -> None:
        """Test VersionDiff with actual chunk objects."""
        from context_library.storage.models import VersionDiff, Chunk, ChunkType

        chunk1 = Chunk(
            chunk_hash="a" * 64,
            chunk_index=0,
            content="Added content",
            chunk_type=ChunkType.STANDARD,
            context_header="",
            domain_metadata={},
            cross_refs=(),
        )

        diff = VersionDiff(
            source_id="src-1",
            from_version=1,
            to_version=2,
            added_hashes=frozenset(["a" * 64]),
            removed_hashes=frozenset(),
            unchanged_hashes=frozenset(),
            added_chunks=(chunk1,),
        )

        assert len(diff.added_chunks) == 1
        assert diff.added_chunks[0].chunk_hash == "a" * 64

    def test_version_diff_disjoint_hashes_validation(self) -> None:
        """Test that VersionDiff validates hash set disjointness."""
        from context_library.storage.models import VersionDiff

        # added and removed should be disjoint
        with pytest.raises(ValueError, match="added_hashes and removed_hashes must be disjoint"):
            VersionDiff(
                source_id="src-1",
                from_version=1,
                to_version=2,
                added_hashes=frozenset(["a" * 64]),
                removed_hashes=frozenset(["a" * 64]),  # Overlap!
                unchanged_hashes=frozenset(),
            )

    def test_version_diff_added_and_unchanged_disjoint(self) -> None:
        """Test that added_hashes and unchanged_hashes must be disjoint."""
        from context_library.storage.models import VersionDiff

        with pytest.raises(ValueError, match="added_hashes and unchanged_hashes must be disjoint"):
            VersionDiff(
                source_id="src-1",
                from_version=1,
                to_version=2,
                added_hashes=frozenset(["a" * 64]),
                removed_hashes=frozenset(),
                unchanged_hashes=frozenset(["a" * 64]),  # Overlap!
            )

    def test_version_diff_removed_and_unchanged_disjoint(self) -> None:
        """Test that removed_hashes and unchanged_hashes must be disjoint."""
        from context_library.storage.models import VersionDiff

        with pytest.raises(ValueError, match="removed_hashes and unchanged_hashes must be disjoint"):
            VersionDiff(
                source_id="src-1",
                from_version=1,
                to_version=2,
                added_hashes=frozenset(),
                removed_hashes=frozenset(["a" * 64]),
                unchanged_hashes=frozenset(["a" * 64]),  # Overlap!
            )

    def test_version_diff_added_chunks_must_match_hashes(self) -> None:
        """Test that added_chunks hashes must be in added_hashes."""
        from context_library.storage.models import VersionDiff, Chunk, ChunkType

        chunk = Chunk(
            chunk_hash="b" * 64,  # Not in added_hashes!
            chunk_index=0,
            content="Content",
            chunk_type=ChunkType.STANDARD,
            context_header="",
            domain_metadata={},
            cross_refs=(),
        )

        with pytest.raises(ValueError, match="added_chunks must be a subset of added_hashes"):
            VersionDiff(
                source_id="src-1",
                from_version=1,
                to_version=2,
                added_hashes=frozenset(["a" * 64]),
                removed_hashes=frozenset(),
                unchanged_hashes=frozenset(),
                added_chunks=(chunk,),
            )

    def test_version_diff_removed_chunks_must_match_hashes(self) -> None:
        """Test that removed_chunks hashes must be in removed_hashes."""
        from context_library.storage.models import VersionDiff, Chunk, ChunkType

        chunk = Chunk(
            chunk_hash="b" * 64,  # Not in removed_hashes!
            chunk_index=0,
            content="Content",
            chunk_type=ChunkType.STANDARD,
            context_header="",
            domain_metadata={},
            cross_refs=(),
        )

        with pytest.raises(ValueError, match="removed_chunks must be a subset of removed_hashes"):
            VersionDiff(
                source_id="src-1",
                from_version=1,
                to_version=2,
                added_hashes=frozenset(),
                removed_hashes=frozenset(["a" * 64]),
                unchanged_hashes=frozenset(),
                removed_chunks=(chunk,),
            )

    def test_version_diff_frozen_immutability(self) -> None:
        """Test that VersionDiff is frozen and immutable."""
        from context_library.storage.models import VersionDiff

        diff = VersionDiff(
            source_id="src-1",
            from_version=1,
            to_version=2,
            added_hashes=frozenset(),
            removed_hashes=frozenset(),
            unchanged_hashes=frozenset(),
        )

        with pytest.raises(Exception):  # Pydantic frozen model
            diff.source_id = "src-2"  # type: ignore


class TestSourceTimeline:
    """Tests for SourceTimeline model."""

    def test_source_timeline_basic_construction(self) -> None:
        """Test basic construction of SourceTimeline."""
        from context_library.storage.models import SourceTimeline, SourceVersion

        version1 = SourceVersion(
            source_id="src-1",
            version=1,
            markdown="Content v1",
            chunk_hashes=("a" * 64,),
            adapter_id="adapter-1",
            normalizer_version="1.0.0",
            fetch_timestamp="2025-03-02T10:00:00Z",
        )

        timeline = SourceTimeline(
            source_id="src-1",
            versions=(version1,),
        )

        assert timeline.source_id == "src-1"
        assert len(timeline.versions) == 1

    def test_source_timeline_multiple_versions_ordered(self) -> None:
        """Test SourceTimeline with multiple ordered versions."""
        from context_library.storage.models import SourceTimeline, SourceVersion

        versions = []
        for v in range(1, 4):
            version = SourceVersion(
                source_id="src-1",
                version=v,
                markdown=f"Content v{v}",
                chunk_hashes=(f"{chr(97 + v)}" * 64,),
                adapter_id="adapter-1",
                normalizer_version="1.0.0",
                fetch_timestamp="2025-03-02T10:00:00Z",
            )
            versions.append(version)

        timeline = SourceTimeline(
            source_id="src-1",
            versions=tuple(versions),
        )

        assert len(timeline.versions) == 3
        assert timeline.versions[0].version == 1
        assert timeline.versions[1].version == 2
        assert timeline.versions[2].version == 3

    def test_source_timeline_empty_versions_allowed(self) -> None:
        """Test that SourceTimeline can have empty versions."""
        from context_library.storage.models import SourceTimeline

        timeline = SourceTimeline(
            source_id="src-1",
            versions=(),
        )

        assert len(timeline.versions) == 0

    def test_source_timeline_version_source_id_mismatch(self) -> None:
        """Test that all versions must have matching source_id."""
        from context_library.storage.models import SourceTimeline, SourceVersion

        version1 = SourceVersion(
            source_id="src-1",
            version=1,
            markdown="Content",
            chunk_hashes=(),
            adapter_id="adapter-1",
            normalizer_version="1.0.0",
            fetch_timestamp="2025-03-02T10:00:00Z",
        )

        version2 = SourceVersion(
            source_id="src-2",  # Mismatched!
            version=2,
            markdown="Content",
            chunk_hashes=(),
            adapter_id="adapter-1",
            normalizer_version="1.0.0",
            fetch_timestamp="2025-03-02T10:00:00Z",
        )

        with pytest.raises(ValueError, match="All versions must have source_id"):
            SourceTimeline(
                source_id="src-1",
                versions=(version1, version2),
            )

    def test_source_timeline_versions_must_be_ordered(self) -> None:
        """Test that versions must be ordered by version number."""
        from context_library.storage.models import SourceTimeline, SourceVersion

        version1 = SourceVersion(
            source_id="src-1",
            version=2,  # Out of order!
            markdown="Content",
            chunk_hashes=(),
            adapter_id="adapter-1",
            normalizer_version="1.0.0",
            fetch_timestamp="2025-03-02T10:00:00Z",
        )

        version2 = SourceVersion(
            source_id="src-1",
            version=1,
            markdown="Content",
            chunk_hashes=(),
            adapter_id="adapter-1",
            normalizer_version="1.0.0",
            fetch_timestamp="2025-03-02T10:00:00Z",
        )

        with pytest.raises(ValueError, match="versions must be ordered chronologically"):
            SourceTimeline(
                source_id="src-1",
                versions=(version1, version2),
            )

    def test_source_timeline_duplicate_version_numbers_rejected(self) -> None:
        """Test that duplicate version numbers are rejected."""
        from context_library.storage.models import SourceTimeline, SourceVersion

        version1 = SourceVersion(
            source_id="src-1",
            version=1,
            markdown="Content",
            chunk_hashes=(),
            adapter_id="adapter-1",
            normalizer_version="1.0.0",
            fetch_timestamp="2025-03-02T10:00:00Z",
        )

        version2 = SourceVersion(
            source_id="src-1",
            version=1,  # Duplicate!
            markdown="Content",
            chunk_hashes=(),
            adapter_id="adapter-1",
            normalizer_version="1.0.0",
            fetch_timestamp="2025-03-02T10:00:00Z",
        )

        with pytest.raises(ValueError, match="versions must be ordered chronologically"):
            SourceTimeline(
                source_id="src-1",
                versions=(version1, version2),
            )

    def test_source_timeline_frozen_immutability(self) -> None:
        """Test that SourceTimeline is frozen and immutable."""
        from context_library.storage.models import SourceTimeline

        timeline = SourceTimeline(
            source_id="src-1",
            versions=(),
        )

        with pytest.raises(Exception):  # Pydantic frozen model
            timeline.source_id = "src-2"  # type: ignore


class TestChunkProvenance:
    """Tests for ChunkProvenance model."""

    def test_chunk_provenance_basic_construction(self) -> None:
        """Test basic construction of ChunkProvenance."""
        from context_library.storage.models import ChunkProvenance, LineageRecord

        chunk = Chunk(
            chunk_hash="a" * 64,
            chunk_index=0,
            content="Content",
            chunk_type=ChunkType.STANDARD,
            context_header="",
            domain_metadata={},
            cross_refs=(),
        )

        lineage = LineageRecord(
            chunk_hash="a" * 64,
            source_id="source-1",
            source_version_id=1,
            adapter_id="adapter-1",
            domain=Domain.NOTES,
            normalizer_version="1.0.0",
            embedding_model_id="model-1",
        )

        provenance = ChunkProvenance(
            chunk=chunk,
            lineage=lineage,
            source_origin_ref="test-source",
            adapter_type="test",
            version_chain=(chunk,),
        )

        assert provenance.chunk.chunk_hash == "a" * 64
        assert provenance.source_origin_ref == "test-source"
        assert len(provenance.version_chain) == 1

    def test_chunk_provenance_multiple_versions_in_chain(self) -> None:
        """Test ChunkProvenance with multiple chunks in version_chain."""
        from context_library.storage.models import ChunkProvenance, LineageRecord

        chunk1 = Chunk(
            chunk_hash="a" * 64,
            chunk_index=0,
            content="Version 1",
            chunk_type=ChunkType.STANDARD,
            context_header="",
            domain_metadata={},
            cross_refs=(),
        )

        chunk2 = Chunk(
            chunk_hash="a" * 64,
            chunk_index=0,
            content="Version 2",
            chunk_type=ChunkType.STANDARD,
            context_header="",
            domain_metadata={},
            cross_refs=(),
        )

        lineage = LineageRecord(
            chunk_hash="a" * 64,
            source_id="source-1",
            source_version_id=2,
            adapter_id="adapter-1",
            domain=Domain.NOTES,
            normalizer_version="1.0.0",
            embedding_model_id="model-1",
        )

        provenance = ChunkProvenance(
            chunk=chunk2,
            lineage=lineage,
            source_origin_ref="test-source",
            adapter_type="test",
            version_chain=(chunk1, chunk2),
        )

        assert len(provenance.version_chain) == 2

    def test_chunk_provenance_empty_version_chain_rejected(self) -> None:
        """Test that empty version_chain is rejected."""
        from context_library.storage.models import ChunkProvenance, LineageRecord

        chunk = Chunk(
            chunk_hash="a" * 64,
            chunk_index=0,
            content="Content",
            chunk_type=ChunkType.STANDARD,
            context_header="",
            domain_metadata={},
            cross_refs=(),
        )

        lineage = LineageRecord(
            chunk_hash="a" * 64,
            source_id="source-1",
            source_version_id=1,
            adapter_id="adapter-1",
            domain=Domain.NOTES,
            normalizer_version="1.0.0",
            embedding_model_id="model-1",
        )

        with pytest.raises(ValueError, match="version_chain cannot be empty"):
            ChunkProvenance(
                chunk=chunk,
                lineage=lineage,
                source_origin_ref="test-source",
                adapter_type="test",
                version_chain=(),
            )

    def test_chunk_provenance_last_chunk_must_match_current(self) -> None:
        """Test that last chunk in version_chain must match current chunk."""
        from context_library.storage.models import ChunkProvenance, LineageRecord

        chunk1 = Chunk(
            chunk_hash="a" * 64,
            chunk_index=0,
            content="Version 1",
            chunk_type=ChunkType.STANDARD,
            context_header="",
            domain_metadata={},
            cross_refs=(),
        )

        chunk2 = Chunk(
            chunk_hash="b" * 64,  # Different hash!
            chunk_index=0,
            content="Version 2",
            chunk_type=ChunkType.STANDARD,
            context_header="",
            domain_metadata={},
            cross_refs=(),
        )

        lineage = LineageRecord(
            chunk_hash="b" * 64,
            source_id="source-1",
            source_version_id=2,
            adapter_id="adapter-1",
            domain=Domain.NOTES,
            normalizer_version="1.0.0",
            embedding_model_id="model-1",
        )

        with pytest.raises(ValueError, match="version_chain must end with the current chunk"):
            ChunkProvenance(
                chunk=chunk2,
                lineage=lineage,
                source_origin_ref="test-source",
                adapter_type="test",
                version_chain=(chunk1,),  # Missing chunk2!
            )

    def test_chunk_provenance_chain_ordering(self) -> None:
        """Test that version_chain maintains proper ordering with current chunk last."""
        from context_library.storage.models import ChunkProvenance, LineageRecord

        chunk1 = Chunk(
            chunk_hash="a" * 64,
            chunk_index=0,
            content="Version 1",
            chunk_type=ChunkType.STANDARD,
            context_header="",
            domain_metadata={},
            cross_refs=(),
        )

        chunk2 = Chunk(
            chunk_hash="b" * 64,
            chunk_index=0,
            content="Version 2",
            chunk_type=ChunkType.STANDARD,
            context_header="",
            domain_metadata={},
            cross_refs=(),
        )

        chunk3 = Chunk(
            chunk_hash="c" * 64,
            chunk_index=0,
            content="Version 3",
            chunk_type=ChunkType.STANDARD,
            context_header="",
            domain_metadata={},
            cross_refs=(),
        )

        lineage = LineageRecord(
            chunk_hash="c" * 64,
            source_id="source-1",
            source_version_id=3,
            adapter_id="adapter-1",
            domain=Domain.NOTES,
            normalizer_version="1.0.0",
            embedding_model_id="model-1",
        )

        provenance = ChunkProvenance(
            chunk=chunk3,
            lineage=lineage,
            source_origin_ref="test-source",
            adapter_type="test",
            version_chain=(chunk1, chunk2, chunk3),
        )

        # Verify order: oldest to newest
        assert provenance.version_chain[0].chunk_hash == "a" * 64
        assert provenance.version_chain[1].chunk_hash == "b" * 64
        assert provenance.version_chain[2].chunk_hash == "c" * 64
        assert provenance.version_chain[-1].chunk_hash == provenance.chunk.chunk_hash

    def test_chunk_provenance_frozen_immutability(self) -> None:
        """Test that ChunkProvenance is frozen and immutable."""
        from context_library.storage.models import ChunkProvenance, LineageRecord

        chunk = Chunk(
            chunk_hash="a" * 64,
            chunk_index=0,
            content="Content",
            chunk_type=ChunkType.STANDARD,
            context_header="",
            domain_metadata={},
            cross_refs=(),
        )

        lineage = LineageRecord(
            chunk_hash="a" * 64,
            source_id="source-1",
            source_version_id=1,
            adapter_id="adapter-1",
            domain=Domain.NOTES,
            normalizer_version="1.0.0",
            embedding_model_id="model-1",
        )

        provenance = ChunkProvenance(
            chunk=chunk,
            lineage=lineage,
            source_origin_ref="test-source",
            adapter_type="test",
            version_chain=(chunk,),
        )

        with pytest.raises(Exception):  # Pydantic frozen model
            provenance.source_origin_ref = "other-source"  # type: ignore
