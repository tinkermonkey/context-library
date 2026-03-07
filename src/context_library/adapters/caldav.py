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
from datetime import datetime, timedelta
from itertools import chain
from typing import TYPE_CHECKING, Any, Iterator

from context_library.adapters.base import BaseAdapter
from context_library.storage.models import (
    Domain,
    EventMetadata,
    NormalizedContent,
    StructuralHints,
)

logger = logging.getLogger(__name__)

# Optional import guard
try:
    import caldav
    from icalendar import Calendar

    HAS_CALDAV = True
except ImportError:
    HAS_CALDAV = False

if TYPE_CHECKING:
    import caldav as caldav_module
    from icalendar import Calendar as CalendarType


class CalDAVAdapter(BaseAdapter):
    """Adapter that syncs events from a CalDAV server.

    Supports incremental fetch via CalDAV sync-token for efficient delta sync.
    Parses iCalendar data for each event and maps to EventMetadata.
    """

    domain = Domain.EVENTS
    normalizer_version = "1.0.0"

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
        # Note: We store the password for initialization but not permanently for security
        self._password = password
        self._initialized = False

    @property
    def adapter_id(self) -> str:
        """Return a deterministic, unique identifier for this adapter instance."""
        if self._calendar_name:
            return f"caldav:{self._url}:{self._calendar_name}"
        return f"caldav:{self._url}"

    def fetch(self, source_ref: str) -> Iterator[NormalizedContent]:
        """Fetch and normalize calendar events from CalDAV server.

        Args:
            source_ref: ISO 8601 timestamp for incremental fetch, or empty for full fetch

        Yields:
            NormalizedContent: Normalized event with EventMetadata in extra_metadata
        """
        try:
            client = caldav.DAVClient(url=self._url, username=self._username, password=self._password)  # type: ignore
            principal = client.principal()
            calendars = principal.calendars()

            if not calendars:
                logger.warning(
                    f"No calendars found on server {self._url} for user {self._username}"
                )
                return

            # Filter calendars by name if specified
            if self._calendar_name:
                calendars = [
                    cal for cal in calendars if self._calendar_name in (cal.name or cal.get_properties().get("resourcetype"))
                ]
                if not calendars:
                    logger.warning(
                        f"No calendar named {self._calendar_name!r} found on server"
                    )
                    return

            # Process each calendar
            for calendar in calendars:
                yield from self._fetch_from_calendar(calendar, source_ref)

        except Exception as e:
            logger.error(f"Error fetching events from CalDAV server: {e}")
            raise

    def _fetch_from_calendar(
        self, calendar: Any, source_ref: str
    ) -> Iterator[NormalizedContent]:
        """Fetch events from a specific calendar.

        Args:
            calendar: caldav.Calendar instance
            source_ref: ISO 8601 timestamp for filtering events

        Yields:
            NormalizedContent: Normalized event
        """
        try:
            calendar_name = calendar.name or "Default"

            # Determine sync strategy
            if source_ref:
                # Incremental fetch using sync-token
                yield from self._fetch_incremental(calendar, calendar_name, source_ref)
            else:
                # Full fetch
                yield from self._fetch_all_events(calendar, calendar_name)

        except Exception as e:
            logger.error(f"Error fetching from calendar {calendar.name}: {e}")
            raise

    def _fetch_all_events(
        self, calendar: Any, calendar_name: str
    ) -> Iterator[NormalizedContent]:
        """Fetch all events from a calendar.

        Args:
            calendar: caldav.Calendar instance
            calendar_name: Name of the calendar

        Yields:
            NormalizedContent: Normalized event
        """
        try:
            events = calendar.search(
                todo=False,
                event=True,
                journal=False,
                include_duplicates=False,
            )

            for event in events:
                yield from self._process_event(event, calendar_name)

        except Exception as e:
            logger.error(f"Error fetching all events from calendar: {e}")
            raise

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
        """
        try:
            # Parse the timestamp to determine the cutoff
            cutoff_dt = datetime.fromisoformat(source_ref.replace("Z", "+00:00"))

            # Try to use sync-token for efficient delta sync
            try:
                sync_token = getattr(calendar, "sync_token", None)
                if sync_token:
                    # CalDAV sync protocol fetch
                    events = calendar.sync(sync_token)
                    for event in events:
                        yield from self._process_event(event, calendar_name, cutoff_dt)
                else:
                    # Fallback to date-range query
                    yield from self._fetch_by_date_range(
                        calendar, calendar_name, cutoff_dt
                    )
            except Exception:
                # If sync fails, fallback to date-range
                yield from self._fetch_by_date_range(calendar, calendar_name, cutoff_dt)

        except ValueError as e:
            logger.error(f"Invalid source_ref timestamp format: {e}")
            raise

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
        """
        # Set end date to far future to catch all events after start_dt
        end_dt = start_dt + timedelta(days=365 * 10)

        try:
            events = calendar.search(
                todo=False,
                event=True,
                journal=False,
                start=start_dt,
                end=end_dt,
                include_duplicates=False,
            )

            for event in events:
                # Filter by last-modified time as post-processing
                yield from self._process_event(event, calendar_name, start_dt)

        except Exception as e:
            logger.error(f"Error fetching events by date range: {e}")
            raise

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

        except Exception as e:
            logger.error(f"Error processing event: {e}")
            # Skip malformed events rather than failing the entire sync
            pass

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
        try:
            # Extract basic fields
            event_id = str(vevent.get("UID", ""))
            title = str(vevent.get("SUMMARY", ""))
            description = str(vevent.get("DESCRIPTION", "")) or title

            # Handle timestamps
            dtstart = vevent.get("DTSTART")
            dtend = vevent.get("DTEND")

            start_date: str | None = None
            end_date: str | None = None

            if dtstart:
                start_date = dtstart.dt.isoformat()
            if dtend:
                end_date = dtend.dt.isoformat()

            # Compute duration
            duration_minutes = self._compute_duration(vevent, dtstart, dtend)

            # Extract organizer and attendees
            organizer = str(vevent.get("ORGANIZER", "")) or None
            attendees_raw = vevent.get("ATTENDEE", [])
            if not isinstance(attendees_raw, list):
                attendees_raw = [attendees_raw]

            attendees = tuple(
                str(a) for a in attendees_raw if str(a) != organizer
            )

            # Filter by last-modified if cutoff provided
            last_modified = vevent.get("LAST-MODIFIED")
            if cutoff_dt and last_modified:
                try:
                    last_mod_dt = last_modified.dt
                    if isinstance(last_mod_dt, str):
                        last_mod_dt = datetime.fromisoformat(
                            last_mod_dt.replace("Z", "+00:00")
                        )
                    if last_mod_dt <= cutoff_dt:
                        # Event is older than cutoff, skip
                        return
                except Exception as e:
                    logger.debug(f"Error parsing LAST-MODIFIED: {e}")

            # Get current timestamp for date_first_observed
            now = datetime.now(tz=datetime.now().astimezone().tzinfo).isoformat()

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

            # Create structural hints
            structural_hints = StructuralHints(
                has_headings=False,
                has_lists=False,
                has_tables=False,
                natural_boundaries=(),
                extra_metadata={
                    "event_id": event_id,
                    "title": title,
                    "start_date": start_date,
                    "end_date": end_date,
                    "duration_minutes": duration_minutes,
                    "host": organizer,
                    "invitees": attendees,
                    "date_first_observed": now,
                    "source_type": "caldav",
                },
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

        except ValueError as e:
            logger.error(f"Error extracting event metadata: {e}")
            # Skip events that fail validation
            pass
        except Exception as e:
            logger.error(f"Unexpected error extracting event metadata: {e}")
            pass

    def _compute_duration(self, vevent: Any, dtstart: Any, dtend: Any) -> int | None:
        """Compute duration in minutes from DURATION property or DTSTART/DTEND.

        Args:
            vevent: icalendar.cal.Event component
            dtstart: DTSTART property or None
            dtend: DTEND property or None

        Returns:
            Duration in minutes, or None if cannot be computed
        """
        try:
            # Try DURATION property first
            duration = vevent.get("DURATION")
            if duration:
                delta = duration.dt
                if isinstance(delta, timedelta):
                    return int(delta.total_seconds() / 60)

            # Fallback to DTEND - DTSTART
            if dtstart and dtend:
                start = dtstart.dt
                end = dtend.dt
                delta = end - start
                if isinstance(delta, timedelta):
                    return int(delta.total_seconds() / 60)

            return None

        except Exception as e:
            logger.debug(f"Error computing duration: {e}")
            return None

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
