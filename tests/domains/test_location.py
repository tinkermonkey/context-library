"""Tests for LocationDomain chunking logic."""

import pytest
from context_library.domains.location import LocationDomain
from context_library.storage.models import (
    Domain,
    NormalizedContent,
    StructuralHints,
    ChunkType,
)


class TestLocationDomainMetadata:
    """Test LocationMetadata validation via LocationDomain.chunk()."""

    def test_latitude_validation_valid_range(self):
        """LocationMetadata validates latitude in [-90, 90]."""
        domain = LocationDomain()
        content = NormalizedContent(
            markdown="Test location",
            source_id="test/location",
            structural_hints=StructuralHints(
                has_headings=False,
                has_lists=False,
                has_tables=False,
                natural_boundaries=[],
                extra_metadata={
                    "location_id": "loc-123",
                    "latitude": 37.7749,
                    "longitude": -122.4194,
                    "source_type": "apple_location_visit",
                    "date_first_observed": "2025-02-10T10:00:00Z",
                    "place_name": "San Francisco",
                }
            ),
            normalizer_version="1.0.0",
            domain=Domain.LOCATION,
        )
        chunks = domain.chunk(content)
        assert len(chunks) == 1
        assert chunks[0].domain_metadata["latitude"] == 37.7749

    def test_latitude_validation_boundary_positive(self):
        """LocationMetadata accepts latitude of exactly 90."""
        domain = LocationDomain()
        content = NormalizedContent(
            markdown="North Pole",
            source_id="test/location",
            structural_hints=StructuralHints(
                has_headings=False,
                has_lists=False,
                has_tables=False,
                natural_boundaries=[],
                extra_metadata={
                    "location_id": "loc-north",
                    "latitude": 90.0,
                    "longitude": 0.0,
                    "source_type": "apple_location_visit",
                    "date_first_observed": "2025-02-10T10:00:00Z",
                }
            ),
            normalizer_version="1.0.0",
            domain=Domain.LOCATION,
        )
        chunks = domain.chunk(content)
        assert len(chunks) == 1
        assert chunks[0].domain_metadata["latitude"] == 90.0

    def test_latitude_validation_boundary_negative(self):
        """LocationMetadata accepts latitude of exactly -90."""
        domain = LocationDomain()
        content = NormalizedContent(
            markdown="South Pole",
            source_id="test/location",
            structural_hints=StructuralHints(
                has_headings=False,
                has_lists=False,
                has_tables=False,
                natural_boundaries=[],
                extra_metadata={
                    "location_id": "loc-south",
                    "latitude": -90.0,
                    "longitude": 0.0,
                    "source_type": "apple_location_visit",
                    "date_first_observed": "2025-02-10T10:00:00Z",
                }
            ),
            normalizer_version="1.0.0",
            domain=Domain.LOCATION,
        )
        chunks = domain.chunk(content)
        assert len(chunks) == 1
        assert chunks[0].domain_metadata["latitude"] == -90.0

    def test_latitude_validation_rejects_out_of_range(self):
        """LocationMetadata rejects latitude > 90."""
        domain = LocationDomain()
        content = NormalizedContent(
            markdown="Invalid",
            source_id="test/location",
            structural_hints=StructuralHints(
                has_headings=False,
                has_lists=False,
                has_tables=False,
                natural_boundaries=[],
                extra_metadata={
                    "location_id": "loc-invalid",
                    "latitude": 91.0,
                    "longitude": 0.0,
                    "source_type": "apple_location_visit",
                    "date_first_observed": "2025-02-10T10:00:00Z",
                }
            ),
            normalizer_version="1.0.0",
            domain=Domain.LOCATION,
        )
        with pytest.raises(ValueError, match="Invalid LocationMetadata"):
            domain.chunk(content)

    def test_longitude_validation_valid_range(self):
        """LocationMetadata validates longitude in [-180, 180]."""
        domain = LocationDomain()
        content = NormalizedContent(
            markdown="Test location",
            source_id="test/location",
            structural_hints=StructuralHints(
                has_headings=False,
                has_lists=False,
                has_tables=False,
                natural_boundaries=[],
                extra_metadata={
                    "location_id": "loc-123",
                    "latitude": 0.0,
                    "longitude": -122.4194,
                    "source_type": "apple_location_visit",
                    "date_first_observed": "2025-02-10T10:00:00Z",
                }
            ),
            normalizer_version="1.0.0",
            domain=Domain.LOCATION,
        )
        chunks = domain.chunk(content)
        assert len(chunks) == 1
        assert chunks[0].domain_metadata["longitude"] == -122.4194

    def test_longitude_validation_boundary_positive(self):
        """LocationMetadata accepts longitude of exactly 180."""
        domain = LocationDomain()
        content = NormalizedContent(
            markdown="Prime meridian",
            source_id="test/location",
            structural_hints=StructuralHints(
                has_headings=False,
                has_lists=False,
                has_tables=False,
                natural_boundaries=[],
                extra_metadata={
                    "location_id": "loc-180",
                    "latitude": 0.0,
                    "longitude": 180.0,
                    "source_type": "apple_location_visit",
                    "date_first_observed": "2025-02-10T10:00:00Z",
                }
            ),
            normalizer_version="1.0.0",
            domain=Domain.LOCATION,
        )
        chunks = domain.chunk(content)
        assert len(chunks) == 1
        assert chunks[0].domain_metadata["longitude"] == 180.0

    def test_longitude_validation_boundary_negative(self):
        """LocationMetadata accepts longitude of exactly -180."""
        domain = LocationDomain()
        content = NormalizedContent(
            markdown="Prime meridian",
            source_id="test/location",
            structural_hints=StructuralHints(
                has_headings=False,
                has_lists=False,
                has_tables=False,
                natural_boundaries=[],
                extra_metadata={
                    "location_id": "loc-neg180",
                    "latitude": 0.0,
                    "longitude": -180.0,
                    "source_type": "apple_location_visit",
                    "date_first_observed": "2025-02-10T10:00:00Z",
                }
            ),
            normalizer_version="1.0.0",
            domain=Domain.LOCATION,
        )
        chunks = domain.chunk(content)
        assert len(chunks) == 1
        assert chunks[0].domain_metadata["longitude"] == -180.0

    def test_longitude_validation_rejects_out_of_range(self):
        """LocationMetadata rejects longitude > 180."""
        domain = LocationDomain()
        content = NormalizedContent(
            markdown="Invalid",
            source_id="test/location",
            structural_hints=StructuralHints(
                has_headings=False,
                has_lists=False,
                has_tables=False,
                natural_boundaries=[],
                extra_metadata={
                    "location_id": "loc-invalid",
                    "latitude": 0.0,
                    "longitude": 181.0,
                    "source_type": "apple_location_visit",
                    "date_first_observed": "2025-02-10T10:00:00Z",
                }
            ),
            normalizer_version="1.0.0",
            domain=Domain.LOCATION,
        )
        with pytest.raises(ValueError, match="Invalid LocationMetadata"):
            domain.chunk(content)


class TestLocationContextHeaders:
    """Test context header formatting for different location types."""

    def test_visit_with_place_name_and_arrival_date(self):
        """Visit with place name and arrival date produces correct context header."""
        domain = LocationDomain()
        content = NormalizedContent(
            markdown="Spent time here",
            source_id="apple_location/visit/123",
            structural_hints=StructuralHints(
                has_headings=False,
                has_lists=False,
                has_tables=False,
                natural_boundaries=[],
                extra_metadata={
                    "location_id": "apple_location/visit/123",
                    "latitude": 37.7749,
                    "longitude": -122.4194,
                    "source_type": "apple_location_visit",
                    "date_first_observed": "2025-02-10T10:00:00Z",
                    "place_name": "San Francisco",
                    "arrival_date": "2025-02-10T08:00:00Z",
                }
            ),
            normalizer_version="1.0.0",
            domain=Domain.LOCATION,
        )
        chunks = domain.chunk(content)
        assert chunks[0].context_header == "San Francisco — 2025-02-10T08:00:00Z"

    def test_visit_with_place_name_only(self):
        """Visit with place name but no arrival date produces place name header."""
        domain = LocationDomain()
        content = NormalizedContent(
            markdown="No arrival date",
            source_id="apple_location/visit/456",
            structural_hints=StructuralHints(
                has_headings=False,
                has_lists=False,
                has_tables=False,
                natural_boundaries=[],
                extra_metadata={
                    "location_id": "apple_location/visit/456",
                    "latitude": 51.5074,
                    "longitude": -0.1278,
                    "source_type": "apple_location_visit",
                    "date_first_observed": "2025-02-10T10:00:00Z",
                    "place_name": "London",
                }
            ),
            normalizer_version="1.0.0",
            domain=Domain.LOCATION,
        )
        chunks = domain.chunk(content)
        assert chunks[0].context_header == "London"

    def test_visit_with_coordinates_fallback(self):
        """Visit without place name falls back to coordinates."""
        domain = LocationDomain()
        content = NormalizedContent(
            markdown="No place name",
            source_id="apple_location/visit/789",
            structural_hints=StructuralHints(
                has_headings=False,
                has_lists=False,
                has_tables=False,
                natural_boundaries=[],
                extra_metadata={
                    "location_id": "apple_location/visit/789",
                    "latitude": 40.7128,
                    "longitude": -74.0060,
                    "source_type": "apple_location_visit",
                    "date_first_observed": "2025-02-10T10:00:00Z",
                }
            ),
            normalizer_version="1.0.0",
            domain=Domain.LOCATION,
        )
        chunks = domain.chunk(content)
        assert chunks[0].context_header == "40.7128, -74.006"

    def test_current_location_snapshot(self):
        """Current location snapshot produces 'Current location — {timestamp}' header."""
        domain = LocationDomain()
        content = NormalizedContent(
            markdown="Current location data",
            source_id="apple-location-current",
            structural_hints=StructuralHints(
                has_headings=False,
                has_lists=False,
                has_tables=False,
                natural_boundaries=[],
                extra_metadata={
                    "location_id": "apple-location-current",
                    "latitude": 37.7749,
                    "longitude": -122.4194,
                    "source_type": "apple_location_current",
                    "date_first_observed": "2025-02-10T15:30:00Z",
                    "place_name": "San Francisco",
                }
            ),
            normalizer_version="1.0.0",
            domain=Domain.LOCATION,
        )
        chunks = domain.chunk(content)
        assert chunks[0].context_header == "Current location — 2025-02-10T15:30:00Z"

    def test_current_location_snapshot_without_place_name(self):
        """Current location snapshot without place name still uses timestamp header."""
        domain = LocationDomain()
        content = NormalizedContent(
            markdown="Current location data",
            source_id="apple-location-current",
            structural_hints=StructuralHints(
                has_headings=False,
                has_lists=False,
                has_tables=False,
                natural_boundaries=[],
                extra_metadata={
                    "location_id": "apple-location-current",
                    "latitude": 37.7749,
                    "longitude": -122.4194,
                    "source_type": "apple_location_current",
                    "date_first_observed": "2025-02-10T15:30:00Z",
                }
            ),
            normalizer_version="1.0.0",
            domain=Domain.LOCATION,
        )
        chunks = domain.chunk(content)
        assert chunks[0].context_header == "Current location — 2025-02-10T15:30:00Z"


class TestLocationChunking:
    """Test chunking behavior for location content."""

    def test_empty_markdown_yields_empty_list(self):
        """Empty markdown content yields empty chunk list."""
        domain = LocationDomain()
        content = NormalizedContent(
            markdown="",
            source_id="apple_location/visit/empty",
            structural_hints=StructuralHints(
                has_headings=False,
                has_lists=False,
                has_tables=False,
                natural_boundaries=[],
                extra_metadata={
                    "location_id": "apple_location/visit/empty",
                    "latitude": 37.7749,
                    "longitude": -122.4194,
                    "source_type": "apple_location_visit",
                    "date_first_observed": "2025-02-10T10:00:00Z",
                }
            ),
            normalizer_version="1.0.0",
            domain=Domain.LOCATION,
        )
        chunks = domain.chunk(content)
        assert chunks == []

    def test_whitespace_only_markdown_yields_empty_list(self):
        """Whitespace-only markdown content yields empty chunk list."""
        domain = LocationDomain()
        content = NormalizedContent(
            markdown="   \n\n  \t  ",
            source_id="apple_location/visit/whitespace",
            structural_hints=StructuralHints(
                has_headings=False,
                has_lists=False,
                has_tables=False,
                natural_boundaries=[],
                extra_metadata={
                    "location_id": "apple_location/visit/whitespace",
                    "latitude": 37.7749,
                    "longitude": -122.4194,
                    "source_type": "apple_location_visit",
                    "date_first_observed": "2025-02-10T10:00:00Z",
                }
            ),
            normalizer_version="1.0.0",
            domain=Domain.LOCATION,
        )
        chunks = domain.chunk(content)
        assert chunks == []

    def test_single_chunk_for_short_content(self):
        """Short content produces a single chunk."""
        domain = LocationDomain()
        content = NormalizedContent(
            markdown="Short description",
            source_id="apple_location/visit/short",
            structural_hints=StructuralHints(
                has_headings=False,
                has_lists=False,
                has_tables=False,
                natural_boundaries=[],
                extra_metadata={
                    "location_id": "apple_location/visit/short",
                    "latitude": 37.7749,
                    "longitude": -122.4194,
                    "source_type": "apple_location_visit",
                    "date_first_observed": "2025-02-10T10:00:00Z",
                    "place_name": "San Francisco",
                }
            ),
            normalizer_version="1.0.0",
            domain=Domain.LOCATION,
        )
        chunks = domain.chunk(content)
        assert len(chunks) == 1
        assert chunks[0].content == "Short description"
        assert chunks[0].chunk_type == ChunkType.STANDARD
        assert chunks[0].chunk_index == 0

    def test_chunk_preserves_metadata(self):
        """Chunks preserve all location metadata fields."""
        domain = LocationDomain()
        content = NormalizedContent(
            markdown="Test location",
            source_id="apple_location/visit/meta",
            structural_hints=StructuralHints(
                has_headings=False,
                has_lists=False,
                has_tables=False,
                natural_boundaries=[],
                extra_metadata={
                    "location_id": "apple_location/visit/meta",
                    "latitude": 37.7749,
                    "longitude": -122.4194,
                    "source_type": "apple_location_visit",
                    "date_first_observed": "2025-02-10T10:00:00Z",
                    "place_name": "San Francisco",
                    "locality": "San Francisco County",
                    "country": "United States",
                    "arrival_date": "2025-02-10T08:00:00Z",
                    "departure_date": "2025-02-10T18:00:00Z",
                    "duration_minutes": 600,
                }
            ),
            normalizer_version="1.0.0",
            domain=Domain.LOCATION,
        )
        chunks = domain.chunk(content)
        assert chunks[0].domain_metadata["place_name"] == "San Francisco"
        assert chunks[0].domain_metadata["locality"] == "San Francisco County"
        assert chunks[0].domain_metadata["country"] == "United States"
        assert chunks[0].domain_metadata["duration_minutes"] == 600

    def test_missing_extra_metadata_raises_error(self):
        """Missing extra_metadata raises ValueError."""
        domain = LocationDomain()
        content = NormalizedContent(
            markdown="Test",
            source_id="test/location",
            structural_hints=StructuralHints(
                has_headings=False,
                has_lists=False,
                has_tables=False,
                natural_boundaries=[],
            ),  # No extra_metadata
            normalizer_version="1.0.0",
            domain=Domain.LOCATION,
        )
        with pytest.raises(ValueError, match="LocationDomain requires extra_metadata"):
            domain.chunk(content)

    def test_invalid_metadata_raises_error(self):
        """Invalid metadata raises ValueError."""
        domain = LocationDomain()
        content = NormalizedContent(
            markdown="Test",
            source_id="test/location",
            structural_hints=StructuralHints(
                has_headings=False,
                has_lists=False,
                has_tables=False,
                natural_boundaries=[],
                extra_metadata={
                    "location_id": "loc-bad",
                    # Missing required latitude and longitude
                    "source_type": "apple_location_visit",
                    "date_first_observed": "2025-02-10T10:00:00Z",
                }
            ),
            normalizer_version="1.0.0",
            domain=Domain.LOCATION,
        )
        with pytest.raises(ValueError, match="Invalid LocationMetadata"):
            domain.chunk(content)
