"""Tests for the people domain."""

import pytest

from context_library.domains.registry import Domain, get_domain_chunker
from context_library.domains.people import PeopleDomain
from context_library.storage.models import (
    Chunk,
    ChunkType,
    NormalizedContent,
    StructuralHints,
    PeopleMetadata,
    compute_chunk_hash,
)


@pytest.fixture
def people_domain():
    """Create a PeopleDomain instance with default limits."""
    return PeopleDomain(hard_limit=1024)


@pytest.fixture
def sample_people_metadata():
    """Create sample PeopleMetadata for testing."""
    return PeopleMetadata(
        contact_id="contact-001",
        display_name="Alice Smith",
        given_name="Alice",
        family_name="Smith",
        emails=("alice@example.com", "alice.smith@work.com"),
        phones=("555-123-4567", "555-987-6543"),
        organization="Acme Corp",
        job_title="Senior Engineer",
        notes="Met at conference 2025",
        source_type="google-contacts",
    )


@pytest.fixture
def sample_people_metadata_minimal():
    """Create minimal PeopleMetadata for testing (no optional fields)."""
    return PeopleMetadata(
        contact_id="contact-002",
        display_name="Bob Jones",
        source_type="apple-contacts",
    )


@pytest.fixture
def sample_people_metadata_no_org():
    """Create PeopleMetadata without organization for testing."""
    return PeopleMetadata(
        contact_id="contact-003",
        display_name="Charlie Brown",
        given_name="Charlie",
        family_name="Brown",
        emails=("charlie@example.com",),
        phones=("555-111-2222",),
        job_title="Product Manager",
        source_type="google-contacts",
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


class TestPeopleDomainRegistry:
    """Tests for PeopleDomain domain registry integration."""

    def test_domain_chunker_registry_returns_people_domain(self):
        """get_domain_chunker(Domain.PEOPLE) returns a PeopleDomain instance."""
        domain = get_domain_chunker(Domain.PEOPLE)

        assert isinstance(domain, PeopleDomain)
        assert domain.hard_limit == 1024


class TestPeopleDomainBasics:
    """Basic tests for PeopleDomain initialization and properties."""

    def test_initialization_with_defaults(self):
        """PeopleDomain initializes with default hard_limit."""
        domain = PeopleDomain()

        assert domain.hard_limit == 1024

    def test_initialization_with_custom_limit(self):
        """PeopleDomain initializes with custom hard_limit."""
        domain = PeopleDomain(hard_limit=512)

        assert domain.hard_limit == 512

    def test_initialization_rejects_zero_hard_limit(self):
        """PeopleDomain rejects hard_limit=0."""
        with pytest.raises(ValueError, match="hard_limit must be a positive integer"):
            PeopleDomain(hard_limit=0)

    def test_initialization_rejects_negative_hard_limit(self):
        """PeopleDomain rejects negative hard_limit."""
        with pytest.raises(ValueError, match="hard_limit must be a positive integer"):
            PeopleDomain(hard_limit=-1)

    def test_chunk_returns_list_of_chunks(
        self, people_domain, sample_people_metadata, base_structural_hints
    ):
        """chunk() returns a list of Chunk instances."""
        hints = StructuralHints(
            has_headings=False,
            has_lists=False,
            has_tables=False,
            natural_boundaries=[],
            extra_metadata=sample_people_metadata.model_dump(),
        )

        content = NormalizedContent(
            markdown="Alice Smith is a Senior Engineer at Acme Corp.\nEmail: alice@example.com\nPhone: 555-123-4567",
            source_id="contact-001",
            structural_hints=hints,
            normalizer_version="1.0.0",
        )

        result = people_domain.chunk(content)

        assert isinstance(result, list)
        assert all(isinstance(chunk, Chunk) for chunk in result)
        assert len(result) >= 1

    def test_chunk_raises_without_extra_metadata(
        self, people_domain, base_structural_hints
    ):
        """chunk() raises ValueError if extra_metadata is missing."""
        content = NormalizedContent(
            markdown="Test contact",
            source_id="contact-001",
            structural_hints=base_structural_hints,
            normalizer_version="1.0.0",
        )

        with pytest.raises(ValueError, match="extra_metadata"):
            people_domain.chunk(content)


class TestSingleContactChunk:
    """Tests for chunking single contacts."""

    def test_single_contact_with_full_metadata_creates_one_chunk(
        self, people_domain, sample_people_metadata
    ):
        """A contact with full metadata creates exactly one chunk."""
        hints = StructuralHints(
            has_headings=False,
            has_lists=False,
            has_tables=False,
            natural_boundaries=[],
            extra_metadata=sample_people_metadata.model_dump(),
        )

        content = NormalizedContent(
            markdown="Alice Smith is a Senior Engineer at Acme Corp.\nEmail: alice@example.com\nPhone: 555-123-4567",
            source_id="contact-001",
            structural_hints=hints,
            normalizer_version="1.0.0",
        )

        chunks = people_domain.chunk(content)

        assert len(chunks) == 1
        assert chunks[0].chunk_index == 0

    def test_contact_with_no_description_returns_empty_list(
        self, people_domain, sample_people_metadata
    ):
        """A contact with no description (empty markdown) returns an empty list."""
        hints = StructuralHints(
            has_headings=False,
            has_lists=False,
            has_tables=False,
            natural_boundaries=[],
            extra_metadata=sample_people_metadata.model_dump(),
        )

        content = NormalizedContent(
            markdown="",
            source_id="contact-001",
            structural_hints=hints,
            normalizer_version="1.0.0",
        )

        chunks = people_domain.chunk(content)

        assert len(chunks) == 0

    def test_contact_with_whitespace_only_description_returns_empty_list(
        self, people_domain, sample_people_metadata
    ):
        """A contact with whitespace-only description returns an empty list."""
        hints = StructuralHints(
            has_headings=False,
            has_lists=False,
            has_tables=False,
            natural_boundaries=[],
            extra_metadata=sample_people_metadata.model_dump(),
        )

        content = NormalizedContent(
            markdown="   \n\t\n   ",
            source_id="contact-001",
            structural_hints=hints,
            normalizer_version="1.0.0",
        )

        chunks = people_domain.chunk(content)

        assert len(chunks) == 0

    def test_chunk_raises_on_invalid_metadata_from_domain(
        self, people_domain, base_structural_hints
    ):
        """chunk() raises ValueError when extra_metadata contains invalid PeopleMetadata."""
        hints = StructuralHints(
            has_headings=False,
            has_lists=False,
            has_tables=False,
            natural_boundaries=[],
            extra_metadata={
                "contact_id": "",  # Invalid: empty contact_id
                "display_name": "Alice",
                "source_type": "google-contacts",
            },
        )

        content = NormalizedContent(
            markdown="Contact description.",
            source_id="contact-001",
            structural_hints=hints,
            normalizer_version="1.0.0",
        )

        with pytest.raises(ValueError, match="Invalid PeopleMetadata"):
            people_domain.chunk(content)

    def test_chunk_has_correct_context_header_with_organization(
        self, people_domain, sample_people_metadata
    ):
        """chunk() sets context_header to 'Contact: {display_name} — {organization}'."""
        hints = StructuralHints(
            has_headings=False,
            has_lists=False,
            has_tables=False,
            natural_boundaries=[],
            extra_metadata=sample_people_metadata.model_dump(),
        )

        content = NormalizedContent(
            markdown="Contact details here.",
            source_id="contact-001",
            structural_hints=hints,
            normalizer_version="1.0.0",
        )

        chunks = people_domain.chunk(content)

        assert chunks[0].context_header == "Contact: Alice Smith — Acme Corp"

    def test_chunk_has_correct_context_header_without_organization(
        self, people_domain, sample_people_metadata_no_org
    ):
        """chunk() omits organization when organization is None."""
        hints = StructuralHints(
            has_headings=False,
            has_lists=False,
            has_tables=False,
            natural_boundaries=[],
            extra_metadata=sample_people_metadata_no_org.model_dump(),
        )

        content = NormalizedContent(
            markdown="Contact details here.",
            source_id="contact-003",
            structural_hints=hints,
            normalizer_version="1.0.0",
        )

        chunks = people_domain.chunk(content)

        assert chunks[0].context_header == "Contact: Charlie Brown"

    def test_chunk_has_correct_context_header_minimal_metadata(
        self, people_domain, sample_people_metadata_minimal
    ):
        """chunk() handles minimal metadata (no org, job_title, emails, phones)."""
        hints = StructuralHints(
            has_headings=False,
            has_lists=False,
            has_tables=False,
            natural_boundaries=[],
            extra_metadata=sample_people_metadata_minimal.model_dump(),
        )

        content = NormalizedContent(
            markdown="Basic contact info.",
            source_id="contact-002",
            structural_hints=hints,
            normalizer_version="1.0.0",
        )

        chunks = people_domain.chunk(content)

        assert chunks[0].context_header == "Contact: Bob Jones"

    def test_chunk_has_standard_chunk_type(
        self, people_domain, sample_people_metadata
    ):
        """chunk() sets chunk_type to ChunkType.STANDARD."""
        hints = StructuralHints(
            has_headings=False,
            has_lists=False,
            has_tables=False,
            natural_boundaries=[],
            extra_metadata=sample_people_metadata.model_dump(),
        )

        content = NormalizedContent(
            markdown="Contact description.",
            source_id="contact-001",
            structural_hints=hints,
            normalizer_version="1.0.0",
        )

        chunks = people_domain.chunk(content)

        assert chunks[0].chunk_type == ChunkType.STANDARD

    def test_chunk_has_domain_metadata(
        self, people_domain, sample_people_metadata
    ):
        """chunk() populates domain_metadata with PeopleMetadata fields."""
        hints = StructuralHints(
            has_headings=False,
            has_lists=False,
            has_tables=False,
            natural_boundaries=[],
            extra_metadata=sample_people_metadata.model_dump(),
        )

        content = NormalizedContent(
            markdown="Contact description.",
            source_id="contact-001",
            structural_hints=hints,
            normalizer_version="1.0.0",
        )

        chunks = people_domain.chunk(content)

        assert chunks[0].domain_metadata is not None
        assert chunks[0].domain_metadata["contact_id"] == "contact-001"
        assert chunks[0].domain_metadata["display_name"] == "Alice Smith"
        assert chunks[0].domain_metadata["organization"] == "Acme Corp"
        assert chunks[0].domain_metadata["job_title"] == "Senior Engineer"


class TestLongContactSplitting:
    """Tests for chunking long contacts that exceed hard_limit."""

    def test_short_contact_not_split(
        self, people_domain, sample_people_metadata
    ):
        """Short contact content not exceeding hard_limit creates single chunk."""
        domain = PeopleDomain(hard_limit=100)

        hints = StructuralHints(
            has_headings=False,
            has_lists=False,
            has_tables=False,
            natural_boundaries=[],
            extra_metadata=sample_people_metadata.model_dump(),
        )

        content = NormalizedContent(
            markdown="Short description.",
            source_id="contact-001",
            structural_hints=hints,
            normalizer_version="1.0.0",
        )

        chunks = domain.chunk(content)

        assert len(chunks) == 1

    def test_long_contact_split_at_sentence_boundaries(
        self, sample_people_metadata
    ):
        """Long contact content is split at sentence boundaries."""
        domain = PeopleDomain(hard_limit=20)

        hints = StructuralHints(
            has_headings=False,
            has_lists=False,
            has_tables=False,
            natural_boundaries=[],
            extra_metadata=sample_people_metadata.model_dump(),
        )

        markdown = (
            "First sentence with lots of content and details. "
            "Second sentence also with significant content and information. "
            "Third sentence continues with even more important information. "
            "Fourth sentence adds even more valuable details and context. "
            "Fifth sentence provides additional information about the contact."
        )

        content = NormalizedContent(
            markdown=markdown,
            source_id="contact-001",
            structural_hints=hints,
            normalizer_version="1.0.0",
        )

        chunks = domain.chunk(content)

        # Should be split into multiple chunks
        assert len(chunks) > 1
        # All chunks should have sequential indices
        for idx, chunk in enumerate(chunks):
            assert chunk.chunk_index == idx
        # All chunks should maintain context header
        for chunk in chunks:
            assert chunk.context_header == "Contact: Alice Smith — Acme Corp"

    def test_split_chunks_have_sequential_indices(
        self, sample_people_metadata
    ):
        """Split chunks have sequential chunk_index values starting from 0."""
        domain = PeopleDomain(hard_limit=30)

        hints = StructuralHints(
            has_headings=False,
            has_lists=False,
            has_tables=False,
            natural_boundaries=[],
            extra_metadata=sample_people_metadata.model_dump(),
        )

        markdown = "First sentence. Second sentence. Third sentence. Fourth sentence."

        content = NormalizedContent(
            markdown=markdown,
            source_id="contact-001",
            structural_hints=hints,
            normalizer_version="1.0.0",
        )

        chunks = domain.chunk(content)

        for idx, chunk in enumerate(chunks):
            assert chunk.chunk_index == idx


class TestChunkHash:
    """Tests for chunk hash computation."""

    def test_chunk_hash_computed_from_content_only(
        self, people_domain, sample_people_metadata
    ):
        """chunk_hash is computed from content, not context_header."""
        hints = StructuralHints(
            has_headings=False,
            has_lists=False,
            has_tables=False,
            natural_boundaries=[],
            extra_metadata=sample_people_metadata.model_dump(),
        )

        content = NormalizedContent(
            markdown="Contact details.",
            source_id="contact-001",
            structural_hints=hints,
            normalizer_version="1.0.0",
        )

        chunks = people_domain.chunk(content)

        expected_hash = compute_chunk_hash("Contact details.")
        assert chunks[0].chunk_hash == expected_hash

    def test_chunk_hash_is_deterministic(
        self, people_domain, sample_people_metadata
    ):
        """Chunking the same content twice yields the same hash."""
        hints = StructuralHints(
            has_headings=False,
            has_lists=False,
            has_tables=False,
            natural_boundaries=[],
            extra_metadata=sample_people_metadata.model_dump(),
        )

        content = NormalizedContent(
            markdown="Deterministic contact content.",
            source_id="contact-001",
            structural_hints=hints,
            normalizer_version="1.0.0",
        )

        chunks1 = people_domain.chunk(content)
        chunks2 = people_domain.chunk(content)

        assert chunks1[0].chunk_hash == chunks2[0].chunk_hash


class TestPeopleMetadataValidation:
    """Tests for PeopleMetadata validation."""

    def test_raises_on_empty_contact_id(self):
        """PeopleMetadata rejects empty contact_id."""
        with pytest.raises(ValueError, match="contact_id must be a non-empty string"):
            PeopleMetadata(
                contact_id="",  # Invalid
                display_name="Alice",
                source_type="google-contacts",
            )

    def test_raises_on_empty_display_name(self):
        """PeopleMetadata rejects empty display_name."""
        with pytest.raises(ValueError, match="display_name must be a non-empty string"):
            PeopleMetadata(
                contact_id="contact-001",
                display_name="",  # Invalid
                source_type="google-contacts",
            )

    def test_raises_on_empty_source_type(self):
        """PeopleMetadata rejects empty source_type."""
        with pytest.raises(ValueError, match="source_type must be a non-empty string"):
            PeopleMetadata(
                contact_id="contact-001",
                display_name="Alice",
                source_type="",  # Invalid
            )

    def test_chunk_raises_on_invalid_contact_id_in_domain(
        self, people_domain, base_structural_hints
    ):
        """chunk() raises ValueError when extra_metadata has invalid contact_id."""
        hints = StructuralHints(
            has_headings=False,
            has_lists=False,
            has_tables=False,
            natural_boundaries=[],
            extra_metadata={
                "contact_id": "",  # Invalid
                "display_name": "Alice",
                "source_type": "google-contacts",
            },
        )

        content = NormalizedContent(
            markdown="Contact info.",
            source_id="contact-001",
            structural_hints=hints,
            normalizer_version="1.0.0",
        )

        with pytest.raises(ValueError, match="Invalid PeopleMetadata"):
            people_domain.chunk(content)


class TestOrganizationVariations:
    """Tests for context_header handling with various organization values."""

    def test_context_header_with_organization(
        self, people_domain, sample_people_metadata
    ):
        """context_header includes organization when present."""
        hints = StructuralHints(
            has_headings=False,
            has_lists=False,
            has_tables=False,
            natural_boundaries=[],
            extra_metadata=sample_people_metadata.model_dump(),
        )

        content = NormalizedContent(
            markdown="Details.",
            source_id="contact-001",
            structural_hints=hints,
            normalizer_version="1.0.0",
        )

        chunks = people_domain.chunk(content)

        assert "—" in chunks[0].context_header
        assert "Acme Corp" in chunks[0].context_header

    def test_context_header_without_organization(
        self, people_domain, sample_people_metadata_minimal
    ):
        """context_header omits organization segment when None."""
        hints = StructuralHints(
            has_headings=False,
            has_lists=False,
            has_tables=False,
            natural_boundaries=[],
            extra_metadata=sample_people_metadata_minimal.model_dump(),
        )

        content = NormalizedContent(
            markdown="Details.",
            source_id="contact-002",
            structural_hints=hints,
            normalizer_version="1.0.0",
        )

        chunks = people_domain.chunk(content)

        assert "—" not in chunks[0].context_header
        assert chunks[0].context_header == "Contact: Bob Jones"

    def test_context_header_preserves_display_name_formatting(
        self, people_domain
    ):
        """context_header preserves exact display_name formatting."""
        meta = PeopleMetadata(
            contact_id="contact-001",
            display_name="Mary-Jane O'Neill",
            organization="Tech Industries Inc.",
            source_type="apple-contacts",
        )

        hints = StructuralHints(
            has_headings=False,
            has_lists=False,
            has_tables=False,
            natural_boundaries=[],
            extra_metadata=meta.model_dump(),
        )

        content = NormalizedContent(
            markdown="Details.",
            source_id="contact-001",
            structural_hints=hints,
            normalizer_version="1.0.0",
        )

        chunks = people_domain.chunk(content)

        assert chunks[0].context_header == "Contact: Mary-Jane O'Neill — Tech Industries Inc."
