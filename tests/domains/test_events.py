"""Tests for the events domain."""

import pytest

from context_library.domains.events import EventsDomain
from context_library.domains.registry import Domain, get_domain_chunker
from context_library.storage.models import (
    Chunk,
    ChunkType,
    EventMetadata,
    NormalizedContent,
    StructuralHints,
    compute_chunk_hash,
)


@pytest.fixture
def events_domain():
    """Create an EventsDomain instance with default limits."""
    return EventsDomain(hard_limit=1024)


@pytest.fixture
def sample_event_metadata():
    """Create sample EventMetadata for testing."""
    return EventMetadata(
        event_id="event-001",
        title="Team Standup Meeting",
        start_date="2025-02-15T10:00:00Z",
        end_date="2025-02-15T10:30:00Z",
        duration_minutes=30,
        host="alice@example.com",
        invitees=("bob@example.com", "charlie@example.com"),
        date_first_observed="2025-01-15T10:30:00Z",
        source_type="google_calendar",
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


class TestEventsDomainRegistry:
    """Tests for EventsDomain domain registry integration."""

    def test_domain_chunker_registry_returns_events_domain(self):
        """get_domain_chunker(Domain.EVENTS) returns an EventsDomain instance."""
        domain = get_domain_chunker(Domain.EVENTS)

        assert isinstance(domain, EventsDomain)
        assert domain.hard_limit == 1024


class TestEventsDomainBasics:
    """Basic tests for EventsDomain initialization and properties."""

    def test_initialization_with_defaults(self):
        """EventsDomain initializes with default hard_limit."""
        domain = EventsDomain()

        assert domain.hard_limit == 1024

    def test_initialization_with_custom_limit(self):
        """EventsDomain initializes with custom hard_limit."""
        domain = EventsDomain(hard_limit=512)

        assert domain.hard_limit == 512

    def test_initialization_rejects_zero_hard_limit(self):
        """EventsDomain rejects hard_limit=0."""
        with pytest.raises(ValueError, match="hard_limit must be a positive integer"):
            EventsDomain(hard_limit=0)

    def test_initialization_rejects_negative_hard_limit(self):
        """EventsDomain rejects negative hard_limit."""
        with pytest.raises(ValueError, match="hard_limit must be a positive integer"):
            EventsDomain(hard_limit=-1)

    def test_initialization_rejects_negative_hard_limit_large(self):
        """EventsDomain rejects large negative hard_limit."""
        with pytest.raises(ValueError, match="hard_limit must be a positive integer"):
            EventsDomain(hard_limit=-1024)

    def test_chunk_returns_list_of_chunks(
        self, events_domain, sample_event_metadata, base_structural_hints
    ):
        """chunk() returns a list of Chunk instances."""
        hints = StructuralHints(
            has_headings=False,
            has_lists=False,
            has_tables=False,
            natural_boundaries=[],
            extra_metadata=sample_event_metadata.model_dump(),
        )

        content = NormalizedContent(
            markdown="This is an event description with some details.",
            source_id="event-001",
            structural_hints=hints,
            normalizer_version="1.0.0",
        )

        result = events_domain.chunk(content)

        assert isinstance(result, list)
        assert all(isinstance(chunk, Chunk) for chunk in result)
        assert len(result) >= 1

    def test_chunk_raises_without_extra_metadata(
        self, events_domain, base_structural_hints
    ):
        """chunk() raises ValueError if extra_metadata is missing."""
        content = NormalizedContent(
            markdown="Test event",
            source_id="event-001",
            structural_hints=base_structural_hints,
            normalizer_version="1.0.0",
        )

        with pytest.raises(ValueError, match="extra_metadata"):
            events_domain.chunk(content)


class TestSingleEventChunk:
    """Tests for chunking single events."""

    def test_single_event_with_title_and_description_creates_one_chunk(
        self, events_domain, sample_event_metadata
    ):
        """An event with title and description creates exactly one chunk."""
        hints = StructuralHints(
            has_headings=False,
            has_lists=False,
            has_tables=False,
            natural_boundaries=[],
            extra_metadata=sample_event_metadata.model_dump(),
        )

        content = NormalizedContent(
            markdown="This is the event description with important details.",
            source_id="event-001",
            structural_hints=hints,
            normalizer_version="1.0.0",
        )

        chunks = events_domain.chunk(content)

        assert len(chunks) == 1
        assert chunks[0].content == "This is the event description with important details."
        assert chunks[0].chunk_index == 0

    def test_event_with_title_but_no_description_returns_empty_list(
        self, events_domain, sample_event_metadata
    ):
        """An event with only a title (no description) returns an empty list per spec."""
        hints = StructuralHints(
            has_headings=False,
            has_lists=False,
            has_tables=False,
            natural_boundaries=[],
            extra_metadata=sample_event_metadata.model_dump(),
        )

        # Empty markdown (no description)
        content = NormalizedContent(
            markdown="",
            source_id="event-001",
            structural_hints=hints,
            normalizer_version="1.0.0",
        )

        chunks = events_domain.chunk(content)

        # Per spec: events with no description content should return empty list
        assert len(chunks) == 0

    def test_event_with_whitespace_only_description_returns_empty_list(
        self, events_domain, sample_event_metadata
    ):
        """An event with whitespace-only description returns an empty list per spec."""
        hints = StructuralHints(
            has_headings=False,
            has_lists=False,
            has_tables=False,
            natural_boundaries=[],
            extra_metadata=sample_event_metadata.model_dump(),
        )

        content = NormalizedContent(
            markdown="   \n\t\n   ",
            source_id="event-001",
            structural_hints=hints,
            normalizer_version="1.0.0",
        )

        chunks = events_domain.chunk(content)

        # Per spec: events with no description content (including whitespace-only) should return empty list
        assert len(chunks) == 0

    def test_event_with_neither_title_nor_description_returns_empty_list(
        self, events_domain
    ):
        """An event with empty title cannot be created - title is required."""
        # EventMetadata validation requires title to be non-empty,
        # so we can't even create an event with empty title
        with pytest.raises(ValueError, match="title must be a non-empty string"):
            EventMetadata(
                event_id="event-001",
                title="",  # Empty title
                start_date=None,
                end_date=None,
                duration_minutes=None,
                host=None,
                invitees=(),
                date_first_observed="2025-01-15T10:30:00Z",
                source_type="google_calendar",
            )

    def test_chunk_raises_on_invalid_metadata_from_domain(
        self, events_domain, base_structural_hints
    ):
        """chunk() raises ValueError when extra_metadata contains invalid EventMetadata."""
        # Create hints with invalid extra_metadata (empty title)
        hints = StructuralHints(
            has_headings=False,
            has_lists=False,
            has_tables=False,
            natural_boundaries=[],
            extra_metadata={
                "event_id": "event-001",
                "title": "",  # Invalid: empty title
                "start_date": None,
                "end_date": None,
                "duration_minutes": None,
                "host": None,
                "invitees": (),
                "date_first_observed": "2025-01-15T10:30:00Z",
                "source_type": "google_calendar",
            },
        )

        content = NormalizedContent(
            markdown="Event description.",
            source_id="event-001",
            structural_hints=hints,
            normalizer_version="1.0.0",
        )

        # The domain's chunk() method should raise ValueError for invalid metadata
        with pytest.raises(ValueError, match="Invalid EventMetadata"):
            events_domain.chunk(content)

    def test_chunk_has_correct_context_header_with_start_date(
        self, events_domain, sample_event_metadata
    ):
        """chunk() sets context_header to '{title} — {start_date}' when start_date is present."""
        hints = StructuralHints(
            has_headings=False,
            has_lists=False,
            has_tables=False,
            natural_boundaries=[],
            extra_metadata=sample_event_metadata.model_dump(),
        )

        content = NormalizedContent(
            markdown="Event description.",
            source_id="event-001",
            structural_hints=hints,
            normalizer_version="1.0.0",
        )

        chunks = events_domain.chunk(content)

        assert (
            chunks[0].context_header
            == "Team Standup Meeting — 2025-02-15T10:00:00Z"
        )

    def test_chunk_has_correct_context_header_without_start_date(self, events_domain):
        """chunk() omits start date when start_date is None."""
        meta = EventMetadata(
            event_id="event-001",
            title="Informal Chat",
            start_date=None,  # No start date
            end_date=None,
            duration_minutes=None,
            host=None,
            invitees=(),
            date_first_observed="2025-01-15T10:30:00Z",
            source_type="slack",
        )

        hints = StructuralHints(
            has_headings=False,
            has_lists=False,
            has_tables=False,
            natural_boundaries=[],
            extra_metadata=meta.model_dump(),
        )

        content = NormalizedContent(
            markdown="Chat description.",
            source_id="event-001",
            structural_hints=hints,
            normalizer_version="1.0.0",
        )

        chunks = events_domain.chunk(content)

        assert chunks[0].context_header == "Informal Chat"

    def test_chunk_has_domain_metadata(
        self, events_domain, sample_event_metadata
    ):
        """chunk() populates domain_metadata with all EventMetadata fields."""
        hints = StructuralHints(
            has_headings=False,
            has_lists=False,
            has_tables=False,
            natural_boundaries=[],
            extra_metadata=sample_event_metadata.model_dump(),
        )

        content = NormalizedContent(
            markdown="Event description.",
            source_id="event-001",
            structural_hints=hints,
            normalizer_version="1.0.0",
        )

        chunks = events_domain.chunk(content)

        assert chunks[0].domain_metadata is not None
        assert chunks[0].domain_metadata["event_id"] == "event-001"
        assert chunks[0].domain_metadata["title"] == "Team Standup Meeting"
        assert chunks[0].domain_metadata["start_date"] == "2025-02-15T10:00:00Z"
        assert chunks[0].domain_metadata["end_date"] == "2025-02-15T10:30:00Z"
        assert chunks[0].domain_metadata["duration_minutes"] == 30
        assert chunks[0].domain_metadata["host"] == "alice@example.com"
        assert chunks[0].domain_metadata["invitees"] == ("bob@example.com", "charlie@example.com")
        assert chunks[0].domain_metadata["date_first_observed"] == "2025-01-15T10:30:00Z"
        assert chunks[0].domain_metadata["source_type"] == "google_calendar"

    def test_chunk_type_is_standard(self, events_domain, sample_event_metadata):
        """All chunks have chunk_type = ChunkType.STANDARD."""
        hints = StructuralHints(
            has_headings=False,
            has_lists=False,
            has_tables=False,
            natural_boundaries=[],
            extra_metadata=sample_event_metadata.model_dump(),
        )

        content = NormalizedContent(
            markdown="Event description.",
            source_id="event-001",
            structural_hints=hints,
            normalizer_version="1.0.0",
        )

        chunks = events_domain.chunk(content)

        assert all(chunk.chunk_type == ChunkType.STANDARD for chunk in chunks)


class TestLongEventSplitting:
    """Tests for splitting oversized event descriptions."""

    def test_short_event_not_split(self, events_domain, sample_event_metadata):
        """Event descriptions under hard_limit are not split."""
        hints = StructuralHints(
            has_headings=False,
            has_lists=False,
            has_tables=False,
            natural_boundaries=[],
            extra_metadata=sample_event_metadata.model_dump(),
        )

        # Create a description with ~500 tokens (under 1024)
        short_description = " ".join(["word"] * 500)

        content = NormalizedContent(
            markdown=short_description,
            source_id="event-001",
            structural_hints=hints,
            normalizer_version="1.0.0",
        )

        chunks = events_domain.chunk(content)

        assert len(chunks) == 1

    def test_long_event_split_at_sentence_boundaries(
        self, sample_event_metadata
    ):
        """Event descriptions exceeding hard_limit are split at sentence boundaries."""
        domain = EventsDomain(hard_limit=30)  # Small limit for testing

        hints = StructuralHints(
            has_headings=False,
            has_lists=False,
            has_tables=False,
            natural_boundaries=[],
            extra_metadata=sample_event_metadata.model_dump(),
        )

        # Create a description with multiple sentences totaling ~70 tokens
        markdown = (
            "First sentence with some content and additional details here. "
            "Second sentence also with some content and more information. "
            "Third sentence continues the description with even more details. "
            "Fourth sentence adds more information to the event. "
            "Fifth sentence wraps up the thought about this event."
        )

        content = NormalizedContent(
            markdown=markdown,
            source_id="event-001",
            structural_hints=hints,
            normalizer_version="1.0.0",
        )

        chunks = domain.chunk(content)

        assert len(chunks) > 1
        # All chunks should have content and be under hard_limit
        for chunk in chunks:
            assert len(chunk.content.split()) <= 30

    def test_long_event_chunks_have_sequential_indices(
        self, sample_event_metadata
    ):
        """Split event descriptions have sequential chunk_index values."""
        domain = EventsDomain(hard_limit=30)

        hints = StructuralHints(
            has_headings=False,
            has_lists=False,
            has_tables=False,
            natural_boundaries=[],
            extra_metadata=sample_event_metadata.model_dump(),
        )

        markdown = "word " * 100  # 100 words total

        content = NormalizedContent(
            markdown=markdown,
            source_id="event-001",
            structural_hints=hints,
            normalizer_version="1.0.0",
        )

        chunks = domain.chunk(content)

        for i, chunk in enumerate(chunks):
            assert chunk.chunk_index == i

    def test_oversized_sentence_split_at_word_boundaries(
        self, sample_event_metadata
    ):
        """Sentences exceeding hard_limit are split at word boundaries."""
        domain = EventsDomain(hard_limit=20)

        hints = StructuralHints(
            has_headings=False,
            has_lists=False,
            has_tables=False,
            natural_boundaries=[],
            extra_metadata=sample_event_metadata.model_dump(),
        )

        # Create a single long sentence (40 words)
        markdown = "word " * 40

        content = NormalizedContent(
            markdown=markdown,
            source_id="event-001",
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
        self, events_domain, sample_event_metadata
    ):
        """chunk_hash is computed from content, not context_header."""
        hints = StructuralHints(
            has_headings=False,
            has_lists=False,
            has_tables=False,
            natural_boundaries=[],
            extra_metadata=sample_event_metadata.model_dump(),
        )

        content = NormalizedContent(
            markdown="The event description.",
            source_id="event-001",
            structural_hints=hints,
            normalizer_version="1.0.0",
        )

        chunks = events_domain.chunk(content)

        # Compute expected hash from content only
        expected_hash = compute_chunk_hash("The event description.")

        assert chunks[0].chunk_hash == expected_hash

    def test_chunk_hash_same_regardless_of_context_header(
        self, events_domain, sample_event_metadata
    ):
        """Changing context_header does not change chunk_hash."""
        meta1 = sample_event_metadata
        meta2 = EventMetadata(
            event_id="event-001",
            title="Different Title",  # Different title
            start_date="2025-03-15T14:00:00Z",  # Different start date
            end_date=None,
            duration_minutes=None,
            host="bob@example.com",  # Different host
            invitees=(),
            date_first_observed="2025-01-15T10:30:00Z",
            source_type="outlook",
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
            markdown="The event content.",
            source_id="event-001",
            structural_hints=hints1,
            normalizer_version="1.0.0",
        )

        content2 = NormalizedContent(
            markdown="The event content.",
            source_id="event-001",
            structural_hints=hints2,
            normalizer_version="1.0.0",
        )

        chunks1 = events_domain.chunk(content1)
        chunks2 = events_domain.chunk(content2)

        # Same content => same hash, even with different context headers
        assert chunks1[0].chunk_hash == chunks2[0].chunk_hash


class TestEventMetadataValidation:
    """Tests for EventMetadata validation."""

    def test_chunk_raises_on_invalid_event_id(self, events_domain):
        """chunk() raises ValueError when event_id is empty."""
        # EventMetadata validation should fail
        with pytest.raises(ValueError, match="event_id must be a non-empty string"):
            EventMetadata(
                event_id="",  # Invalid: empty
                title="Test event",
                start_date=None,
                end_date=None,
                duration_minutes=None,
                host=None,
                invitees=(),
                date_first_observed="2025-01-15T10:30:00Z",
                source_type="google_calendar",
            )

    def test_chunk_raises_on_invalid_start_date_format(self, events_domain):
        """chunk() raises ValueError when start_date is not valid ISO 8601."""
        with pytest.raises(ValueError, match="ISO 8601"):
            EventMetadata(
                event_id="event-001",
                title="Test event",
                start_date="not-a-date",  # Invalid format
                end_date=None,
                duration_minutes=None,
                host=None,
                invitees=(),
                date_first_observed="2025-01-15T10:30:00Z",
                source_type="google_calendar",
            )

    def test_chunk_raises_on_invalid_end_date_format(self, events_domain):
        """chunk() raises ValueError when end_date is not valid ISO 8601."""
        with pytest.raises(ValueError, match="ISO 8601"):
            EventMetadata(
                event_id="event-001",
                title="Test event",
                start_date="2025-02-15T10:00:00Z",
                end_date="not-a-date",  # Invalid format
                duration_minutes=None,
                host=None,
                invitees=(),
                date_first_observed="2025-01-15T10:30:00Z",
                source_type="google_calendar",
            )

    def test_chunk_raises_on_invalid_date_first_observed(self, events_domain):
        """chunk() raises ValueError when date_first_observed is not valid ISO 8601."""
        with pytest.raises(ValueError, match="ISO 8601"):
            EventMetadata(
                event_id="event-001",
                title="Test event",
                start_date=None,
                end_date=None,
                duration_minutes=None,
                host=None,
                invitees=(),
                date_first_observed="invalid-date",  # Invalid format
                source_type="google_calendar",
            )

    def test_chunk_raises_on_start_date_after_end_date(self, events_domain):
        """chunk() raises ValueError when start_date > end_date."""
        with pytest.raises(ValueError, match="start_date must be <= end_date"):
            EventMetadata(
                event_id="event-001",
                title="Test event",
                start_date="2025-02-15T14:00:00Z",  # After end_date
                end_date="2025-02-15T10:00:00Z",
                duration_minutes=None,
                host=None,
                invitees=(),
                date_first_observed="2025-01-15T10:30:00Z",
                source_type="google_calendar",
            )


class TestEventSourceTypeVariations:
    """Tests for different event source types."""

    @pytest.mark.parametrize(
        "source_type",
        ["google_calendar", "outlook", "slack", "zoom", "custom"],
    )
    def test_all_source_types_produce_valid_chunks(
        self, events_domain, source_type
    ):
        """All event source types produce valid chunks with domain_metadata."""
        meta = EventMetadata(
            event_id="event-001",
            title="Test event",
            start_date="2025-02-15T10:00:00Z",
            end_date=None,
            duration_minutes=None,
            host=None,
            invitees=(),
            date_first_observed="2025-01-15T10:30:00Z",
            source_type=source_type,
        )

        hints = StructuralHints(
            has_headings=False,
            has_lists=False,
            has_tables=False,
            natural_boundaries=[],
            extra_metadata=meta.model_dump(),
        )

        content = NormalizedContent(
            markdown="Event description.",
            source_id="event-001",
            structural_hints=hints,
            normalizer_version="1.0.0",
        )

        chunks = events_domain.chunk(content)

        assert len(chunks) == 1
        assert chunks[0].domain_metadata["source_type"] == source_type


class TestHealthSpecificMetadataPreservation:
    """Tests for preservation of health-specific metadata fields."""

    def test_apple_health_extra_fields_preserved_in_domain_metadata(
        self, events_domain
    ):
        """Health-specific extra fields are preserved in domain_metadata.

        This tests the fix for the metadata loss issue where Apple Health metrics
        (calories_kcal, distance_meters, avg_heart_rate_bpm) were being silently
        dropped during chunking due to EventMetadata's extra="ignore" config.
        """
        # Simulate Apple Health adapter's event_metadata_dict with health-specific fields
        health_metadata = {
            "event_id": "workout-123",
            "title": "Running",
            "start_date": "2025-03-07T10:00:00Z",
            "end_date": "2025-03-07T10:30:00Z",
            "duration_minutes": 30,
            "host": None,
            "invitees": [],
            "date_first_observed": "2025-03-08T12:00:00Z",
            "source_type": "apple_health",
            # Health-specific extras that should be preserved
            "calories_kcal": 250.5,
            "distance_meters": 5000.0,
            "avg_heart_rate_bpm": 145.0,
        }

        hints = StructuralHints(
            has_headings=False,
            has_lists=True,
            has_tables=False,
            natural_boundaries=[],
            extra_metadata=health_metadata,
        )

        content = NormalizedContent(
            markdown="**Running**\n- Calories: 250 kcal\n- Distance: 5.00 km\n- Avg heart rate: 145 bpm\n- Duration: 30 minutes",
            source_id="running/workout-123",
            structural_hints=hints,
            normalizer_version="1.0.0",
        )

        chunks = events_domain.chunk(content)

        # Verify the chunk has domain_metadata with all fields including extras
        assert len(chunks) == 1
        assert chunks[0].domain_metadata is not None

        # Standard EventMetadata fields
        assert chunks[0].domain_metadata["event_id"] == "workout-123"
        assert chunks[0].domain_metadata["title"] == "Running"
        assert chunks[0].domain_metadata["source_type"] == "apple_health"

        # Health-specific extra fields must be preserved
        assert "calories_kcal" in chunks[0].domain_metadata, "calories_kcal field lost during chunking"
        assert chunks[0].domain_metadata["calories_kcal"] == 250.5

        assert "distance_meters" in chunks[0].domain_metadata, "distance_meters field lost during chunking"
        assert chunks[0].domain_metadata["distance_meters"] == 5000.0

        assert "avg_heart_rate_bpm" in chunks[0].domain_metadata, "avg_heart_rate_bpm field lost during chunking"
        assert chunks[0].domain_metadata["avg_heart_rate_bpm"] == 145.0
