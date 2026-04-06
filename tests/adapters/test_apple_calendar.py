"""Tests for the AppleCalendarAdapter."""

import pytest

import httpx

from context_library.adapters.apple_calendar import AppleCalendarAdapter
from context_library.storage.models import Domain, PollStrategy, NormalizedContent, EventMetadata


class TestAppleCalendarAdapterInitialization:
    """Tests for AppleCalendarAdapter initialization."""

    def test_init_default_parameters(self):
        """__init__ uses default parameters when not provided."""
        adapter = AppleCalendarAdapter(api_url="http://127.0.0.1:7123", api_key="test-token")
        assert adapter._api_url == "http://127.0.0.1:7123"
        assert adapter._api_key == "test-token"
        assert adapter._account_id == "default"

    def test_init_custom_parameters(self):
        """__init__ accepts and stores custom parameters."""
        adapter = AppleCalendarAdapter(
            api_url="http://localhost:8000",
            api_key="test_key",
            account_id="work",
        )
        assert adapter._api_url == "http://localhost:8000"
        assert adapter._api_key == "test_key"
        assert adapter._account_id == "work"

    def test_init_strips_trailing_slash_from_url(self):
        """__init__ strips trailing slash from api_url."""
        adapter = AppleCalendarAdapter(api_url="http://127.0.0.1:7123/", api_key="test-token")
        assert adapter._api_url == "http://127.0.0.1:7123"

    def test_init_no_trailing_slash(self):
        """__init__ leaves api_url unchanged if no trailing slash."""
        adapter = AppleCalendarAdapter(api_url="http://127.0.0.1:7123", api_key="test-token")
        assert adapter._api_url == "http://127.0.0.1:7123"

    def test_init_requires_api_key(self):
        """__init__ raises ValueError when api_key is empty."""
        with pytest.raises(ValueError, match="api_key is required"):
            AppleCalendarAdapter(api_url="http://127.0.0.1:7123", api_key="")


class TestAppleCalendarAdapterProperties:
    """Tests for AppleCalendarAdapter properties."""

    def test_adapter_id_format_default(self):
        """adapter_id has correct format: apple_calendar:{account_id}."""
        adapter = AppleCalendarAdapter(api_url="http://127.0.0.1:7123", api_key="test-token")
        assert adapter.adapter_id == "apple_calendar:default"

    def test_adapter_id_format_custom_account(self):
        """adapter_id uses custom account_id."""
        adapter = AppleCalendarAdapter(api_url="http://127.0.0.1:7123", api_key="test-token", account_id="work")
        assert adapter.adapter_id == "apple_calendar:work"

    def test_domain_property(self):
        """domain property returns Domain.EVENTS."""
        adapter = AppleCalendarAdapter(api_url="http://127.0.0.1:7123", api_key="test-token")
        assert adapter.domain == Domain.EVENTS

    def test_poll_strategy_property(self):
        """poll_strategy property returns PollStrategy.PULL."""
        adapter = AppleCalendarAdapter(api_url="http://127.0.0.1:7123", api_key="test-token")
        assert adapter.poll_strategy == PollStrategy.PULL

    def test_normalizer_version_property(self):
        """normalizer_version property returns '1.0.0'."""
        adapter = AppleCalendarAdapter(api_url="http://127.0.0.1:7123", api_key="test-token")
        assert adapter.normalizer_version == "1.0.0"


class TestAppleCalendarAdapterFetch:
    """Tests for AppleCalendarAdapter.fetch() method."""

    def test_fetch_single_event_with_notes(self, mock_httpx_client_calendar):
        """fetch() yields NormalizedContent for a single event with notes."""
        adapter = AppleCalendarAdapter(api_url="http://127.0.0.1:7123", api_key="test-token")

        # Mock events response
        events_url = "http://127.0.0.1:7123/calendar/events"
        mock_httpx_client_calendar.set_response(events_url, [
            {
                "id": "event-1",
                "title": "Team meeting",
                "notes": "Discuss Q2 roadmap",
                "startDate": "2026-03-10T10:00:00Z",
                "endDate": "2026-03-10T11:00:00Z",
                "isAllDay": False,
                "calendar": "Work",
                "location": "Zoom",
                "status": "confirmed",
                "lastModified": "2026-03-06T10:00:00Z",
                "attendees": [
                    {"name": "Alice Smith", "email": "alice@example.com"},
                    {"name": "Bob Jones", "email": "bob@example.com"},
                ],
                "recurrence": None,
                "url": None,
            }
        ])

        results = list(adapter.fetch(""))
        assert len(results) == 1
        assert isinstance(results[0], NormalizedContent)
        assert results[0].source_id == "apple_calendar/event-1"
        # Markdown contains just the notes (description body)
        assert results[0].markdown == "Discuss Q2 roadmap"
        # Title is in extra_metadata, not markdown
        assert results[0].structural_hints.extra_metadata["title"] == "Team meeting"

    def test_fetch_event_without_notes_yielded_with_empty_markdown(self, mock_httpx_client_calendar):
        """fetch() yields events with null notes as empty markdown."""
        adapter = AppleCalendarAdapter(api_url="http://127.0.0.1:7123", api_key="test-token")

        events_url = "http://127.0.0.1:7123/calendar/events"
        mock_httpx_client_calendar.set_response(events_url, [
            {
                "id": "event-1",
                "title": "Conference",
                "notes": None,
                "startDate": "2026-03-10T10:00:00Z",
                "endDate": "2026-03-10T15:00:00Z",
                "isAllDay": False,
                "calendar": "Personal",
                "location": None,
                "status": "confirmed",
                "lastModified": "2026-03-06T10:00:00Z",
                "attendees": [],
                "recurrence": None,
                "url": None,
            }
        ])

        results = list(adapter.fetch(""))
        assert len(results) == 1
        assert results[0].markdown == ""
        assert results[0].source_id == "apple_calendar/event-1"

    def test_fetch_incremental_with_since(self, mock_httpx_client_calendar):
        """fetch() passes 'since' query parameter for incremental fetch."""
        adapter = AppleCalendarAdapter(api_url="http://127.0.0.1:7123", api_key="test-token")

        events_url = "http://127.0.0.1:7123/calendar/events"
        mock_httpx_client_calendar.set_response(events_url, [])

        list(adapter.fetch("2026-03-06T10:00:00Z"))

        # Verify the request was made with the 'since' parameter
        request = mock_httpx_client_calendar.requests[0]
        assert request["params"]["since"] == "2026-03-06T10:00:00Z"

    def test_fetch_with_api_key_auth(self, mock_httpx_client_calendar):
        """fetch() sends Authorization header when api_key is provided."""
        adapter = AppleCalendarAdapter(
            api_url="http://127.0.0.1:7123",
            api_key="test_token_123"
        )

        events_url = "http://127.0.0.1:7123/calendar/events"
        mock_httpx_client_calendar.set_response(events_url, [])

        list(adapter.fetch(""))

        # Verify the request was made with Authorization header
        request = mock_httpx_client_calendar.requests[0]
        assert request["headers"]["Authorization"] == "Bearer test_token_123"

    def test_fetch_event_metadata(self, mock_httpx_client_calendar):
        """fetch() extracts correct EventMetadata from event."""
        adapter = AppleCalendarAdapter(api_url="http://127.0.0.1:7123", api_key="test-token")

        events_url = "http://127.0.0.1:7123/calendar/events"
        mock_httpx_client_calendar.set_response(events_url, [
            {
                "id": "event-1",
                "title": "Project deadline",
                "notes": "Final submission",
                "startDate": "2026-03-20T09:00:00Z",
                "endDate": "2026-03-20T17:00:00Z",
                "isAllDay": False,
                "calendar": "Work",
                "location": "Office",
                "status": "confirmed",
                "lastModified": "2026-03-06T10:00:00Z",
                "attendees": [],
                "recurrence": None,
                "url": None,
            }
        ])

        results = list(adapter.fetch(""))
        metadata = EventMetadata.model_validate(results[0].structural_hints.extra_metadata)
        assert metadata.event_id == "event-1"
        assert metadata.title == "Project deadline"
        assert metadata.start_date == "2026-03-20T09:00:00Z"
        assert metadata.end_date == "2026-03-20T17:00:00Z"
        assert metadata.source_type == "apple_calendar"
        assert metadata.host is None  # Host field is mapped but not populated from Apple Calendar API

    def test_fetch_event_date_first_observed_uses_ingestion_time(self, mock_httpx_client_calendar):
        """fetch() sets date_first_observed to current time, not event lastModified."""
        from datetime import datetime, timezone

        adapter = AppleCalendarAdapter(api_url="http://127.0.0.1:7123", api_key="test-token")

        events_url = "http://127.0.0.1:7123/calendar/events"
        # Use an old lastModified timestamp to verify it's not used
        mock_httpx_client_calendar.set_response(events_url, [
            {
                "id": "event-1",
                "title": "Old event",
                "notes": "Description",
                "startDate": "2026-03-20T09:00:00Z",
                "endDate": "2026-03-20T17:00:00Z",
                "isAllDay": False,
                "calendar": "Work",
                "location": "Office",
                "status": "confirmed",
                "lastModified": "2020-01-01T10:00:00Z",  # Old timestamp
                "attendees": [],
                "recurrence": None,
                "url": None,
            }
        ])

        # Capture approximate current time
        before_fetch = datetime.now(timezone.utc)
        results = list(adapter.fetch(""))
        after_fetch = datetime.now(timezone.utc)

        metadata = EventMetadata.model_validate(results[0].structural_hints.extra_metadata)
        observed_time = datetime.fromisoformat(metadata.date_first_observed)

        # Verify date_first_observed is approximately now, not the old lastModified timestamp
        assert before_fetch <= observed_time <= after_fetch
        assert metadata.date_first_observed != "2020-01-01T10:00:00Z"

    def test_fetch_attendees_formatting(self, mock_httpx_client_calendar):
        """fetch() formats attendees as display strings."""
        adapter = AppleCalendarAdapter(api_url="http://127.0.0.1:7123", api_key="test-token")

        events_url = "http://127.0.0.1:7123/calendar/events"
        mock_httpx_client_calendar.set_response(events_url, [
            {
                "id": "event-1",
                "title": "Meeting",
                "notes": "Discussion",
                "startDate": "2026-03-10T10:00:00Z",
                "endDate": "2026-03-10T11:00:00Z",
                "isAllDay": False,
                "calendar": "Work",
                "location": None,
                "status": "confirmed",
                "lastModified": "2026-03-06T10:00:00Z",
                "attendees": [
                    {"name": "Alice Smith", "email": "alice@example.com"},
                    {"name": "Bob", "email": "bob@example.com"},
                ],
                "recurrence": None,
                "url": None,
            }
        ])

        results = list(adapter.fetch(""))
        metadata = EventMetadata.model_validate(results[0].structural_hints.extra_metadata)
        assert len(metadata.invitees) == 2
        assert "Alice Smith <alice@example.com>" in metadata.invitees

    def test_fetch_cancelled_event_status_in_extra_metadata(self, mock_httpx_client_calendar):
        """fetch() preserves cancelled status in extra_metadata."""
        adapter = AppleCalendarAdapter(api_url="http://127.0.0.1:7123", api_key="test-token")

        events_url = "http://127.0.0.1:7123/calendar/events"
        mock_httpx_client_calendar.set_response(events_url, [
            {
                "id": "event-1",
                "title": "Cancelled meeting",
                "notes": "This was cancelled",
                "startDate": "2026-03-10T10:00:00Z",
                "endDate": "2026-03-10T11:00:00Z",
                "isAllDay": False,
                "calendar": "Work",
                "location": None,
                "status": "cancelled",
                "lastModified": "2026-03-06T10:00:00Z",
                "attendees": [],
                "recurrence": None,
                "url": None,
            }
        ])

        results = list(adapter.fetch(""))
        extra = results[0].structural_hints.extra_metadata
        assert extra["status"] == "cancelled"

    def test_fetch_extra_metadata_fields(self, mock_httpx_client_calendar):
        """fetch() includes all required extra_metadata fields."""
        adapter = AppleCalendarAdapter(api_url="http://127.0.0.1:7123", api_key="test-token")

        events_url = "http://127.0.0.1:7123/calendar/events"
        mock_httpx_client_calendar.set_response(events_url, [
            {
                "id": "event-1",
                "title": "Event",
                "notes": "Description",
                "startDate": "2026-03-10T10:00:00Z",
                "endDate": "2026-03-10T11:00:00Z",
                "isAllDay": True,
                "calendar": "Work",
                "location": "Room 123",
                "status": "confirmed",
                "lastModified": "2026-03-06T10:00:00Z",
                "attendees": [],
                "recurrence": {"frequency": "weekly"},
                "url": "https://example.com/event",
            }
        ])

        results = list(adapter.fetch(""))
        extra = results[0].structural_hints.extra_metadata
        assert extra["location"] == "Room 123"
        assert extra["calendar"] == "Work"
        assert extra["status"] == "confirmed"
        assert extra["isAllDay"] is True
        assert extra["recurrence"] == {"frequency": "weekly"}
        assert extra["url"] == "https://example.com/event"
        assert extra["lastModified"] == "2026-03-06T10:00:00Z"

    def test_fetch_http_error_propagates(self, mock_httpx_client_calendar):
        """fetch() propagates HTTP errors."""
        adapter = AppleCalendarAdapter(api_url="http://127.0.0.1:7123", api_key="test-token")

        events_url = "http://127.0.0.1:7123/calendar/events"
        mock_httpx_client_calendar.set_response(events_url, {}, status_code=500)

        with pytest.raises(httpx.HTTPStatusError):
            list(adapter.fetch(""))

    def test_fetch_invalid_response_schema_raises(self, mock_httpx_client_calendar):
        """fetch() raises ValueError if response is not a list."""
        adapter = AppleCalendarAdapter(api_url="http://127.0.0.1:7123", api_key="test-token")

        events_url = "http://127.0.0.1:7123/calendar/events"
        mock_httpx_client_calendar.set_response(events_url, {"events": []})  # Should be a list, not dict

        with pytest.raises(ValueError, match="must be a list"):
            list(adapter.fetch(""))

    def test_fetch_missing_required_field_title_raises(self, mock_httpx_client_calendar):
        """fetch() raises KeyError if event is missing 'title' field."""
        adapter = AppleCalendarAdapter(api_url="http://127.0.0.1:7123", api_key="test-token")

        events_url = "http://127.0.0.1:7123/calendar/events"
        mock_httpx_client_calendar.set_response(events_url, [
            {
                "id": "event-1",
                # Missing 'title'
                "notes": "Description",
                "startDate": "2026-03-10T10:00:00Z",
                "endDate": "2026-03-10T11:00:00Z",
                "isAllDay": False,
                "calendar": "Work",
                "location": None,
                "status": "confirmed",
                "lastModified": "2026-03-06T10:00:00Z",
                "attendees": [],
                "recurrence": None,
                "url": None,
            }
        ])

        with pytest.raises(KeyError, match="title"):
            list(adapter.fetch(""))

    def test_fetch_missing_required_field_id_raises(self, mock_httpx_client_calendar):
        """fetch() raises KeyError if event is missing 'id' field."""
        adapter = AppleCalendarAdapter(api_url="http://127.0.0.1:7123", api_key="test-token")

        events_url = "http://127.0.0.1:7123/calendar/events"
        mock_httpx_client_calendar.set_response(events_url, [
            {
                # Missing 'id'
                "title": "Team meeting",
                "notes": "Description",
                "startDate": "2026-03-10T10:00:00Z",
                "endDate": "2026-03-10T11:00:00Z",
                "isAllDay": False,
                "calendar": "Work",
                "location": None,
                "status": "confirmed",
                "lastModified": "2026-03-06T10:00:00Z",
                "attendees": [],
                "recurrence": None,
                "url": None,
            }
        ])

        with pytest.raises(KeyError, match="id"):
            list(adapter.fetch(""))

    def test_fetch_missing_required_field_lastModified_raises(self, mock_httpx_client_calendar):
        """fetch() raises KeyError if event is missing 'lastModified' field."""
        adapter = AppleCalendarAdapter(api_url="http://127.0.0.1:7123", api_key="test-token")

        events_url = "http://127.0.0.1:7123/calendar/events"
        mock_httpx_client_calendar.set_response(events_url, [
            {
                "id": "event-1",
                "title": "Team meeting",
                "notes": "Description",
                "startDate": "2026-03-10T10:00:00Z",
                "endDate": "2026-03-10T11:00:00Z",
                "isAllDay": False,
                "calendar": "Work",
                "location": None,
                "status": "confirmed",
                # Missing 'lastModified'
                "attendees": [],
                "recurrence": None,
                "url": None,
            }
        ])

        with pytest.raises(KeyError, match="lastModified"):
            list(adapter.fetch(""))

    def test_context_manager_closes_client(self, mock_httpx_client_calendar):
        """Adapter supports context manager and closes client on exit."""
        with AppleCalendarAdapter(api_url="http://127.0.0.1:7123", api_key="test-token") as adapter:
            assert adapter._client is not None
        # Client should be closed after exiting context (close() is called)


class TestAppleCalendarAdapterMarkdownGeneration:
    """Tests for markdown generation in fetch()."""

    def test_markdown_is_notes_body(self, mock_httpx_client_calendar):
        """Generated markdown is the notes/description body only."""
        adapter = AppleCalendarAdapter(api_url="http://127.0.0.1:7123", api_key="test-token")

        events_url = "http://127.0.0.1:7123/calendar/events"
        mock_httpx_client_calendar.set_response(events_url, [
            {
                "id": "event-1",
                "title": "Team standup",
                "notes": "Daily sync",
                "startDate": "2026-03-10T09:00:00Z",
                "endDate": "2026-03-10T09:30:00Z",
                "isAllDay": False,
                "calendar": "Work",
                "location": None,
                "status": "confirmed",
                "lastModified": "2026-03-06T10:00:00Z",
                "attendees": [],
                "recurrence": None,
                "url": None,
            }
        ])

        results = list(adapter.fetch(""))
        # Markdown is just the notes, not the title or metadata
        assert results[0].markdown == "Daily sync"
        # Title is in extra_metadata, used by EventsDomain for context headers
        assert results[0].structural_hints.extra_metadata["title"] == "Team standup"

    def test_markdown_contains_notes(self, mock_httpx_client_calendar):
        """Generated markdown contains the event notes/description."""
        adapter = AppleCalendarAdapter(api_url="http://127.0.0.1:7123", api_key="test-token")

        events_url = "http://127.0.0.1:7123/calendar/events"
        mock_httpx_client_calendar.set_response(events_url, [
            {
                "id": "event-1",
                "title": "Event",
                "notes": "Important description here",
                "startDate": "2026-03-10T10:00:00Z",
                "endDate": "2026-03-10T11:00:00Z",
                "isAllDay": False,
                "calendar": "Work",
                "location": None,
                "status": "confirmed",
                "lastModified": "2026-03-06T10:00:00Z",
                "attendees": [],
                "recurrence": None,
                "url": None,
            }
        ])

        results = list(adapter.fetch(""))
        # Markdown is just the notes
        assert results[0].markdown == "Important description here"


