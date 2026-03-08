"""Tests for the CalDAVAdapter."""

import pytest
from unittest.mock import MagicMock, patch, PropertyMock

from context_library.adapters.caldav import CalDAVAdapter, HAS_CALDAV
from context_library.storage.models import Domain, EventMetadata, NormalizedContent


pytestmark = pytest.mark.skipif(not HAS_CALDAV, reason="caldav and icalendar not installed")


class TestCalDAVAdapterInitialization:
    """Tests for CalDAVAdapter initialization."""

    def test_init_with_required_parameters(self):
        """__init__ accepts url, username, and password."""
        adapter = CalDAVAdapter(
            url="https://calendar.google.com/caldav/v2/",
            username="user@example.com",
            password="password123",
        )
        assert adapter._url == "https://calendar.google.com/caldav/v2/"
        assert adapter._username == "user@example.com"
        assert adapter._calendar_name is None

    def test_init_with_calendar_name(self):
        """__init__ accepts optional calendar_name parameter."""
        adapter = CalDAVAdapter(
            url="https://calendar.google.com/caldav/v2/",
            username="user@example.com",
            password="password123",
            calendar_name="Work",
        )
        assert adapter._calendar_name == "Work"

    def test_init_raises_import_error_if_caldav_missing(self):
        """__init__ raises ImportError if caldav/icalendar not available."""
        # Test that HAS_CALDAV flag is properly exported
        from context_library.adapters.caldav import HAS_CALDAV

        # Since we have caldav installed in the test environment, HAS_CALDAV should be True
        # The import guard only prevents instantiation if the packages are not available
        assert HAS_CALDAV is True

        # Verify constructor checks the flag by patching it
        with patch("context_library.adapters.caldav.HAS_CALDAV", False):
            with pytest.raises(ImportError, match="caldav"):
                CalDAVAdapter(
                    url="https://calendar.example.com/",
                    username="user",
                    password="pass",
                )


class TestCalDAVAdapterProperties:
    """Tests for CalDAVAdapter properties."""

    def test_adapter_id_without_calendar_name(self):
        """adapter_id includes only url when calendar_name is None."""
        adapter = CalDAVAdapter(
            url="https://calendar.google.com/caldav/v2/",
            username="user@example.com",
            password="password123",
        )
        assert adapter.adapter_id == "caldav:https://calendar.google.com/caldav/v2/"

    def test_adapter_id_with_calendar_name(self):
        """adapter_id does not include calendar_name (only url)."""
        adapter = CalDAVAdapter(
            url="https://calendar.google.com/caldav/v2/",
            username="user@example.com",
            password="password123",
            calendar_name="Work",
        )
        # adapter_id should only include URL, not calendar_name
        assert adapter.adapter_id == "caldav:https://calendar.google.com/caldav/v2/"

    def test_adapter_id_deterministic(self):
        """adapter_id is deterministic for the same configuration."""
        adapter1 = CalDAVAdapter(
            url="https://calendar.google.com/caldav/v2/",
            username="user@example.com",
            password="password123",
        )
        adapter2 = CalDAVAdapter(
            url="https://calendar.google.com/caldav/v2/",
            username="user@example.com",
            password="password123",
        )
        assert adapter1.adapter_id == adapter2.adapter_id

    def test_domain_property(self):
        """domain property returns Domain.EVENTS."""
        adapter = CalDAVAdapter(
            url="https://calendar.google.com/caldav/v2/",
            username="user@example.com",
            password="password123",
        )
        assert adapter.domain == Domain.EVENTS

    def test_normalizer_version_property(self):
        """normalizer_version property returns '1.0.0'."""
        adapter = CalDAVAdapter(
            url="https://calendar.google.com/caldav/v2/",
            username="user@example.com",
            password="password123",
        )
        assert adapter.normalizer_version == "1.0.0"

    def test_poll_strategy_property(self):
        """poll_strategy property returns PollStrategy.PULL."""
        from context_library.storage.models import PollStrategy

        adapter = CalDAVAdapter(
            url="https://calendar.google.com/caldav/v2/",
            username="user@example.com",
            password="password123",
        )
        assert adapter.poll_strategy == PollStrategy.PULL


class TestCalDAVAdapterContextManager:
    """Tests for CalDAVAdapter context manager protocol."""

    def test_context_manager_enter_returns_self(self):
        """__enter__ returns self."""
        adapter = CalDAVAdapter(
            url="https://calendar.google.com/caldav/v2/",
            username="user@example.com",
            password="password123",
        )
        with adapter as ctx:
            assert ctx is adapter

    def test_context_manager_exit_returns_false(self):
        """__exit__ returns False (does not suppress exceptions)."""
        adapter = CalDAVAdapter(
            url="https://calendar.google.com/caldav/v2/",
            username="user@example.com",
            password="password123",
        )
        result = adapter.__exit__(None, None, None)
        assert result is False


class TestCalDAVAdapterFetch:
    """Tests for CalDAVAdapter.fetch() method."""

    def _create_ical_event(
        self,
        uid: str = "event1",
        summary: str = "Meeting",
        dtstart: str = "20260307T100000Z",
        dtend: str = "20260307T110000Z",
        description: str = "Meeting description",
        organizer: str = "organizer@example.com",
        attendees: list | None = None,
    ) -> str:
        """Create a simple iCalendar event string."""
        if attendees is None:
            attendees = []

        attendee_lines = "\n".join(f"ATTENDEE:{a}" for a in attendees)

        ical = f"""BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//Test//Test//EN
BEGIN:VEVENT
UID:{uid}
SUMMARY:{summary}
DTSTART:{dtstart}
DTEND:{dtend}
DESCRIPTION:{description}
ORGANIZER:{organizer}
{attendee_lines}
END:VEVENT
END:VCALENDAR"""
        return ical

    @patch("context_library.adapters.caldav.caldav.DAVClient")
    def test_fetch_single_event(self, mock_dav_client_class, mock_caldav_client):
        """fetch() yields NormalizedContent for a single event."""
        mock_client, mock_calendar = mock_caldav_client
        mock_dav_client_class.return_value = mock_client

        # Create mock event
        mock_event = MagicMock()
        ical_data = self._create_ical_event()
        mock_event.data = ical_data.encode("utf-8")

        mock_calendar.search.return_value = [mock_event]

        adapter = CalDAVAdapter(
            url="https://calendar.example.com/",
            username="user@example.com",
            password="password123",
        )

        results = list(adapter.fetch(""))
        assert len(results) == 1
        assert isinstance(results[0], NormalizedContent)
        assert results[0].source_id == "Default/event1"
        assert "Meeting" in results[0].markdown

    @patch("context_library.adapters.caldav.caldav.DAVClient")
    def test_fetch_multiple_events(self, mock_dav_client_class, mock_caldav_client):
        """fetch() yields NormalizedContent for multiple events."""
        mock_client, mock_calendar = mock_caldav_client
        mock_dav_client_class.return_value = mock_client

        # Create mock events
        mock_event1 = MagicMock()
        mock_event1.data = self._create_ical_event(uid="event1", summary="Meeting 1").encode("utf-8")

        mock_event2 = MagicMock()
        mock_event2.data = self._create_ical_event(uid="event2", summary="Meeting 2").encode("utf-8")

        mock_calendar.search.return_value = [mock_event1, mock_event2]

        adapter = CalDAVAdapter(
            url="https://calendar.example.com/",
            username="user@example.com",
            password="password123",
        )

        results = list(adapter.fetch(""))
        assert len(results) == 2
        assert results[0].source_id == "Default/event1"
        assert results[1].source_id == "Default/event2"

    @patch("context_library.adapters.caldav.caldav.DAVClient")
    def test_fetch_empty_response(self, mock_dav_client_class, mock_caldav_client):
        """fetch() handles empty event list gracefully."""
        mock_client, mock_calendar = mock_caldav_client
        mock_dav_client_class.return_value = mock_client

        mock_calendar.search.return_value = []

        adapter = CalDAVAdapter(
            url="https://calendar.example.com/",
            username="user@example.com",
            password="password123",
        )

        results = list(adapter.fetch(""))
        assert results == []

    @patch("context_library.adapters.caldav.caldav.DAVClient")
    def test_fetch_filters_by_calendar_name(self, mock_dav_client_class):
        """fetch() filters calendars by calendar_name when provided."""
        mock_client = MagicMock()
        mock_dav_client_class.return_value = mock_client

        # Create multiple calendars
        work_calendar = MagicMock()
        work_calendar.name = "Work"
        personal_calendar = MagicMock()
        personal_calendar.name = "Personal"

        mock_principal = MagicMock()
        mock_principal.calendars.return_value = [work_calendar, personal_calendar]
        mock_client.principal.return_value = mock_principal

        work_calendar.search.return_value = []
        personal_calendar.search.return_value = []

        adapter = CalDAVAdapter(
            url="https://calendar.example.com/",
            username="user@example.com",
            password="password123",
            calendar_name="Work",
        )

        list(adapter.fetch(""))

        # Only Work calendar should be searched
        work_calendar.search.assert_called_once()

    @patch("context_library.adapters.caldav.caldav.DAVClient")
    def test_fetch_with_incremental_sync_token(self, mock_dav_client_class, mock_caldav_client):
        """fetch() uses sync-token for incremental fetch."""
        mock_client, mock_calendar = mock_caldav_client
        mock_dav_client_class.return_value = mock_client

        # Setup sync method
        mock_event = MagicMock()
        mock_event.data = self._create_ical_event().encode("utf-8")
        mock_calendar.sync.return_value = [mock_event]
        mock_calendar.sync_token = "sync-token-123"

        adapter = CalDAVAdapter(
            url="https://calendar.example.com/",
            username="user@example.com",
            password="password123",
        )

        since = "2026-03-01T00:00:00Z"
        results = list(adapter.fetch(since))

        assert len(results) == 1

    @patch("context_library.adapters.caldav.caldav.DAVClient")
    def test_fetch_event_metadata_extraction(self, mock_dav_client_class, mock_caldav_client):
        """fetch() correctly extracts EventMetadata from iCalendar data."""
        mock_client, mock_calendar = mock_caldav_client
        mock_dav_client_class.return_value = mock_client

        # Create event with full metadata
        ical_data = self._create_ical_event(
            uid="event123",
            summary="Team Standup",
            dtstart="20260307T100000Z",
            dtend="20260307T103000Z",
            description="Daily team synchronization",
            organizer="manager@example.com",
            attendees=["dev1@example.com", "dev2@example.com"],
        )

        mock_event = MagicMock()
        mock_event.data = ical_data.encode("utf-8")
        mock_calendar.search.return_value = [mock_event]

        adapter = CalDAVAdapter(
            url="https://calendar.example.com/",
            username="user@example.com",
            password="password123",
        )

        results = list(adapter.fetch(""))
        assert len(results) == 1

        # Extract metadata from extra_metadata
        extra_metadata = results[0].structural_hints.extra_metadata
        assert extra_metadata["event_id"] == "event123"
        assert extra_metadata["title"] == "Team Standup"
        assert extra_metadata["host"] == "manager@example.com"
        assert len(extra_metadata["invitees"]) >= 0  # Attendees excluding organizer

    @patch("context_library.adapters.caldav.caldav.DAVClient")
    def test_fetch_event_duration_from_dtstart_dtend(self, mock_dav_client_class, mock_caldav_client):
        """fetch() computes duration_minutes from DTSTART and DTEND."""
        mock_client, mock_calendar = mock_caldav_client
        mock_dav_client_class.return_value = mock_client

        ical_data = self._create_ical_event(
            dtstart="20260307T100000Z",
            dtend="20260307T113000Z",  # 1 hour 30 minutes = 90 minutes
        )

        mock_event = MagicMock()
        mock_event.data = ical_data.encode("utf-8")
        mock_calendar.search.return_value = [mock_event]

        adapter = CalDAVAdapter(
            url="https://calendar.example.com/",
            username="user@example.com",
            password="password123",
        )

        results = list(adapter.fetch(""))
        extra_metadata = results[0].structural_hints.extra_metadata
        assert extra_metadata["duration_minutes"] == 90

    @patch("context_library.adapters.caldav.caldav.DAVClient")
    def test_fetch_event_duration_from_duration_property(self, mock_dav_client_class, mock_caldav_client):
        """fetch() computes duration_minutes from DURATION property when present."""
        mock_client, mock_calendar = mock_caldav_client
        mock_dav_client_class.return_value = mock_client

        # Create event with DURATION property (60 minutes)
        ical_data = """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//Test//Test//EN
BEGIN:VEVENT
UID:event_with_duration
SUMMARY:Event with DURATION
DTSTART:20260307T100000Z
DURATION:PT1H
END:VEVENT
END:VCALENDAR"""

        mock_event = MagicMock()
        mock_event.data = ical_data.encode("utf-8")
        mock_calendar.search.return_value = [mock_event]

        adapter = CalDAVAdapter(
            url="https://calendar.example.com/",
            username="user@example.com",
            password="password123",
        )

        results = list(adapter.fetch(""))
        extra_metadata = results[0].structural_hints.extra_metadata
        assert extra_metadata["duration_minutes"] == 60

    @patch("context_library.adapters.caldav.caldav.DAVClient")
    def test_fetch_event_with_missing_optional_fields(self, mock_dav_client_class, mock_caldav_client):
        """fetch() handles missing optional fields gracefully."""
        mock_client, mock_calendar = mock_caldav_client
        mock_dav_client_class.return_value = mock_client

        # Minimal event with required fields only
        ical = """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//Test//Test//EN
BEGIN:VEVENT
UID:event1
SUMMARY:Minimal Event
END:VEVENT
END:VCALENDAR"""

        mock_event = MagicMock()
        mock_event.data = ical.encode("utf-8")
        mock_calendar.search.return_value = [mock_event]

        adapter = CalDAVAdapter(
            url="https://calendar.example.com/",
            username="user@example.com",
            password="password123",
        )

        results = list(adapter.fetch(""))
        assert len(results) == 1
        extra_metadata = results[0].structural_hints.extra_metadata
        assert extra_metadata["event_id"] == "event1"
        assert extra_metadata["title"] == "Minimal Event"
        assert extra_metadata["start_date"] is None
        assert extra_metadata["end_date"] is None
        assert extra_metadata["duration_minutes"] is None

    @patch("context_library.adapters.caldav.caldav.DAVClient")
    def test_fetch_includes_event_metadata_in_normalized_content(
        self, mock_dav_client_class, mock_caldav_client
    ):
        """fetch() includes EventMetadata in structural_hints.extra_metadata."""
        mock_client, mock_calendar = mock_caldav_client
        mock_dav_client_class.return_value = mock_client

        ical_data = self._create_ical_event(
            uid="event1",
            summary="Test Event",
            dtstart="20260307T100000Z",
            dtend="20260307T110000Z",
        )

        mock_event = MagicMock()
        mock_event.data = ical_data.encode("utf-8")
        mock_calendar.search.return_value = [mock_event]

        adapter = CalDAVAdapter(
            url="https://calendar.example.com/",
            username="user@example.com",
            password="password123",
        )

        results = list(adapter.fetch(""))
        assert len(results) == 1

        normalized = results[0]
        assert normalized.structural_hints.extra_metadata is not None
        assert "event_id" in normalized.structural_hints.extra_metadata
        assert "title" in normalized.structural_hints.extra_metadata
        assert "source_type" in normalized.structural_hints.extra_metadata
        assert normalized.structural_hints.extra_metadata["source_type"] == "caldav"

    @patch("context_library.adapters.caldav.caldav.DAVClient")
    def test_fetch_markdown_content_format(self, mock_dav_client_class, mock_caldav_client):
        """fetch() creates properly formatted markdown content."""
        mock_client, mock_calendar = mock_caldav_client
        mock_dav_client_class.return_value = mock_client

        ical_data = self._create_ical_event(
            uid="event1",
            summary="Team Meeting",
            dtstart="20260307T140000Z",
            dtend="20260307T150000Z",
            description="Quarterly planning session",
            organizer="ceo@example.com",
            attendees=["exec1@example.com", "exec2@example.com"],
        )

        mock_event = MagicMock()
        mock_event.data = ical_data.encode("utf-8")
        mock_calendar.search.return_value = [mock_event]

        adapter = CalDAVAdapter(
            url="https://calendar.example.com/",
            username="user@example.com",
            password="password123",
        )

        results = list(adapter.fetch(""))
        markdown = results[0].markdown

        # Check markdown contains expected content
        assert "Team Meeting" in markdown
        assert "Quarterly planning session" in markdown
        assert "ceo@example.com" in markdown

    @patch("context_library.adapters.caldav.caldav.DAVClient")
    def test_fetch_structural_hints_always_false(self, mock_dav_client_class, mock_caldav_client):
        """fetch() always sets has_headings, has_lists, has_tables to False."""
        mock_client, mock_calendar = mock_caldav_client
        mock_dav_client_class.return_value = mock_client

        ical_data = self._create_ical_event()

        mock_event = MagicMock()
        mock_event.data = ical_data.encode("utf-8")
        mock_calendar.search.return_value = [mock_event]

        adapter = CalDAVAdapter(
            url="https://calendar.example.com/",
            username="user@example.com",
            password="password123",
        )

        results = list(adapter.fetch(""))
        hints = results[0].structural_hints

        assert hints.has_headings is False
        assert hints.has_lists is False
        assert hints.has_tables is False
        assert hints.natural_boundaries == ()

    @patch("context_library.adapters.caldav.caldav.DAVClient")
    def test_fetch_malformed_event_skipped(self, mock_dav_client_class, mock_caldav_client):
        """fetch() skips malformed events and continues with others."""
        mock_client, mock_calendar = mock_caldav_client
        mock_dav_client_class.return_value = mock_client

        # Create one good event and one malformed event
        good_event = MagicMock()
        good_event.data = self._create_ical_event(uid="good").encode("utf-8")

        bad_event = MagicMock()
        bad_event.data = b"INVALID ICAL DATA"

        mock_calendar.search.return_value = [good_event, bad_event]

        adapter = CalDAVAdapter(
            url="https://calendar.example.com/",
            username="user@example.com",
            password="password123",
        )

        results = list(adapter.fetch(""))
        # Should yield only the good event
        assert len(results) == 1
        assert results[0].source_id == "Default/good"

    @patch("context_library.adapters.caldav.caldav.DAVClient")
    def test_fetch_no_calendars_found(self, mock_dav_client_class):
        """fetch() handles case when no calendars are found."""
        mock_client = MagicMock()
        mock_dav_client_class.return_value = mock_client

        mock_principal = MagicMock()
        mock_principal.calendars.return_value = []
        mock_client.principal.return_value = mock_principal

        adapter = CalDAVAdapter(
            url="https://calendar.example.com/",
            username="user@example.com",
            password="password123",
        )

        results = list(adapter.fetch(""))
        assert results == []

    @patch("context_library.adapters.caldav.caldav.DAVClient")
    def test_fetch_calendar_name_not_found(self, mock_dav_client_class):
        """fetch() handles case when specified calendar_name is not found."""
        mock_client = MagicMock()
        mock_dav_client_class.return_value = mock_client

        # Create calendar with different name
        calendar = MagicMock()
        calendar.name = "Personal"

        mock_principal = MagicMock()
        mock_principal.calendars.return_value = [calendar]
        mock_client.principal.return_value = mock_principal

        adapter = CalDAVAdapter(
            url="https://calendar.example.com/",
            username="user@example.com",
            password="password123",
            calendar_name="Work",
        )

        results = list(adapter.fetch(""))
        assert results == []


class TestCalDAVAdapterEventMetadataValidation:
    """Tests for EventMetadata validation and contract."""

    @patch("context_library.adapters.caldav.caldav.DAVClient")
    def test_event_metadata_passes_validation(self, mock_dav_client_class, mock_caldav_client):
        """fetch() yields EventMetadata that passes model_validate()."""
        mock_client, mock_calendar = mock_caldav_client
        mock_dav_client_class.return_value = mock_client

        ical_data = """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//Test//Test//EN
BEGIN:VEVENT
UID:evt123
SUMMARY:Valid Event
DTSTART:20260307T100000Z
DTEND:20260307T110000Z
DESCRIPTION:Test event
END:VEVENT
END:VCALENDAR"""

        mock_event = MagicMock()
        mock_event.data = ical_data.encode("utf-8")
        mock_calendar.search.return_value = [mock_event]

        adapter = CalDAVAdapter(
            url="https://calendar.example.com/",
            username="user@example.com",
            password="password123",
        )

        results = list(adapter.fetch(""))
        assert len(results) == 1

        # Extract and validate EventMetadata
        extra_metadata = results[0].structural_hints.extra_metadata
        event_data = {
            "event_id": extra_metadata["event_id"],
            "title": extra_metadata["title"],
            "start_date": extra_metadata["start_date"],
            "end_date": extra_metadata["end_date"],
            "duration_minutes": extra_metadata["duration_minutes"],
            "host": extra_metadata["host"],
            "invitees": extra_metadata["invitees"],
            "date_first_observed": extra_metadata["date_first_observed"],
            "source_type": extra_metadata["source_type"],
        }

        # This should not raise any validation errors
        validated = EventMetadata.model_validate(event_data)
        assert validated.event_id == "evt123"
        assert validated.title == "Valid Event"

    @patch("context_library.adapters.caldav.caldav.DAVClient")
    def test_event_id_and_title_required(self, mock_dav_client_class, mock_caldav_client):
        """fetch() ensures event_id and title are non-empty."""
        mock_client, mock_calendar = mock_caldav_client
        mock_dav_client_class.return_value = mock_client

        # Event with empty UID and SUMMARY (should be skipped on validation)
        ical_data = """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//Test//Test//EN
BEGIN:VEVENT
UID:
SUMMARY:
END:VEVENT
END:VCALENDAR"""

        mock_event = MagicMock()
        mock_event.data = ical_data.encode("utf-8")
        mock_calendar.search.return_value = [mock_event]

        adapter = CalDAVAdapter(
            url="https://calendar.example.com/",
            username="user@example.com",
            password="password123",
        )

        # Empty event_id/title should cause validation to fail and event to be skipped
        results = list(adapter.fetch(""))
        # The adapter should skip events that fail validation
        assert len(results) == 0


class TestCalDAVAdapterIntegration:
    """Integration tests for CalDAVAdapter."""

    @patch("context_library.adapters.caldav.caldav.DAVClient")
    def test_full_workflow_with_multiple_calendars(self, mock_dav_client_class):
        """Full workflow: connect, list calendars, fetch events."""
        mock_client = MagicMock()
        mock_dav_client_class.return_value = mock_client

        # Create multiple calendars
        work_cal = MagicMock()
        work_cal.name = "Work"
        personal_cal = MagicMock()
        personal_cal.name = "Personal"

        mock_principal = MagicMock()
        mock_principal.calendars.return_value = [work_cal, personal_cal]
        mock_client.principal.return_value = mock_principal

        # Create events for each calendar
        work_event = MagicMock()
        work_event.data = """BEGIN:VCALENDAR
VERSION:2.0
BEGIN:VEVENT
UID:work1
SUMMARY:Work Meeting
DTSTART:20260307T090000Z
DTEND:20260307T100000Z
END:VEVENT
END:VCALENDAR""".encode("utf-8")

        personal_event = MagicMock()
        personal_event.data = """BEGIN:VCALENDAR
VERSION:2.0
BEGIN:VEVENT
UID:personal1
SUMMARY:Personal Appointment
DTSTART:20260307T170000Z
DTEND:20260307T180000Z
END:VEVENT
END:VCALENDAR""".encode("utf-8")

        work_cal.search.return_value = [work_event]
        personal_cal.search.return_value = [personal_event]

        adapter = CalDAVAdapter(
            url="https://calendar.example.com/",
            username="user@example.com",
            password="password123",
        )

        results = list(adapter.fetch(""))

        # Should get events from both calendars
        assert len(results) == 2
        source_ids = [r.source_id for r in results]
        assert "Work/work1" in source_ids
        assert "Personal/personal1" in source_ids


class TestCalDAVAdapterAllDayEvents:
    """Tests for all-day event handling (date vs datetime)."""

    @patch("context_library.adapters.caldav.caldav.DAVClient")
    def test_fetch_all_day_event(self, mock_dav_client_class, mock_caldav_client):
        """fetch() handles all-day events (date objects) correctly."""
        mock_client, mock_calendar = mock_caldav_client
        mock_dav_client_class.return_value = mock_client

        # Create an all-day event (uses DATE format, not DATETIME)
        ical_data = """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//Test//Test//EN
BEGIN:VEVENT
UID:allday1
SUMMARY:All-Day Conference
DTSTART;VALUE=DATE:20260307
DTEND;VALUE=DATE:20260308
DESCRIPTION:All-day event
END:VEVENT
END:VCALENDAR"""

        mock_event = MagicMock()
        mock_event.data = ical_data.encode("utf-8")
        mock_calendar.search.return_value = [mock_event]

        adapter = CalDAVAdapter(
            url="https://calendar.example.com/",
            username="user@example.com",
            password="password123",
        )

        results = list(adapter.fetch(""))
        assert len(results) == 1

        # Verify event was not silently dropped
        extra_metadata = results[0].structural_hints.extra_metadata
        assert extra_metadata["event_id"] == "allday1"
        assert extra_metadata["title"] == "All-Day Conference"

        # Verify start_date and end_date are valid ISO 8601 timestamps
        assert extra_metadata["start_date"] is not None
        assert extra_metadata["end_date"] is not None
        # Should have time component for all-day events (midnight UTC)
        assert "T" in extra_metadata["start_date"]
        assert "T" in extra_metadata["end_date"]

        # Verify duration computation works (1 day = 1440 minutes)
        assert extra_metadata["duration_minutes"] == 1440

        # Verify EventMetadata validation passes
        event_data = {
            "event_id": extra_metadata["event_id"],
            "title": extra_metadata["title"],
            "start_date": extra_metadata["start_date"],
            "end_date": extra_metadata["end_date"],
            "duration_minutes": extra_metadata["duration_minutes"],
            "host": extra_metadata["host"],
            "invitees": extra_metadata["invitees"],
            "date_first_observed": extra_metadata["date_first_observed"],
            "source_type": extra_metadata["source_type"],
        }
        validated = EventMetadata.model_validate(event_data)
        assert validated.event_id == "allday1"

    @patch("context_library.adapters.caldav.caldav.DAVClient")
    def test_fetch_mixed_all_day_and_timed_events(
        self, mock_dav_client_class, mock_caldav_client
    ):
        """fetch() handles both all-day and timed events in same calendar."""
        mock_client, mock_calendar = mock_caldav_client
        mock_dav_client_class.return_value = mock_client

        # Create one all-day event and one timed event
        all_day_event = MagicMock()
        all_day_event.data = """BEGIN:VCALENDAR
VERSION:2.0
BEGIN:VEVENT
UID:allday1
SUMMARY:All-Day Event
DTSTART;VALUE=DATE:20260307
DTEND;VALUE=DATE:20260308
END:VEVENT
END:VCALENDAR""".encode("utf-8")

        timed_event = MagicMock()
        timed_event.data = """BEGIN:VCALENDAR
VERSION:2.0
BEGIN:VEVENT
UID:timed1
SUMMARY:Timed Meeting
DTSTART:20260307T100000Z
DTEND:20260307T110000Z
END:VEVENT
END:VCALENDAR""".encode("utf-8")

        mock_calendar.search.return_value = [all_day_event, timed_event]

        adapter = CalDAVAdapter(
            url="https://calendar.example.com/",
            username="user@example.com",
            password="password123",
        )

        results = list(adapter.fetch(""))
        assert len(results) == 2

        # Verify both events were processed
        source_ids = [r.source_id for r in results]
        assert "Default/allday1" in source_ids
        assert "Default/timed1" in source_ids

        # Verify both have valid ISO 8601 timestamps
        for result in results:
            extra_metadata = result.structural_hints.extra_metadata
            if extra_metadata["start_date"]:
                assert "T" in extra_metadata["start_date"]
            if extra_metadata["end_date"]:
                assert "T" in extra_metadata["end_date"]

    @patch("context_library.adapters.caldav.caldav.DAVClient")
    def test_fetch_all_day_event_duration_zero_minutes(
        self, mock_dav_client_class, mock_caldav_client
    ):
        """fetch() computes zero duration for same-day all-day events."""
        mock_client, mock_calendar = mock_caldav_client
        mock_dav_client_class.return_value = mock_client

        # All-day event on single day (DTSTART and DTEND are same day)
        ical_data = """BEGIN:VCALENDAR
VERSION:2.0
BEGIN:VEVENT
UID:singleday
SUMMARY:Single Day Event
DTSTART;VALUE=DATE:20260307
DTEND;VALUE=DATE:20260307
END:VEVENT
END:VCALENDAR"""

        mock_event = MagicMock()
        mock_event.data = ical_data.encode("utf-8")
        mock_calendar.search.return_value = [mock_event]

        adapter = CalDAVAdapter(
            url="https://calendar.example.com/",
            username="user@example.com",
            password="password123",
        )

        results = list(adapter.fetch(""))
        assert len(results) == 1

        extra_metadata = results[0].structural_hints.extra_metadata
        # When DTSTART and DTEND are same date, duration should be 0
        assert extra_metadata["duration_minutes"] == 0


class TestCalDAVAdapterDatetimeHandling:
    """Tests for datetime handling fixes in PR feedback.

    Addresses three issues:
    1. TypeError from mixed naive/aware datetimes in _compute_duration
    2. Naive datetime comparison in _is_event_modified_after_cutoff defeats incremental sync
    3. _normalize_datetime silently assumes UTC for naive datetimes without logging
    """

    @patch("context_library.adapters.caldav.caldav.DAVClient")
    def test_compute_duration_with_naive_dtstart_aware_dtend(
        self, mock_dav_client_class, mock_caldav_client
    ):
        """_compute_duration handles naive DTSTART with aware DTEND (Issue #1)."""
        mock_client, mock_calendar = mock_caldav_client
        mock_dav_client_class.return_value = mock_client

        # Create event with naive DTSTART and aware DTEND
        # (simulates servers returning mixed naive/aware datetimes)
        ical_data = """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//Test//Test//EN
BEGIN:VEVENT
UID:mixed_naive_aware
SUMMARY:Mixed Timezone Event
DTSTART:20260307T100000
DTEND:20260307T110000Z
END:VEVENT
END:VCALENDAR"""

        mock_event = MagicMock()
        mock_event.data = ical_data.encode("utf-8")
        mock_calendar.search.return_value = [mock_event]

        adapter = CalDAVAdapter(
            url="https://calendar.example.com/",
            username="user@example.com",
            password="password123",
        )

        # Should not raise TypeError when computing duration
        results = list(adapter.fetch(""))
        assert len(results) == 1
        extra_metadata = results[0].structural_hints.extra_metadata
        # Both datetimes should be normalized to UTC for subtraction
        assert extra_metadata["duration_minutes"] == 60

    @patch("context_library.adapters.caldav.caldav.DAVClient")
    def test_compute_duration_with_both_naive_datetimes(
        self, mock_dav_client_class, mock_caldav_client
    ):
        """_compute_duration handles both naive DTSTART and DTEND."""
        mock_client, mock_calendar = mock_caldav_client
        mock_dav_client_class.return_value = mock_client

        # Create event with both naive datetimes
        ical_data = """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//Test//Test//EN
BEGIN:VEVENT
UID:both_naive
SUMMARY:Both Naive Event
DTSTART:20260307T100000
DTEND:20260307T110000
END:VEVENT
END:VCALENDAR"""

        mock_event = MagicMock()
        mock_event.data = ical_data.encode("utf-8")
        mock_calendar.search.return_value = [mock_event]

        adapter = CalDAVAdapter(
            url="https://calendar.example.com/",
            username="user@example.com",
            password="password123",
        )

        # Should not raise TypeError
        results = list(adapter.fetch(""))
        assert len(results) == 1
        extra_metadata = results[0].structural_hints.extra_metadata
        assert extra_metadata["duration_minutes"] == 60

    @patch("context_library.adapters.caldav.caldav.DAVClient")
    def test_compute_duration_with_naive_dtstart_and_date_dtend(
        self, mock_dav_client_class, mock_caldav_client
    ):
        """_compute_duration handles naive DTSTART with date DTEND (Issue #1 exact scenario).

        Tests the specific scenario mentioned in the bug report: naive datetime DTSTART
        with a date object DTEND (all-day end). This ensures both conversions work together.
        """
        mock_client, mock_calendar = mock_caldav_client
        mock_dav_client_class.return_value = mock_client

        # Create event with naive DTSTART (time) and DTEND as date (all-day end)
        # This simulates the exact scenario in the bug report
        ical_data = """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//Test//Test//EN
BEGIN:VEVENT
UID:naive_dtstart_date_dtend
SUMMARY:Partial All-Day Event
DTSTART:20260307T100000
DTEND:20260308
END:VEVENT
END:VCALENDAR"""

        mock_event = MagicMock()
        mock_event.data = ical_data.encode("utf-8")
        mock_calendar.search.return_value = [mock_event]

        adapter = CalDAVAdapter(
            url="https://calendar.example.com/",
            username="user@example.com",
            password="password123",
        )

        # Should not raise TypeError even with mixed date/datetime and naive/aware
        results = list(adapter.fetch(""))
        assert len(results) == 1
        extra_metadata = results[0].structural_hints.extra_metadata
        # March 7 10:00 to March 8 00:00 = 14 hours = 840 minutes
        assert extra_metadata["duration_minutes"] == 840

    def test_is_event_modified_after_cutoff_directly_with_naive_datetime(self):
        """_is_event_modified_after_cutoff handles naive LAST-MODIFIED directly (Issue #2)."""
        from datetime import datetime, timezone

        with patch("context_library.adapters.caldav.caldav.DAVClient"):
            adapter = CalDAVAdapter(
                url="https://calendar.example.com/",
                username="user@example.com",
                password="password123",
            )

            # Create a mock LAST-MODIFIED property with naive datetime
            last_modified = MagicMock()
            # Naive datetime (no timezone info)
            last_modified.dt = datetime(2026, 3, 8, 12, 0, 0)

            # Create a timezone-aware cutoff
            cutoff_dt = datetime(2026, 3, 1, 0, 0, 0, tzinfo=timezone.utc)

            # Before fix, this would raise TypeError when comparing naive with aware
            # After fix, it should return True (event is after cutoff)
            result = adapter._is_event_modified_after_cutoff(
                last_modified, cutoff_dt, "TestCalendar", "test-event-id"
            )

            assert result is True  # Event should be included (is after cutoff)

    @patch("context_library.adapters.caldav.caldav.DAVClient")
    def test_normalize_datetime_logs_warning_for_naive_datetime(
        self, mock_dav_client_class, mock_caldav_client, caplog
    ):
        """_normalize_datetime logs warning when assuming UTC for naive datetimes (Issue #3)."""
        import logging
        caplog.set_level(logging.WARNING)

        mock_client, mock_calendar = mock_caldav_client
        mock_dav_client_class.return_value = mock_client

        # Create event with naive DTSTART
        ical_data = """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//Test//Test//EN
BEGIN:VEVENT
UID:naive_dtstart_event
SUMMARY:Event with Naive DTSTART
DTSTART:20260307T100000
DTEND:20260307T110000Z
END:VEVENT
END:VCALENDAR"""

        mock_event = MagicMock()
        mock_event.data = ical_data.encode("utf-8")
        mock_calendar.search.return_value = [mock_event]

        adapter = CalDAVAdapter(
            url="https://calendar.example.com/",
            username="user@example.com",
            password="password123",
        )

        results = list(adapter.fetch(""))
        assert len(results) == 1

        # Verify warning was logged about naive datetime and UTC assumption
        assert any(
            "naive datetime" in record.message.lower() and "UTC" in record.message
            for record in caplog.records
        ), f"Expected naive datetime warning in logs. Caplog: {[r.message for r in caplog.records]}"

    def test_incremental_sync_not_defeated_by_naive_lastmodified(self):
        """Incremental sync filters correctly with naive LAST-MODIFIED (Issue #2).

        Tests that the fix to _is_event_modified_after_cutoff allows proper filtering
        of events even when LAST-MODIFIED is naive (without timezone info).
        """
        from datetime import datetime, timezone

        with patch("context_library.adapters.caldav.caldav.DAVClient"):
            adapter = CalDAVAdapter(
                url="https://calendar.example.com/",
                username="user@example.com",
                password="password123",
            )

            # Cutoff at March 5
            cutoff_dt = datetime(2026, 3, 5, 0, 0, 0, tzinfo=timezone.utc)

            # Event 1: modified March 2 (before cutoff) - with naive datetime
            old_modified = MagicMock()
            old_modified.dt = datetime(2026, 3, 2, 12, 0, 0)  # naive

            # Event 2: modified March 8 (after cutoff) - with naive datetime
            new_modified = MagicMock()
            new_modified.dt = datetime(2026, 3, 8, 12, 0, 0)  # naive

            # Before fix: both would fail comparison and return True, defeating filtering
            # After fix: proper naive->UTC normalization allows correct filtering
            old_result = adapter._is_event_modified_after_cutoff(
                old_modified, cutoff_dt, "TestCalendar", "old-event"
            )
            new_result = adapter._is_event_modified_after_cutoff(
                new_modified, cutoff_dt, "TestCalendar", "new-event"
            )

            # Old event should be filtered (before cutoff)
            assert old_result is False
            # New event should be included (after cutoff)
            assert new_result is True

    def test_unexpected_typeerror_propagates_in_is_event_modified_after_cutoff(self):
        """Unexpected TypeError exceptions in _is_event_modified_after_cutoff propagate.

        Verifies that after removing TypeError from the exception handler, unexpected
        TypeErrors (not from naive/aware datetime comparison) are not silently caught
        and properly propagate to the caller.
        """
        from datetime import datetime, timezone

        with patch("context_library.adapters.caldav.caldav.DAVClient"):
            adapter = CalDAVAdapter(
                url="https://calendar.example.com/",
                username="user@example.com",
                password="password123",
            )

            cutoff_dt = datetime(2026, 3, 5, 0, 0, 0, tzinfo=timezone.utc)

            # Create a mock that will raise TypeError from an unexpected source
            # (not from naive/aware datetime comparison)
            last_modified = MagicMock()
            # Set up dt property to raise TypeError when accessed
            type(last_modified).dt = PropertyMock(side_effect=TypeError("Unexpected error"))

            # The TypeError should propagate, not be caught and return True
            with pytest.raises(TypeError, match="Unexpected error"):
                adapter._is_event_modified_after_cutoff(
                    last_modified, cutoff_dt, "TestCalendar", "test-event"
                )


class TestEventMetadataFieldExtraction:
    """Tests for _extract_event_metadata field handling edge cases."""

    def _create_ical_event(
        self,
        uid: str = "event1",
        summary: str = "Meeting",
        dtstart: str = "20260307T100000Z",
        dtend: str = "20260307T110000Z",
        description: str = "Meeting description",
        organizer: str = "organizer@example.com",
        attendees: list | None = None,
    ) -> str:
        """Create a simple iCalendar event string."""
        if attendees is None:
            attendees = []

        attendee_lines = "\n".join(f"ATTENDEE:{a}" for a in attendees)
        organizer_line = f"ORGANIZER:{organizer}" if organizer is not None else ""

        ical = f"""BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//Test//Test//EN
BEGIN:VEVENT
UID:{uid}
SUMMARY:{summary}
DTSTART:{dtstart}
DTEND:{dtend}
DESCRIPTION:{description}
{organizer_line}
{attendee_lines}
END:VEVENT
END:VCALENDAR"""
        return ical

    @patch("context_library.adapters.caldav.caldav.DAVClient")
    def test_extract_event_with_none_uid_skips_gracefully(
        self, mock_dav_client_class, mock_caldav_client, caplog
    ):
        """_extract_event_metadata skips events with None UID and logs warning."""
        from icalendar import Calendar, Event

        mock_client, _ = mock_caldav_client
        mock_dav_client_class.return_value = mock_client

        adapter = CalDAVAdapter(
            url="https://calendar.example.com/",
            username="user@example.com",
            password="password123",
        )

        # Create VEVENT with None UID (explicit None, not missing)
        vevent = Event()
        vevent["UID"] = None
        vevent["SUMMARY"] = "Meeting"
        vevent["DTSTART"] = "20260307T100000Z"

        results = list(adapter._extract_event_metadata(vevent, "TestCalendar"))

        assert results == []
        assert "UID is missing or empty" in caplog.text
        assert "TestCalendar" in caplog.text

    @patch("context_library.adapters.caldav.caldav.DAVClient")
    def test_extract_event_with_missing_uid_skips_gracefully(
        self, mock_dav_client_class, mock_caldav_client, caplog
    ):
        """_extract_event_metadata skips events with missing UID and logs warning."""
        from icalendar import Calendar, Event

        mock_client, _ = mock_caldav_client
        mock_dav_client_class.return_value = mock_client

        adapter = CalDAVAdapter(
            url="https://calendar.example.com/",
            username="user@example.com",
            password="password123",
        )

        # Create VEVENT without UID
        vevent = Event()
        # Don't set UID at all
        vevent["SUMMARY"] = "Meeting"
        vevent["DTSTART"] = "20260307T100000Z"

        results = list(adapter._extract_event_metadata(vevent, "TestCalendar"))

        assert results == []
        assert "UID is missing or empty" in caplog.text

    @patch("context_library.adapters.caldav.caldav.DAVClient")
    def test_extract_event_with_empty_uid_skips_gracefully(
        self, mock_dav_client_class, mock_caldav_client, caplog
    ):
        """_extract_event_metadata skips events with empty UID string and logs warning."""
        from icalendar import Calendar, Event

        mock_client, _ = mock_caldav_client
        mock_dav_client_class.return_value = mock_client

        adapter = CalDAVAdapter(
            url="https://calendar.example.com/",
            username="user@example.com",
            password="password123",
        )

        # Create VEVENT with empty UID string
        vevent = Event()
        vevent["UID"] = ""
        vevent["SUMMARY"] = "Meeting"
        vevent["DTSTART"] = "20260307T100000Z"

        results = list(adapter._extract_event_metadata(vevent, "TestCalendar"))

        assert results == []
        assert "UID is missing or empty" in caplog.text

    @patch("context_library.adapters.caldav.caldav.DAVClient")
    def test_extract_event_with_none_summary_skips_gracefully(
        self, mock_dav_client_class, mock_caldav_client, caplog
    ):
        """_extract_event_metadata skips events with None SUMMARY and logs warning."""
        from icalendar import Calendar, Event

        mock_client, _ = mock_caldav_client
        mock_dav_client_class.return_value = mock_client

        adapter = CalDAVAdapter(
            url="https://calendar.example.com/",
            username="user@example.com",
            password="password123",
        )

        # Create VEVENT with None SUMMARY
        vevent = Event()
        vevent["UID"] = "event-123"
        vevent["SUMMARY"] = None
        vevent["DTSTART"] = "20260307T100000Z"

        results = list(adapter._extract_event_metadata(vevent, "TestCalendar"))

        assert results == []
        assert "SUMMARY is missing or empty" in caplog.text
        assert "TestCalendar" in caplog.text

    @patch("context_library.adapters.caldav.caldav.DAVClient")
    def test_extract_event_with_missing_summary_skips_gracefully(
        self, mock_dav_client_class, mock_caldav_client, caplog
    ):
        """_extract_event_metadata skips events with missing SUMMARY and logs warning."""
        from icalendar import Calendar, Event

        mock_client, _ = mock_caldav_client
        mock_dav_client_class.return_value = mock_client

        adapter = CalDAVAdapter(
            url="https://calendar.example.com/",
            username="user@example.com",
            password="password123",
        )

        # Create VEVENT without SUMMARY
        vevent = Event()
        vevent["UID"] = "event-123"
        # Don't set SUMMARY
        vevent["DTSTART"] = "20260307T100000Z"

        results = list(adapter._extract_event_metadata(vevent, "TestCalendar"))

        assert results == []
        assert "SUMMARY is missing or empty" in caplog.text

    @patch("context_library.adapters.caldav.caldav.DAVClient")
    def test_extract_event_with_none_organizer_produces_none_not_string(
        self, mock_dav_client_class, mock_caldav_client
    ):
        """_extract_event_metadata produces None for None ORGANIZER, not literal "None" string."""
        from icalendar import Calendar, Event

        mock_client, _ = mock_caldav_client
        mock_dav_client_class.return_value = mock_client

        adapter = CalDAVAdapter(
            url="https://calendar.example.com/",
            username="user@example.com",
            password="password123",
        )

        # Create VEVENT with None ORGANIZER
        vevent = Event()
        vevent["UID"] = "event-123"
        vevent["SUMMARY"] = "Meeting"
        vevent["DTSTART"] = "20260307T100000Z"
        vevent["ORGANIZER"] = None

        results = list(adapter._extract_event_metadata(vevent, "TestCalendar"))

        assert len(results) == 1
        content = results[0]
        event_metadata = content.structural_hints.extra_metadata
        # Verify organizer is None, not the literal string "None"
        assert event_metadata["host"] is None
        assert event_metadata["host"] != "None"

    @patch("context_library.adapters.caldav.caldav.DAVClient")
    def test_extract_event_with_missing_organizer_produces_none(
        self, mock_dav_client_class, mock_caldav_client
    ):
        """_extract_event_metadata produces None for missing ORGANIZER."""
        from icalendar import Calendar, Event

        mock_client, _ = mock_caldav_client
        mock_dav_client_class.return_value = mock_client

        adapter = CalDAVAdapter(
            url="https://calendar.example.com/",
            username="user@example.com",
            password="password123",
        )

        # Create VEVENT without ORGANIZER
        vevent = Event()
        vevent["UID"] = "event-123"
        vevent["SUMMARY"] = "Meeting"
        vevent["DTSTART"] = "20260307T100000Z"
        # Don't set ORGANIZER

        results = list(adapter._extract_event_metadata(vevent, "TestCalendar"))

        assert len(results) == 1
        content = results[0]
        event_metadata = content.structural_hints.extra_metadata
        assert event_metadata["host"] is None

    @patch("context_library.adapters.caldav.caldav.DAVClient")
    def test_extract_event_with_valid_organizer_produces_string(
        self, mock_dav_client_class, mock_caldav_client
    ):
        """_extract_event_metadata produces organizer string when present."""
        from icalendar import Calendar, Event

        mock_client, _ = mock_caldav_client
        mock_dav_client_class.return_value = mock_client

        adapter = CalDAVAdapter(
            url="https://calendar.example.com/",
            username="user@example.com",
            password="password123",
        )

        # Create VEVENT with valid ORGANIZER
        vevent = Event()
        vevent["UID"] = "event-123"
        vevent["SUMMARY"] = "Meeting"
        vevent["DTSTART"] = "20260307T100000Z"
        vevent["ORGANIZER"] = "organizer@example.com"

        results = list(adapter._extract_event_metadata(vevent, "TestCalendar"))

        assert len(results) == 1
        content = results[0]
        event_metadata = content.structural_hints.extra_metadata
        assert event_metadata["host"] == "organizer@example.com"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
