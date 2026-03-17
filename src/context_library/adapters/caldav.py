"""CalDAV adapter for syncing calendar events using CalDAV (RFC 4791) and iCalendar (RFC 5545).

This adapter supports broad compatibility with calendar servers including:
- Google Calendar
- Apple Calendar
- Fastmail
- Nextcloud
- Self-hosted calendar servers (e.g., Radicale, Baïkal)

The adapter uses incremental fetch via CalDAV sync-token for efficient delta sync.
"""

from __future__ import annotations

import logging
from datetime import date, datetime, time, timedelta, timezone
from typing import Any, Iterator, Literal

from context_library.adapters.base import BaseAdapter
from context_library.storage.models import (
    Domain,
    EventMetadata,
    NormalizedContent,
    PollStrategy,
    StructuralHints,
)

logger = logging.getLogger(__name__)

# Optional import guard
try:
    import caldav
    from caldav.lib.error import DAVError
    from icalendar import Calendar

    HAS_CALDAV = True
except ImportError:
    HAS_CALDAV = False


class CalDAVAdapter(BaseAdapter):
    """Adapter that syncs events from a CalDAV server.

    Supports incremental fetch via CalDAV sync-token for efficient delta sync.
    Parses iCalendar data for each event and maps to EventMetadata.
    """

    def __init__(
        self,
        url: str,
        username: str,
        password: str,
        calendar_name: str | None = None,
    ) -> None:
        """Initialize CalDAVAdapter.

        Args:
            url: CalDAV server URL (e.g., https://calendar.google.com/caldav/v2/)
            username: Username for authentication
            password: Password or app-specific token for authentication
            calendar_name: Optional calendar name to filter to a specific calendar
        """
        if not HAS_CALDAV:
            raise ImportError(
                "CalDAV adapter requires 'caldav' and 'icalendar' packages. "
                "Install with: pip install context-library[caldav]"
            )

        self._url = url
        self._username = username
        self._calendar_name = calendar_name
        self._client = caldav.DAVClient(url=self._url, username=self._username, password=password)  # type: ignore

    @property
    def adapter_id(self) -> str:
        """Return a deterministic, unique identifier for this adapter instance."""
        return f"caldav:{self._username}@{self._url}"

    @property
    def domain(self) -> Domain:
        """Return the domain this adapter serves."""
        return Domain.EVENTS

    @property
    def poll_strategy(self) -> PollStrategy:
        """Return the polling strategy for this adapter."""
        return PollStrategy.PULL

    @property
    def normalizer_version(self) -> str:
        """Return the normalizer version."""
        return "1.0.0"

    def __enter__(self):
        """Context manager entry: return self for use in with statement."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> Literal[False]:
        """Context manager exit: clean up DAVClient session."""
        self._client.close()
        return False

    def __del__(self) -> None:
        """Clean up DAVClient session when adapter is destroyed (safety net)."""
        if hasattr(self, "_client"):
            self._client.close()

    def fetch(self, source_ref: str) -> Iterator[NormalizedContent]:
        """Fetch and normalize calendar events from CalDAV server.

        Args:
            source_ref: ISO 8601 timestamp for incremental fetch, or empty for full fetch

        Yields:
            NormalizedContent: Normalized event with EventMetadata in extra_metadata
        """
        principal = self._client.principal()
        calendars = principal.calendars()

        if not calendars:
            logger.warning(
                f"No calendars found on server {self._url} for user {self._username}"
            )
            return

        # Filter calendars by name if specified
        if self._calendar_name:
            calendars = [cal for cal in calendars if cal.name == self._calendar_name]
            if not calendars:
                logger.warning(
                    f"No calendar named {self._calendar_name!r} found on server"
                )
                return

        # Process each calendar
        for calendar in calendars:
            yield from self._fetch_from_calendar(calendar, source_ref)

    def _fetch_from_calendar(
        self, calendar: Any, source_ref: str
    ) -> Iterator[NormalizedContent]:
        """Fetch events from a specific calendar.

        Args:
            calendar: caldav.Calendar instance
            source_ref: ISO 8601 timestamp for filtering events

        Yields:
            NormalizedContent: Normalized event

        Raises:
            RuntimeError: If all events encountered UnicodeDecodeError (aggregate error reporting)
        """
        calendar_name = calendar.name or "Default"

        # Determine sync strategy
        if source_ref:
            # Incremental fetch using sync-token
            yield from self._fetch_incremental(calendar, calendar_name, source_ref)
        else:
            # Full fetch
            yield from self._fetch_all_events(calendar, calendar_name)

    def _fetch_all_events(
        self, calendar: Any, calendar_name: str
    ) -> Iterator[NormalizedContent]:
        """Fetch all events from a calendar.

        Args:
            calendar: caldav.Calendar instance
            calendar_name: Name of the calendar

        Yields:
            NormalizedContent: Normalized event

        Raises:
            RuntimeError: If all events encountered UnicodeDecodeError
                (via _process_events_with_aggregate_check)
        """
        events = calendar.search(
            todo=False,
            event=True,
            journal=False,
            include_duplicates=False,
        )

        yield from self._process_events_with_aggregate_check(
            events, calendar_name
        )

    def _fetch_incremental(
        self, calendar: Any, calendar_name: str, source_ref: str
    ) -> Iterator[NormalizedContent]:
        """Fetch events modified after a given timestamp.

        Args:
            calendar: caldav.Calendar instance
            calendar_name: Name of the calendar
            source_ref: ISO 8601 timestamp string for filtering

        Yields:
            NormalizedContent: Normalized event modified after source_ref

        Raises:
            RuntimeError: If all events encountered UnicodeDecodeError

        Notes:
            Event processing errors (from _process_event) propagate to caller.
            Only CalDAV-specific sync errors trigger fallback to date-range query.
        """
        # Parse the timestamp to determine the cutoff
        cutoff_dt = datetime.fromisoformat(source_ref.replace("Z", "+00:00"))

        # Try to use sync-token for efficient delta sync
        sync_token = getattr(calendar, "sync_token", None)
        if sync_token:
            try:
                # CalDAV sync protocol fetch - only catch sync-level errors
                events = calendar.sync(sync_token)
            except DAVError as e:
                # If sync fails, fallback to date-range
                logger.warning(
                    f"Sync-token fetch failed for calendar {calendar_name!r}: {e}. "
                    f"Falling back to date-range query."
                )
                yield from self._fetch_by_date_range(calendar, calendar_name, cutoff_dt)
                return

            # Process events with aggregate error tracking
            yield from self._process_events_with_aggregate_check(
                events, calendar_name, cutoff_dt
            )
        else:
            # No sync token available, use date-range query
            yield from self._fetch_by_date_range(calendar, calendar_name, cutoff_dt)

    def _fetch_by_date_range(
        self, calendar: Any, calendar_name: str, start_dt: datetime
    ) -> Iterator[NormalizedContent]:
        """Fetch events within a date range.

        Args:
            calendar: caldav.Calendar instance
            calendar_name: Name of the calendar
            start_dt: Start datetime for filtering

        Yields:
            NormalizedContent: Normalized event within date range

        Raises:
            RuntimeError: If all events encountered UnicodeDecodeError
                (via _process_events_with_aggregate_check)
        """
        # Set end date to far future to catch all events after start_dt
        end_dt = start_dt + timedelta(days=365 * 10)

        events = calendar.search(
            todo=False,
            event=True,
            journal=False,
            start=start_dt,
            end=end_dt,
            include_duplicates=False,
        )

        yield from self._process_events_with_aggregate_check(
            events, calendar_name, start_dt
        )

    def _process_events_with_aggregate_check(
        self,
        events: Any,
        calendar_name: str,
        cutoff_dt: datetime | None = None,
    ) -> Iterator[NormalizedContent]:
        """Process events with aggregate error tracking.

        Only raises RuntimeError if all events encountered UnicodeDecodeError
        (actual encoding errors), not if they were filtered out by other criteria.

        Args:
            events: Iterable of caldav.Event instances
            calendar_name: Name of the calendar
            cutoff_dt: Optional datetime cutoff for filtering by LAST-MODIFIED

        Yields:
            NormalizedContent: Normalized event

        Raises:
            RuntimeError: If all events encountered UnicodeDecodeError
        """
        events_list = list(events)
        if not events_list:
            return

        unicode_error_count = 0
        for event in events_list:
            try:
                for item in self._process_event(event, calendar_name, cutoff_dt):
                    yield item
            except UnicodeDecodeError:
                # Track actual encoding errors separately
                unicode_error_count += 1

        # If all events encountered UnicodeDecodeError, raise aggregate error
        if unicode_error_count > 0 and unicode_error_count == len(events_list):
            raise RuntimeError(
                f"Failed to process all {len(events_list)} events from calendar "
                f"{calendar_name!r}: all events encountered UnicodeDecodeError when decoding iCalendar data"
            )

    def _process_event(
        self,
        event: Any,
        calendar_name: str,
        cutoff_dt: datetime | None = None,
    ) -> Iterator[NormalizedContent]:
        """Process a single event and yield NormalizedContent.

        Args:
            event: caldav.Event instance
            calendar_name: Name of the calendar
            cutoff_dt: Optional datetime cutoff for filtering by LAST-MODIFIED

        Yields:
            NormalizedContent: Normalized event

        Raises:
            UnicodeDecodeError: If event data cannot be decoded as UTF-8 (for aggregate tracking)

        Notes:
            Errors in event parsing or metadata extraction propagate to caller for visibility.
            Only UnicodeDecodeError is caught, logged, and re-raised for aggregate error tracking.
        """
        try:
            ical_data = event.data
            if isinstance(ical_data, bytes):
                ical_data = ical_data.decode("utf-8")

            calendar = Calendar.from_ical(ical_data)

            # Extract VEVENT components
            for component in calendar.walk():
                if component.name == "VEVENT":
                    yield from self._extract_event_metadata(
                        component, calendar_name, cutoff_dt
                    )

        except UnicodeDecodeError as e:
            logger.warning(
                f"Skipping event from calendar {calendar_name!r}: "
                f"Failed to decode iCalendar data: {e}"
            )
            raise
        except ValueError as e:
            logger.warning(
                f"Skipping event from calendar {calendar_name!r}: "
                f"Failed to parse iCalendar data: {e}"
            )
            raise UnicodeDecodeError("utf-8", b"", 0, 1, "Invalid iCalendar data")

    def _extract_event_metadata(
        self,
        vevent: Any,
        calendar_name: str,
        cutoff_dt: datetime | None = None,
    ) -> Iterator[NormalizedContent]:
        """Extract EventMetadata from a VEVENT component.

        Args:
            vevent: icalendar.cal.Event component
            calendar_name: Name of the calendar
            cutoff_dt: Optional datetime cutoff for filtering by LAST-MODIFIED

        Yields:
            NormalizedContent: Normalized event with EventMetadata
        """
        # Extract basic fields with explicit presence checks (following Apple Reminders pattern)
        uid = vevent.get("UID")
        if "UID" not in vevent:
            # Missing UID: log warning and skip event
            logger.warning(
                f"Skipping event from calendar {calendar_name!r}: "
                "UID is missing (required for event identification)"
            )
            return
        # UID is present but may be None or empty after string conversion
        uid_str = str(uid).strip() if uid is not None else ""
        if not uid_str:
            # Empty UID after conversion: log warning and skip event
            logger.warning(
                f"Skipping event from calendar {calendar_name!r}: "
                "UID is empty (required for event identification)"
            )
            return
        event_id = uid_str

        summary = vevent.get("SUMMARY")
        if summary is None:
            # Missing SUMMARY: log warning and skip event
            logger.warning(
                f"Skipping event from calendar {calendar_name!r}: "
                "SUMMARY is missing (required for event title)"
            )
            return
        # Convert to string before checking emptiness to handle vText objects
        summary_str = str(summary).strip()
        if not summary_str:
            # Empty SUMMARY after conversion: log warning and skip event
            logger.warning(
                f"Skipping event from calendar {calendar_name!r}: "
                "SUMMARY is empty (required for event title)"
            )
            return
        title = summary_str

        description_field = vevent.get("DESCRIPTION")
        description = (str(description_field) if description_field is not None else "") or title

        # Handle timestamps
        dtstart = vevent.get("DTSTART")
        dtend = vevent.get("DTEND")

        start_date: str | None = None
        end_date: str | None = None

        if dtstart:
            dt_value = dtstart.dt if hasattr(dtstart, 'dt') else dtstart
            start_date = self._normalize_datetime(dt_value)
        if dtend:
            dt_value = dtend.dt if hasattr(dtend, 'dt') else dtend
            end_date = self._normalize_datetime(dt_value)

        # Compute duration
        duration_minutes = self._compute_duration(vevent, dtstart, dtend)

        # Extract organizer and attendees (explicit presence check prevents "None" string)
        organizer_field = vevent.get("ORGANIZER")
        organizer = str(organizer_field) if organizer_field is not None else None
        attendees_raw = vevent.get("ATTENDEE", [])
        if not isinstance(attendees_raw, list):
            attendees_raw = [attendees_raw]

        attendees = tuple(str(a) for a in attendees_raw if str(a) != organizer)

        # Filter by last-modified if cutoff provided
        last_modified = vevent.get("LAST-MODIFIED")
        if cutoff_dt and last_modified:
            if not self._is_event_modified_after_cutoff(
                last_modified, cutoff_dt, calendar_name, event_id
            ):
                # Event is older than cutoff, skip
                return

        # Get current timestamp for date_first_observed
        now = datetime.now(timezone.utc).isoformat()

        # Create EventMetadata
        event_metadata = EventMetadata(
            event_id=event_id,
            title=title,
            start_date=start_date,
            end_date=end_date,
            duration_minutes=duration_minutes,
            host=organizer,
            invitees=attendees,
            date_first_observed=now,
            source_type="caldav",
        )

        # Create source_id
        source_id = f"{calendar_name}/{event_id}"

        # Create structural hints with metadata dumped from model
        structural_hints = StructuralHints(
            has_headings=False,
            has_lists=False,
            has_tables=False,
            natural_boundaries=(),
            extra_metadata=event_metadata.model_dump(),
        )

        # Create markdown content
        markdown = self._create_markdown(
            title, description, start_date, end_date, organizer, attendees
        )

        # Create NormalizedContent
        normalized_content = NormalizedContent(
            markdown=markdown,
            source_id=source_id,
            structural_hints=structural_hints,
            normalizer_version=self.normalizer_version,
        )

        yield normalized_content

    def _compute_duration(self, vevent: Any, dtstart: Any, dtend: Any) -> int | None:
        """Compute duration in minutes from DURATION property or DTSTART/DTEND.

        Args:
            vevent: icalendar.cal.Event component
            dtstart: DTSTART property or None
            dtend: DTEND property or None

        Returns:
            Duration in minutes, or None if cannot be computed

        Raises:
            TypeError: Only if neither DTSTART nor DTEND can be converted to datetime objects
        """
        # Try DURATION property first
        duration = vevent.get("DURATION")
        if duration:
            delta = duration.dt if hasattr(duration, 'dt') else duration
            if isinstance(delta, timedelta):
                return int(delta.total_seconds() / 60)

        # Fallback to DTEND - DTSTART
        if dtstart and dtend:
            start = dtstart.dt if hasattr(dtstart, 'dt') else dtstart
            end = dtend.dt if hasattr(dtend, 'dt') else dtend
            # Normalize date objects to datetime for consistent subtraction
            if isinstance(start, date) and not isinstance(start, datetime):
                start = datetime.combine(start, time.min, timezone.utc)
            if isinstance(end, date) and not isinstance(end, datetime):
                end = datetime.combine(end, time.min, timezone.utc)

            # Normalize naive datetimes to UTC (matching _normalize_datetime behavior)
            if isinstance(start, datetime) and start.tzinfo is None:
                logger.warning(f"Naive DTSTART {start!r}; assuming UTC.")
                start = start.replace(tzinfo=timezone.utc)
            if isinstance(end, datetime) and end.tzinfo is None:
                logger.warning(f"Naive DTEND {end!r}; assuming UTC.")
                end = end.replace(tzinfo=timezone.utc)

            delta = end - start
            if isinstance(delta, timedelta):
                return int(delta.total_seconds() / 60)

        return None

    def _normalize_datetime(self, dt_value: date | datetime | str) -> str:
        """Normalize date/datetime to ISO 8601 timestamp string.

        Converts all-day events (represented as date objects) to midnight UTC datetimes
        to ensure consistent ISO 8601 timestamp format (YYYY-MM-DDTHH:MM:SS±HH:MM).

        For naive datetimes (which lack timezone info), assumes UTC. This is a best-effort
        assumption that may be incorrect for self-hosted servers returning local time.
        A warning is logged when this assumption is made.

        Args:
            dt_value: A datetime.date, datetime.datetime, or ISO 8601 string from iCalendar

        Returns:
            ISO 8601 timestamp string in UTC
        """
        # Handle string values (raw iCalendar data)
        if isinstance(dt_value, str):
            # Parse ISO 8601 string, handling both Z and +00:00 formats
            dt_value = datetime.fromisoformat(dt_value.replace("Z", "+00:00"))

        if isinstance(dt_value, datetime):
            # Already a datetime, convert to UTC if needed
            if dt_value.tzinfo is None:
                # Naive datetime, assume UTC (with warning)
                logger.warning(
                    f"Naive datetime {dt_value!r} in iCalendar data; assuming UTC."
                )
                return dt_value.replace(tzinfo=timezone.utc).isoformat()
            else:
                # Aware datetime, convert to UTC and return ISO format
                return dt_value.astimezone(timezone.utc).isoformat()
        else:
            # It's a date object (all-day event), convert to midnight UTC
            return datetime.combine(dt_value, time.min, timezone.utc).isoformat()

    def _is_event_modified_after_cutoff(
        self,
        last_modified: Any,
        cutoff_dt: datetime,
        calendar_name: str,
        event_id: str,
    ) -> bool:
        """Check if event's LAST-MODIFIED is after the cutoff datetime.

        Args:
            last_modified: LAST-MODIFIED property from vevent
            cutoff_dt: Cutoff datetime for filtering (must be timezone-aware)
            calendar_name: Name of the calendar (for logging)
            event_id: Event UID (for logging)

        Returns:
            True if event is modified after cutoff (should be included),
            False if event is older than cutoff (should be skipped),
            True if LAST-MODIFIED cannot be parsed or is non-datetime type (include for safety)

        Notes:
            ValueError and AttributeError during LAST-MODIFIED parsing are caught
            and logged; the event is included (safety-first approach).
        """
        try:
            last_mod_dt = last_modified.dt if hasattr(last_modified, 'dt') else last_modified
            if isinstance(last_mod_dt, str):
                last_mod_dt = datetime.fromisoformat(last_mod_dt.replace("Z", "+00:00"))
            if isinstance(last_mod_dt, datetime):
                # Normalize naive datetimes to UTC for comparison
                if last_mod_dt.tzinfo is None:
                    logger.warning(
                        f"Event {event_id!r} LAST-MODIFIED is naive; assuming UTC."
                    )
                    last_mod_dt = last_mod_dt.replace(tzinfo=timezone.utc)
                return last_mod_dt > cutoff_dt
            else:
                # For non-datetime types, include event for safety
                logger.warning(
                    f"Cannot parse LAST-MODIFIED for event {event_id!r} "
                    f"in calendar {calendar_name!r}: unexpected type {type(last_mod_dt)}. "
                    f"Including event in sync."
                )
                return True
        except (ValueError, AttributeError) as e:
            # Log parse failure and include event for safety
            logger.warning(
                f"Cannot parse LAST-MODIFIED for event {event_id!r} "
                f"in calendar {calendar_name!r}: {e}. Including event in sync."
            )
            return True

    def _create_markdown(
        self,
        title: str,
        description: str,
        start_date: str | None,
        end_date: str | None,
        organizer: str | None,
        attendees: tuple[str, ...],
    ) -> str:
        """Create markdown representation of event.

        Args:
            title: Event title
            description: Event description
            start_date: Start date (ISO 8601)
            end_date: End date (ISO 8601)
            organizer: Organizer email/name
            attendees: Tuple of attendee emails/names

        Returns:
            Markdown string
        """
        lines = [f"# {title}\n"]

        if start_date:
            lines.append(f"**Start:** {start_date}\n")
        if end_date:
            lines.append(f"**End:** {end_date}\n")
        if organizer:
            lines.append(f"**Organizer:** {organizer}\n")

        if attendees:
            attendee_list = "\n".join(f"- {a}" for a in attendees)
            lines.append(f"\n**Attendees:**\n{attendee_list}\n")

        if description and description != title:
            lines.append(f"\n{description}\n")

        return "".join(lines)
