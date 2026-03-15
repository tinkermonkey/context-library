"""Tests for the health domain."""

import pytest

from context_library.domains.health import HealthDomain
from context_library.domains.registry import Domain, get_domain_chunker
from context_library.storage.models import (
    Chunk,
    ChunkType,
    HealthMetadata,
    NormalizedContent,
    StructuralHints,
    compute_chunk_hash,
)


@pytest.fixture
def health_domain():
    """Create a HealthDomain instance with default limits."""
    return HealthDomain(hard_limit=1024)


@pytest.fixture
def sample_health_metadata():
    """Create sample HealthMetadata for testing."""
    return HealthMetadata(
        record_id="health-001",
        health_type="sleep_summary",
        date="2026-03-07",
        source_type="apple_health",
        date_first_observed="2026-03-07T08:00:00Z",
        duration_minutes=480,
        score=85.5,
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


class TestHealthDomainRegistry:
    """Tests for HealthDomain domain registry integration."""

    def test_domain_chunker_registry_returns_health_domain(self):
        """get_domain_chunker(Domain.HEALTH) returns a HealthDomain instance."""
        domain = get_domain_chunker(Domain.HEALTH)

        assert isinstance(domain, HealthDomain)
        assert domain.hard_limit == 1024


class TestHealthDomainBasics:
    """Basic tests for HealthDomain initialization and properties."""

    def test_initialization_with_defaults(self):
        """HealthDomain initializes with default hard_limit."""
        domain = HealthDomain()

        assert domain.hard_limit == 1024

    def test_initialization_with_custom_hard_limit(self):
        """HealthDomain initializes with custom hard_limit."""
        domain = HealthDomain(hard_limit=512)

        assert domain.hard_limit == 512

    def test_initialization_rejects_zero_hard_limit(self):
        """HealthDomain rejects hard_limit=0."""
        with pytest.raises(ValueError, match="hard_limit must be a positive integer"):
            HealthDomain(hard_limit=0)

    def test_initialization_rejects_negative_hard_limit(self):
        """HealthDomain rejects negative hard_limit."""
        with pytest.raises(ValueError, match="hard_limit must be a positive integer"):
            HealthDomain(hard_limit=-1)

    def test_chunk_returns_list_of_chunks(
        self, health_domain, sample_health_metadata, base_structural_hints
    ):
        """chunk() returns a list of Chunk instances."""
        hints = StructuralHints(
            has_headings=False,
            has_lists=False,
            has_tables=False,
            natural_boundaries=[],
            extra_metadata=sample_health_metadata.model_dump(),
        )

        content = NormalizedContent(
            markdown="Sleep quality was excellent with deep sleep phases.",
            source_id="apple_health_1",
            structural_hints=hints,
            normalizer_version="1.0.0",
        )

        result = health_domain.chunk(content)

        assert isinstance(result, list)
        assert all(isinstance(chunk, Chunk) for chunk in result)
        assert len(result) >= 1

    def test_chunk_raises_without_extra_metadata(
        self, health_domain, base_structural_hints
    ):
        """chunk() raises ValueError if extra_metadata is missing."""
        content = NormalizedContent(
            markdown="Health data",
            source_id="health_1",
            structural_hints=base_structural_hints,
            normalizer_version="1.0.0",
        )

        with pytest.raises(ValueError, match="extra_metadata"):
            health_domain.chunk(content)


class TestSingleHealthChunk:
    """Tests for chunking single health records."""

    def test_single_sleep_record_creates_one_chunk(
        self, health_domain, sample_health_metadata
    ):
        """A single sleep record creates exactly one chunk."""
        hints = StructuralHints(
            has_headings=False,
            has_lists=False,
            has_tables=False,
            natural_boundaries=[],
            extra_metadata=sample_health_metadata.model_dump(),
        )

        content = NormalizedContent(
            markdown="Sleep quality was excellent.",
            source_id="health_1",
            structural_hints=hints,
            normalizer_version="1.0.0",
        )

        chunks = health_domain.chunk(content)

        assert len(chunks) == 1
        assert chunks[0].content == "Sleep quality was excellent."
        assert chunks[0].chunk_index == 0

    def test_health_record_with_empty_markdown_returns_empty_list(
        self, health_domain, sample_health_metadata
    ):
        """A health record with empty markdown returns an empty list."""
        hints = StructuralHints(
            has_headings=False,
            has_lists=False,
            has_tables=False,
            natural_boundaries=[],
            extra_metadata=sample_health_metadata.model_dump(),
        )

        content = NormalizedContent(
            markdown="",
            source_id="health_1",
            structural_hints=hints,
            normalizer_version="1.0.0",
        )

        chunks = health_domain.chunk(content)

        assert len(chunks) == 0

    def test_health_record_with_whitespace_only_returns_empty_list(
        self, health_domain, sample_health_metadata
    ):
        """A health record with whitespace-only markdown returns an empty list."""
        hints = StructuralHints(
            has_headings=False,
            has_lists=False,
            has_tables=False,
            natural_boundaries=[],
            extra_metadata=sample_health_metadata.model_dump(),
        )

        content = NormalizedContent(
            markdown="   \n\t\n   ",
            source_id="health_1",
            structural_hints=hints,
            normalizer_version="1.0.0",
        )

        chunks = health_domain.chunk(content)

        assert len(chunks) == 0

    def test_chunk_has_correct_context_header_format(
        self, health_domain, sample_health_metadata
    ):
        """chunk() sets context_header to '{health_type} — {date}' format."""
        hints = StructuralHints(
            has_headings=False,
            has_lists=False,
            has_tables=False,
            natural_boundaries=[],
            extra_metadata=sample_health_metadata.model_dump(),
        )

        content = NormalizedContent(
            markdown="Health data.",
            source_id="health_1",
            structural_hints=hints,
            normalizer_version="1.0.0",
        )

        chunks = health_domain.chunk(content)

        assert chunks[0].context_header == "sleep_summary — 2026-03-07"

    def test_chunk_has_domain_metadata(
        self, health_domain, sample_health_metadata
    ):
        """chunk() populates domain_metadata with all HealthMetadata fields."""
        hints = StructuralHints(
            has_headings=False,
            has_lists=False,
            has_tables=False,
            natural_boundaries=[],
            extra_metadata=sample_health_metadata.model_dump(),
        )

        content = NormalizedContent(
            markdown="Health data.",
            source_id="health_1",
            structural_hints=hints,
            normalizer_version="1.0.0",
        )

        chunks = health_domain.chunk(content)

        assert chunks[0].domain_metadata is not None
        assert chunks[0].domain_metadata["record_id"] == "health-001"
        assert chunks[0].domain_metadata["health_type"] == "sleep_summary"
        assert chunks[0].domain_metadata["date"] == "2026-03-07"
        assert chunks[0].domain_metadata["source_type"] == "apple_health"
        assert chunks[0].domain_metadata["duration_minutes"] == 480
        assert chunks[0].domain_metadata["score"] == 85.5

    def test_chunk_type_is_standard(self, health_domain, sample_health_metadata):
        """All chunks have chunk_type = ChunkType.STANDARD."""
        hints = StructuralHints(
            has_headings=False,
            has_lists=False,
            has_tables=False,
            natural_boundaries=[],
            extra_metadata=sample_health_metadata.model_dump(),
        )

        content = NormalizedContent(
            markdown="Health data.",
            source_id="health_1",
            structural_hints=hints,
            normalizer_version="1.0.0",
        )

        chunks = health_domain.chunk(content)

        assert all(chunk.chunk_type == ChunkType.STANDARD for chunk in chunks)


class TestContextHeaderFormat:
    """Tests for context header formatting across different health types."""

    @pytest.mark.parametrize(
        "health_type",
        [
            "sleep_summary",
            "readiness_summary",
            "activity_summary",
            "workout_session",
            "heart_rate_series",
            "spo2_summary",
            "mindfulness_session",
            "user_health_tag",
        ],
    )
    def test_context_header_format_for_all_health_types(
        self, health_domain, health_type
    ):
        """Context header is correctly formatted for all health types."""
        meta = HealthMetadata(
            record_id="health-001",
            health_type=health_type,
            date="2026-03-07",
            source_type="apple_health",
            date_first_observed="2026-03-07T08:00:00Z",
        )

        hints = StructuralHints(
            has_headings=False,
            has_lists=False,
            has_tables=False,
            natural_boundaries=[],
            extra_metadata=meta.model_dump(),
        )

        content = NormalizedContent(
            markdown="Health data.",
            source_id="health_1",
            structural_hints=hints,
            normalizer_version="1.0.0",
        )

        chunks = health_domain.chunk(content)

        assert chunks[0].context_header == f"{health_type} — 2026-03-07"


class TestLongHealthSplitting:
    """Tests for splitting oversized health records."""

    def test_short_health_record_not_split(self, health_domain, sample_health_metadata):
        """Health records under hard_limit are not split."""
        hints = StructuralHints(
            has_headings=False,
            has_lists=False,
            has_tables=False,
            natural_boundaries=[],
            extra_metadata=sample_health_metadata.model_dump(),
        )

        # Create content with ~500 tokens (under 1024)
        short_content = " ".join(["word"] * 500)

        content = NormalizedContent(
            markdown=short_content,
            source_id="health_1",
            structural_hints=hints,
            normalizer_version="1.0.0",
        )

        chunks = health_domain.chunk(content)

        assert len(chunks) == 1

    def test_long_health_record_split_at_sentence_boundaries(
        self, sample_health_metadata
    ):
        """Health records exceeding hard_limit are split at sentence boundaries."""
        domain = HealthDomain(hard_limit=30)  # Small limit for testing

        hints = StructuralHints(
            has_headings=False,
            has_lists=False,
            has_tables=False,
            natural_boundaries=[],
            extra_metadata=sample_health_metadata.model_dump(),
        )

        # Create content with multiple sentences totaling ~70 tokens
        markdown = (
            "First sentence with some content and additional details here. "
            "Second sentence also with some content and more information. "
            "Third sentence continues the description with even more details. "
            "Fourth sentence adds more information to the record. "
            "Fifth sentence wraps up the health data."
        )

        content = NormalizedContent(
            markdown=markdown,
            source_id="health_1",
            structural_hints=hints,
            normalizer_version="1.0.0",
        )

        chunks = domain.chunk(content)

        assert len(chunks) > 1
        # All chunks should have content and be under hard_limit
        for chunk in chunks:
            assert len(chunk.content.split()) <= 30

    def test_long_health_chunks_have_sequential_indices(
        self, sample_health_metadata
    ):
        """Split health records have sequential chunk_index values."""
        domain = HealthDomain(hard_limit=30)

        hints = StructuralHints(
            has_headings=False,
            has_lists=False,
            has_tables=False,
            natural_boundaries=[],
            extra_metadata=sample_health_metadata.model_dump(),
        )

        markdown = "word " * 100  # 100 words total

        content = NormalizedContent(
            markdown=markdown,
            source_id="health_1",
            structural_hints=hints,
            normalizer_version="1.0.0",
        )

        chunks = domain.chunk(content)

        for i, chunk in enumerate(chunks):
            assert chunk.chunk_index == i


class TestChunkHash:
    """Tests for chunk hash computation."""

    def test_chunk_hash_computed_from_content_only(
        self, health_domain, sample_health_metadata
    ):
        """chunk_hash is computed from content, not context_header."""
        hints = StructuralHints(
            has_headings=False,
            has_lists=False,
            has_tables=False,
            natural_boundaries=[],
            extra_metadata=sample_health_metadata.model_dump(),
        )

        content = NormalizedContent(
            markdown="The health data description.",
            source_id="health_1",
            structural_hints=hints,
            normalizer_version="1.0.0",
        )

        chunks = health_domain.chunk(content)

        # Compute expected hash from content only
        expected_hash = compute_chunk_hash("The health data description.")

        assert chunks[0].chunk_hash == expected_hash

    def test_chunk_hash_determinism_across_calls(
        self, health_domain, sample_health_metadata
    ):
        """Chunk hashes are deterministic across multiple calls with same input."""
        hints = StructuralHints(
            has_headings=False,
            has_lists=False,
            has_tables=False,
            natural_boundaries=[],
            extra_metadata=sample_health_metadata.model_dump(),
        )

        content = NormalizedContent(
            markdown="The health data description.",
            source_id="health_1",
            structural_hints=hints,
            normalizer_version="1.0.0",
        )

        chunks1 = health_domain.chunk(content)
        chunks2 = health_domain.chunk(content)

        assert chunks1[0].chunk_hash == chunks2[0].chunk_hash

    def test_chunk_hash_same_regardless_of_date(self, health_domain):
        """Changing date (context_header) does not change chunk_hash."""
        meta1 = HealthMetadata(
            record_id="health-001",
            health_type="sleep_summary",
            date="2026-03-07",
            source_type="apple_health",
            date_first_observed="2026-03-07T08:00:00Z",
        )

        meta2 = HealthMetadata(
            record_id="health-001",
            health_type="sleep_summary",
            date="2026-03-08",  # Different date
            source_type="apple_health",
            date_first_observed="2026-03-08T08:00:00Z",
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
            markdown="The health content.",
            source_id="health_1",
            structural_hints=hints1,
            normalizer_version="1.0.0",
        )

        content2 = NormalizedContent(
            markdown="The health content.",
            source_id="health_1",
            structural_hints=hints2,
            normalizer_version="1.0.0",
        )

        chunks1 = health_domain.chunk(content1)
        chunks2 = health_domain.chunk(content2)

        # Same content => same hash, even with different dates
        assert chunks1[0].chunk_hash == chunks2[0].chunk_hash


class TestHealthMetadataValidation:
    """Tests for HealthMetadata validation."""

    def test_chunk_raises_on_invalid_record_id(self, health_domain):
        """chunk() raises ValueError when record_id is empty."""
        with pytest.raises(ValueError, match="record_id must be a non-empty string"):
            HealthMetadata(
                record_id="",  # Invalid: empty
                health_type="sleep_summary",
                date="2026-03-07",
                source_type="apple_health",
                date_first_observed="2026-03-07T08:00:00Z",
            )

    def test_chunk_raises_on_invalid_health_type(self, health_domain):
        """chunk() raises ValueError when health_type is not in ALLOWED_TYPES."""
        with pytest.raises(ValueError, match="health_type must be one of"):
            HealthMetadata(
                record_id="health-001",
                health_type="invalid_type",  # Invalid: not in ALLOWED_TYPES
                date="2026-03-07",
                source_type="apple_health",
                date_first_observed="2026-03-07T08:00:00Z",
            )

    def test_chunk_raises_on_invalid_date_format(self, health_domain):
        """chunk() raises ValueError when date is not valid ISO 8601."""
        with pytest.raises(ValueError, match="date must be a valid ISO 8601 date"):
            HealthMetadata(
                record_id="health-001",
                health_type="sleep_summary",
                date="not-a-date",  # Invalid format
                source_type="apple_health",
                date_first_observed="2026-03-07T08:00:00Z",
            )

    def test_chunk_raises_on_invalid_source_type(self, health_domain):
        """chunk() raises ValueError when source_type is empty."""
        with pytest.raises(ValueError, match="source_type must be a non-empty string"):
            HealthMetadata(
                record_id="health-001",
                health_type="sleep_summary",
                date="2026-03-07",
                source_type="",  # Invalid: empty
                date_first_observed="2026-03-07T08:00:00Z",
            )

    def test_chunk_raises_on_invalid_date_first_observed(self, health_domain):
        """chunk() raises ValueError when date_first_observed is not valid ISO 8601."""
        with pytest.raises(ValueError, match="ISO 8601"):
            HealthMetadata(
                record_id="health-001",
                health_type="sleep_summary",
                date="2026-03-07",
                source_type="apple_health",
                date_first_observed="invalid-date",  # Invalid format
            )

    def test_chunk_raises_on_invalid_duration_minutes(self, health_domain):
        """chunk() raises ValueError when duration_minutes is negative."""
        with pytest.raises(ValueError, match="duration_minutes must be non-negative"):
            HealthMetadata(
                record_id="health-001",
                health_type="sleep_summary",
                date="2026-03-07",
                source_type="apple_health",
                date_first_observed="2026-03-07T08:00:00Z",
                duration_minutes=-10,  # Invalid: negative
            )

    def test_chunk_raises_on_invalid_score_range(self, health_domain):
        """chunk() raises ValueError when score is outside 0-100 range."""
        with pytest.raises(ValueError, match="score must be in range 0-100"):
            HealthMetadata(
                record_id="health-001",
                health_type="sleep_summary",
                date="2026-03-07",
                source_type="apple_health",
                date_first_observed="2026-03-07T08:00:00Z",
                score=150.0,  # Invalid: > 100
            )

    def test_chunk_raises_on_missing_required_field(self, health_domain, base_structural_hints):
        """chunk() raises ValueError when required HealthMetadata field is missing."""
        hints = StructuralHints(
            has_headings=False,
            has_lists=False,
            has_tables=False,
            natural_boundaries=[],
            extra_metadata={
                "record_id": "health-001",
                "health_type": "sleep_summary",
                "date": "2026-03-07",
                # Missing 'source_type' and 'date_first_observed'
            },
        )

        content = NormalizedContent(
            markdown="Health data.",
            source_id="health_1",
            structural_hints=hints,
            normalizer_version="1.0.0",
        )

        with pytest.raises(ValueError, match="Invalid HealthMetadata"):
            health_domain.chunk(content)


class TestHealthSourceTypeVariations:
    """Tests for different health source types."""

    @pytest.mark.parametrize(
        "source_type",
        ["apple_health", "oura", "fitbit", "garmin", "whoop"],
    )
    def test_all_source_types_produce_valid_chunks(
        self, health_domain, source_type
    ):
        """All health source types produce valid chunks with domain_metadata."""
        meta = HealthMetadata(
            record_id="health-001",
            health_type="sleep_summary",
            date="2026-03-07",
            source_type=source_type,
            date_first_observed="2026-03-07T08:00:00Z",
        )

        hints = StructuralHints(
            has_headings=False,
            has_lists=False,
            has_tables=False,
            natural_boundaries=[],
            extra_metadata=meta.model_dump(),
        )

        content = NormalizedContent(
            markdown="Health data description.",
            source_id="health_1",
            structural_hints=hints,
            normalizer_version="1.0.0",
        )

        chunks = health_domain.chunk(content)

        assert len(chunks) == 1
        assert chunks[0].domain_metadata["source_type"] == source_type
