"""Tests for the tasks domain."""

import pytest

from context_library.domains.registry import Domain, get_domain_chunker
from context_library.domains.tasks import TasksDomain
from context_library.storage.models import (
    Chunk,
    ChunkType,
    NormalizedContent,
    StructuralHints,
    TaskMetadata,
    compute_chunk_hash,
)


@pytest.fixture
def tasks_domain():
    """Create a TasksDomain instance with default limits."""
    return TasksDomain(hard_limit=1024)


@pytest.fixture
def sample_task_metadata():
    """Create sample TaskMetadata for testing."""
    return TaskMetadata(
        task_id="task-001",
        status="open",
        title="Complete project documentation",
        due_date="2025-02-15T23:59:59Z",
        priority=1,
        dependencies=("task-000",),
        collaborators=("alice@example.com",),
        date_first_observed="2025-01-15T10:30:00Z",
        source_type="todoist",
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


class TestTasksDomainRegistry:
    """Tests for TasksDomain domain registry integration."""

    def test_domain_chunker_registry_returns_tasks_domain(self):
        """get_domain_chunker(Domain.TASKS) returns a TasksDomain instance."""
        domain = get_domain_chunker(Domain.TASKS)

        assert isinstance(domain, TasksDomain)
        assert domain.hard_limit == 1024


class TestTasksDomainBasics:
    """Basic tests for TasksDomain initialization and properties."""

    def test_initialization_with_defaults(self):
        """TasksDomain initializes with default hard_limit."""
        domain = TasksDomain()

        assert domain.hard_limit == 1024

    def test_initialization_with_custom_limit(self):
        """TasksDomain initializes with custom hard_limit."""
        domain = TasksDomain(hard_limit=512)

        assert domain.hard_limit == 512

    def test_initialization_rejects_zero_hard_limit(self):
        """TasksDomain rejects hard_limit=0."""
        with pytest.raises(ValueError, match="hard_limit must be a positive integer"):
            TasksDomain(hard_limit=0)

    def test_initialization_rejects_negative_hard_limit(self):
        """TasksDomain rejects negative hard_limit."""
        with pytest.raises(ValueError, match="hard_limit must be a positive integer"):
            TasksDomain(hard_limit=-1)

    def test_initialization_rejects_negative_hard_limit_large(self):
        """TasksDomain rejects large negative hard_limit."""
        with pytest.raises(ValueError, match="hard_limit must be a positive integer"):
            TasksDomain(hard_limit=-1024)

    def test_chunk_returns_list_of_chunks(
        self, tasks_domain, sample_task_metadata, base_structural_hints
    ):
        """chunk() returns a list of Chunk instances."""
        hints = StructuralHints(
            has_headings=False,
            has_lists=False,
            has_tables=False,
            natural_boundaries=[],
            extra_metadata=sample_task_metadata.model_dump(),
        )

        content = NormalizedContent(
            markdown="This is a task description with some details.",
            source_id="task-001",
            structural_hints=hints,
            normalizer_version="1.0.0",
        )

        result = tasks_domain.chunk(content)

        assert isinstance(result, list)
        assert all(isinstance(chunk, Chunk) for chunk in result)
        assert len(result) >= 1

    def test_chunk_raises_without_extra_metadata(
        self, tasks_domain, base_structural_hints
    ):
        """chunk() raises ValueError if extra_metadata is missing."""
        content = NormalizedContent(
            markdown="Test task",
            source_id="task-001",
            structural_hints=base_structural_hints,
            normalizer_version="1.0.0",
        )

        with pytest.raises(ValueError, match="extra_metadata"):
            tasks_domain.chunk(content)


class TestSingleTaskChunk:
    """Tests for chunking single tasks."""

    def test_single_task_with_title_and_description_creates_one_chunk(
        self, tasks_domain, sample_task_metadata
    ):
        """A task with title and description creates exactly one chunk."""
        hints = StructuralHints(
            has_headings=False,
            has_lists=False,
            has_tables=False,
            natural_boundaries=[],
            extra_metadata=sample_task_metadata.model_dump(),
        )

        content = NormalizedContent(
            markdown="This is the task description with important details.",
            source_id="task-001",
            structural_hints=hints,
            normalizer_version="1.0.0",
        )

        chunks = tasks_domain.chunk(content)

        assert len(chunks) == 1
        assert chunks[0].content == "This is the task description with important details."
        assert chunks[0].chunk_index == 0

    def test_task_with_title_but_no_description_returns_empty_list(
        self, tasks_domain, sample_task_metadata
    ):
        """A task with only a title (no description) returns an empty list per spec."""
        hints = StructuralHints(
            has_headings=False,
            has_lists=False,
            has_tables=False,
            natural_boundaries=[],
            extra_metadata=sample_task_metadata.model_dump(),
        )

        # Empty markdown (no description)
        content = NormalizedContent(
            markdown="",
            source_id="task-001",
            structural_hints=hints,
            normalizer_version="1.0.0",
        )

        chunks = tasks_domain.chunk(content)

        # Per spec: tasks with no description content should return empty list
        assert len(chunks) == 0

    def test_task_with_whitespace_only_description_returns_empty_list(
        self, tasks_domain, sample_task_metadata
    ):
        """A task with whitespace-only description returns an empty list per spec."""
        hints = StructuralHints(
            has_headings=False,
            has_lists=False,
            has_tables=False,
            natural_boundaries=[],
            extra_metadata=sample_task_metadata.model_dump(),
        )

        content = NormalizedContent(
            markdown="   \n\t\n   ",
            source_id="task-001",
            structural_hints=hints,
            normalizer_version="1.0.0",
        )

        chunks = tasks_domain.chunk(content)

        # Per spec: tasks with no description content (including whitespace-only) should return empty list
        assert len(chunks) == 0

    def test_task_with_neither_title_nor_description_returns_empty_list(
        self, tasks_domain
    ):
        """A task with empty title cannot be created - title is required."""
        # TaskMetadata validation requires title to be non-empty,
        # so we can't even create a task with empty title
        with pytest.raises(ValueError, match="title must be a non-empty string"):
            TaskMetadata(
                task_id="task-001",
                status="open",
                title="",  # Empty title
                due_date=None,
                priority=None,
                dependencies=(),
                collaborators=(),
                date_first_observed="2025-01-15T10:30:00Z",
                source_type="todoist",
            )

    def test_chunk_raises_on_invalid_metadata_from_domain(
        self, tasks_domain, base_structural_hints
    ):
        """chunk() raises ValueError when extra_metadata contains invalid TaskMetadata."""
        # Create hints with invalid extra_metadata (empty title)
        hints = StructuralHints(
            has_headings=False,
            has_lists=False,
            has_tables=False,
            natural_boundaries=[],
            extra_metadata={
                "task_id": "task-001",
                "status": "open",
                "title": "",  # Invalid: empty title
                "due_date": None,
                "priority": None,
                "dependencies": (),
                "collaborators": (),
                "date_first_observed": "2025-01-15T10:30:00Z",
                "source_type": "todoist",
            },
        )

        content = NormalizedContent(
            markdown="Task description.",
            source_id="task-001",
            structural_hints=hints,
            normalizer_version="1.0.0",
        )

        # The domain's chunk() method should raise ValueError for invalid metadata
        with pytest.raises(ValueError, match="Invalid TaskMetadata"):
            tasks_domain.chunk(content)

    def test_chunk_has_correct_context_header_with_due_date(
        self, tasks_domain, sample_task_metadata
    ):
        """chunk() sets context_header to '{title} [due: {due_date}] [{status}]'."""
        hints = StructuralHints(
            has_headings=False,
            has_lists=False,
            has_tables=False,
            natural_boundaries=[],
            extra_metadata=sample_task_metadata.model_dump(),
        )

        content = NormalizedContent(
            markdown="Task description.",
            source_id="task-001",
            structural_hints=hints,
            normalizer_version="1.0.0",
        )

        chunks = tasks_domain.chunk(content)

        assert (
            chunks[0].context_header
            == "Complete project documentation [due: 2025-02-15T23:59:59Z] [open]"
        )

    def test_chunk_has_correct_context_header_without_due_date(self, tasks_domain):
        """chunk() omits due date when due_date is None."""
        meta = TaskMetadata(
            task_id="task-001",
            status="in-progress",
            title="Review code changes",
            due_date=None,  # No due date
            priority=2,
            dependencies=(),
            collaborators=(),
            date_first_observed="2025-01-15T10:30:00Z",
            source_type="github",
        )

        hints = StructuralHints(
            has_headings=False,
            has_lists=False,
            has_tables=False,
            natural_boundaries=[],
            extra_metadata=meta.model_dump(),
        )

        content = NormalizedContent(
            markdown="Review the pull request changes.",
            source_id="task-001",
            structural_hints=hints,
            normalizer_version="1.0.0",
        )

        chunks = tasks_domain.chunk(content)

        assert chunks[0].context_header == "Review code changes [in-progress]"

    def test_chunk_has_domain_metadata(
        self, tasks_domain, sample_task_metadata
    ):
        """chunk() populates domain_metadata with all TaskMetadata fields."""
        hints = StructuralHints(
            has_headings=False,
            has_lists=False,
            has_tables=False,
            natural_boundaries=[],
            extra_metadata=sample_task_metadata.model_dump(),
        )

        content = NormalizedContent(
            markdown="Task description.",
            source_id="task-001",
            structural_hints=hints,
            normalizer_version="1.0.0",
        )

        chunks = tasks_domain.chunk(content)

        assert chunks[0].domain_metadata is not None
        assert chunks[0].domain_metadata["task_id"] == "task-001"
        assert chunks[0].domain_metadata["status"] == "open"
        assert chunks[0].domain_metadata["title"] == "Complete project documentation"
        assert chunks[0].domain_metadata["due_date"] == "2025-02-15T23:59:59Z"
        assert chunks[0].domain_metadata["priority"] == 1
        assert chunks[0].domain_metadata["dependencies"] == ("task-000",)
        assert chunks[0].domain_metadata["collaborators"] == ("alice@example.com",)
        assert chunks[0].domain_metadata["date_first_observed"] == "2025-01-15T10:30:00Z"
        assert chunks[0].domain_metadata["source_type"] == "todoist"

    def test_chunk_type_is_standard(self, tasks_domain, sample_task_metadata):
        """All chunks have chunk_type = ChunkType.STANDARD."""
        hints = StructuralHints(
            has_headings=False,
            has_lists=False,
            has_tables=False,
            natural_boundaries=[],
            extra_metadata=sample_task_metadata.model_dump(),
        )

        content = NormalizedContent(
            markdown="Task description.",
            source_id="task-001",
            structural_hints=hints,
            normalizer_version="1.0.0",
        )

        chunks = tasks_domain.chunk(content)

        assert all(chunk.chunk_type == ChunkType.STANDARD for chunk in chunks)


class TestLongTaskSplitting:
    """Tests for splitting oversized task descriptions."""

    def test_short_task_not_split(self, tasks_domain, sample_task_metadata):
        """Task descriptions under hard_limit are not split."""
        hints = StructuralHints(
            has_headings=False,
            has_lists=False,
            has_tables=False,
            natural_boundaries=[],
            extra_metadata=sample_task_metadata.model_dump(),
        )

        # Create a description with ~500 tokens (under 1024)
        short_description = " ".join(["word"] * 500)

        content = NormalizedContent(
            markdown=short_description,
            source_id="task-001",
            structural_hints=hints,
            normalizer_version="1.0.0",
        )

        chunks = tasks_domain.chunk(content)

        assert len(chunks) == 1

    def test_long_task_split_at_sentence_boundaries(
        self, sample_task_metadata
    ):
        """Task descriptions exceeding hard_limit are split at sentence boundaries."""
        domain = TasksDomain(hard_limit=30)  # Small limit for testing

        hints = StructuralHints(
            has_headings=False,
            has_lists=False,
            has_tables=False,
            natural_boundaries=[],
            extra_metadata=sample_task_metadata.model_dump(),
        )

        # Create a description with multiple sentences totaling ~70 tokens
        markdown = (
            "First sentence with some content and additional details here. "
            "Second sentence also with some content and more information. "
            "Third sentence continues the description with even more details. "
            "Fourth sentence adds more information to the task. "
            "Fifth sentence wraps up the thought about this task."
        )

        content = NormalizedContent(
            markdown=markdown,
            source_id="task-001",
            structural_hints=hints,
            normalizer_version="1.0.0",
        )

        chunks = domain.chunk(content)

        assert len(chunks) > 1
        # All chunks should have content and be under hard_limit
        for chunk in chunks:
            assert len(chunk.content.split()) <= 30

    def test_long_task_chunks_have_sequential_indices(
        self, sample_task_metadata
    ):
        """Split task descriptions have sequential chunk_index values."""
        domain = TasksDomain(hard_limit=30)

        hints = StructuralHints(
            has_headings=False,
            has_lists=False,
            has_tables=False,
            natural_boundaries=[],
            extra_metadata=sample_task_metadata.model_dump(),
        )

        markdown = "word " * 100  # 100 words total

        content = NormalizedContent(
            markdown=markdown,
            source_id="task-001",
            structural_hints=hints,
            normalizer_version="1.0.0",
        )

        chunks = domain.chunk(content)

        for i, chunk in enumerate(chunks):
            assert chunk.chunk_index == i

    def test_oversized_sentence_split_at_word_boundaries(
        self, sample_task_metadata
    ):
        """Sentences exceeding hard_limit are split at word boundaries."""
        domain = TasksDomain(hard_limit=20)

        hints = StructuralHints(
            has_headings=False,
            has_lists=False,
            has_tables=False,
            natural_boundaries=[],
            extra_metadata=sample_task_metadata.model_dump(),
        )

        # Create a single long sentence (40 words)
        markdown = "word " * 40

        content = NormalizedContent(
            markdown=markdown,
            source_id="task-001",
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
        self, tasks_domain, sample_task_metadata
    ):
        """chunk_hash is computed from content, not context_header."""
        hints = StructuralHints(
            has_headings=False,
            has_lists=False,
            has_tables=False,
            natural_boundaries=[],
            extra_metadata=sample_task_metadata.model_dump(),
        )

        content = NormalizedContent(
            markdown="The task description.",
            source_id="task-001",
            structural_hints=hints,
            normalizer_version="1.0.0",
        )

        chunks = tasks_domain.chunk(content)

        # Compute expected hash from content only
        expected_hash = compute_chunk_hash("The task description.")

        assert chunks[0].chunk_hash == expected_hash

    def test_chunk_hash_same_regardless_of_context_header(
        self, tasks_domain, sample_task_metadata
    ):
        """Changing context_header does not change chunk_hash."""
        meta1 = sample_task_metadata
        meta2 = TaskMetadata(
            task_id="task-001",
            status="completed",  # Different status
            title="Different title",  # Different title
            due_date="2025-03-15T23:59:59Z",  # Different due date
            priority=3,
            dependencies=(),
            collaborators=(),
            date_first_observed="2025-01-15T10:30:00Z",
            source_type="todoist",
        )

        hints1 = StructuralHints(
            has_headings=False,
            has_lists=False,
            has_tables=False,
            natural_boundaries=[],
            extra_metadata=meta1.model_dump(),
        )

        hints2 = StructuralHints(
            has_headings=False,
            has_lists=False,
            has_tables=False,
            natural_boundaries=[],
            extra_metadata=meta2.model_dump(),
        )

        content1 = NormalizedContent(
            markdown="The task content.",
            source_id="task-001",
            structural_hints=hints1,
            normalizer_version="1.0.0",
        )

        content2 = NormalizedContent(
            markdown="The task content.",
            source_id="task-001",
            structural_hints=hints2,
            normalizer_version="1.0.0",
        )

        chunks1 = tasks_domain.chunk(content1)
        chunks2 = tasks_domain.chunk(content2)

        # Same content => same hash, even with different context headers
        assert chunks1[0].chunk_hash == chunks2[0].chunk_hash


class TestTaskMetadataValidation:
    """Tests for TaskMetadata validation."""

    def test_chunk_raises_on_invalid_task_id(self, tasks_domain):
        """chunk() raises ValueError when task_id is empty."""
        # TaskMetadata validation should fail
        with pytest.raises(ValueError, match="task_id must be a non-empty string"):
            TaskMetadata(
                task_id="",  # Invalid: empty
                status="open",
                title="Test task",
                due_date=None,
                priority=None,
                dependencies=(),
                collaborators=(),
                date_first_observed="2025-01-15T10:30:00Z",
                source_type="todoist",
            )

    def test_chunk_raises_on_invalid_status(self, tasks_domain):
        """chunk() raises ValueError when status is not in allowed set."""
        with pytest.raises(ValueError, match="status must be one of"):
            TaskMetadata(
                task_id="task-001",
                status="invalid-status",  # Invalid status
                title="Test task",
                due_date=None,
                priority=None,
                dependencies=(),
                collaborators=(),
                date_first_observed="2025-01-15T10:30:00Z",
                source_type="todoist",
            )

    def test_chunk_raises_on_invalid_due_date_format(self, tasks_domain):
        """chunk() raises ValueError when due_date is not valid ISO 8601."""
        with pytest.raises(ValueError, match="ISO 8601"):
            TaskMetadata(
                task_id="task-001",
                status="open",
                title="Test task",
                due_date="not-a-date",  # Invalid format
                priority=None,
                dependencies=(),
                collaborators=(),
                date_first_observed="2025-01-15T10:30:00Z",
                source_type="todoist",
            )

    def test_chunk_raises_on_invalid_date_first_observed(self, tasks_domain):
        """chunk() raises ValueError when date_first_observed is not valid ISO 8601."""
        with pytest.raises(ValueError, match="ISO 8601"):
            TaskMetadata(
                task_id="task-001",
                status="open",
                title="Test task",
                due_date=None,
                priority=None,
                dependencies=(),
                collaborators=(),
                date_first_observed="invalid-date",  # Invalid format
                source_type="todoist",
            )


class TestTaskStatusVariations:
    """Tests for different task statuses."""

    @pytest.mark.parametrize(
        "status",
        ["open", "completed", "cancelled", "in-progress"],
    )
    def test_all_valid_statuses_produce_correct_header(
        self, tasks_domain, status
    ):
        """All valid task statuses are included in context_header."""
        meta = TaskMetadata(
            task_id="task-001",
            status=status,
            title="Test task",
            due_date=None,
            priority=None,
            dependencies=(),
            collaborators=(),
            date_first_observed="2025-01-15T10:30:00Z",
            source_type="todoist",
        )

        hints = StructuralHints(
            has_headings=False,
            has_lists=False,
            has_tables=False,
            natural_boundaries=[],
            extra_metadata=meta.model_dump(),
        )

        content = NormalizedContent(
            markdown="Task description.",
            source_id="task-001",
            structural_hints=hints,
            normalizer_version="1.0.0",
        )

        chunks = tasks_domain.chunk(content)

        assert f"[{status}]" in chunks[0].context_header
