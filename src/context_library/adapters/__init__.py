"""Adapters module for content normalization from various sources."""

import importlib.util

from context_library.adapters.base import (
    AllEndpointsFailedError,
    BaseAdapter,
    EndpointFetchError,
    PartialFetchError,
    ResetResult,
)
from context_library.adapters.filesystem import FilesystemAdapter
from context_library.adapters.serve import serve_adapter as serve_adapter

__all__ = [
    "AllEndpointsFailedError",
    "BaseAdapter",
    "EndpointFetchError",
    "FilesystemAdapter",
    "PartialFetchError",
    "ResetResult",
    "serve_adapter",
]

# Check if obsidian adapter's dependencies are available
if importlib.util.find_spec("obsidiantools") is not None:
    from context_library.adapters.obsidian import (
        ObsidianAdapter as ObsidianAdapter,
    )

    __all__.append("ObsidianAdapter")

# Check if obsidian tasks adapter's dependencies are available
if importlib.util.find_spec("frontmatter") is not None:
    from context_library.adapters.obsidian_tasks import (
        ObsidianTasksAdapter as ObsidianTasksAdapter,
    )

    __all__.append("ObsidianTasksAdapter")

# Check if email adapter's dependencies are available
if (
    importlib.util.find_spec("httpx") is not None
    and importlib.util.find_spec("html2text") is not None
):
    from context_library.adapters.email import (
        EmailAdapter as EmailAdapter,
    )

    __all__.append("EmailAdapter")

# Check if caldav adapter's dependencies are available
if (
    importlib.util.find_spec("caldav") is not None
    and importlib.util.find_spec("icalendar") is not None
):
    from context_library.adapters.caldav import (
        CalDAVAdapter as CalDAVAdapter,
    )

    __all__.append("CalDAVAdapter")

# Check if apple_calendar adapter's dependencies are available
if importlib.util.find_spec("httpx") is not None:
    from context_library.adapters.apple_calendar import (
        AppleCalendarAdapter as AppleCalendarAdapter,
    )

    __all__.append("AppleCalendarAdapter")

# Check if apple_reminders adapter's dependencies are available
if importlib.util.find_spec("httpx") is not None:
    from context_library.adapters.apple_reminders import (
        AppleRemindersAdapter as AppleRemindersAdapter,
    )

    __all__.append("AppleRemindersAdapter")

# Check if apple_health adapter's dependencies are available
if importlib.util.find_spec("httpx") is not None:
    from context_library.adapters.apple_health import (
        AppleHealthAdapter as AppleHealthAdapter,
    )

    __all__.append("AppleHealthAdapter")

# Check if remote adapter's dependencies are available
if importlib.util.find_spec("httpx") is not None:
    from context_library.adapters.remote import (
        RemoteAdapter as RemoteAdapter,
    )

    __all__.append("RemoteAdapter")

# Check if oura adapter's dependencies are available
if importlib.util.find_spec("httpx") is not None:
    from context_library.adapters.oura import (
        OuraAdapter as OuraAdapter,
    )

    __all__.append("OuraAdapter")

# Check if apple_music adapter's dependencies are available
if importlib.util.find_spec("httpx") is not None:
    from context_library.adapters.apple_music import (
        AppleMusicAdapter as AppleMusicAdapter,
    )

    __all__.append("AppleMusicAdapter")

# Check if apple_music_library adapter's dependencies are available
if importlib.util.find_spec("httpx") is not None:
    from context_library.adapters.apple_music_library import (
        AppleMusicLibraryAdapter as AppleMusicLibraryAdapter,
    )

    __all__.append("AppleMusicLibraryAdapter")

# Check if apple_contacts adapter's dependencies are available
if importlib.util.find_spec("httpx") is not None:
    from context_library.adapters.apple_contacts import (
        AppleContactsAdapter as AppleContactsAdapter,
    )

    __all__.append("AppleContactsAdapter")

# Check if apple_imessage adapter's dependencies are available
if importlib.util.find_spec("httpx") is not None:
    from context_library.adapters.apple_imessage import (
        AppleiMessageAdapter as AppleiMessageAdapter,
    )

    __all__.append("AppleiMessageAdapter")

# Check if apple_notes adapter's dependencies are available
if importlib.util.find_spec("httpx") is not None:
    from context_library.adapters.apple_notes import (
        AppleNotesAdapter as AppleNotesAdapter,
    )

    __all__.append("AppleNotesAdapter")

# Check if apple_podcasts adapter's dependencies are available
if importlib.util.find_spec("httpx") is not None:
    from context_library.adapters.apple_podcasts import (
        ApplePodcastsAdapter as ApplePodcastsAdapter,
    )

    __all__.append("ApplePodcastsAdapter")

# Check if apple_browser_history adapter's dependencies are available
if importlib.util.find_spec("httpx") is not None:
    from context_library.adapters.apple_browser_history import (
        AppleBrowserHistoryAdapter as AppleBrowserHistoryAdapter,
    )

    __all__.append("AppleBrowserHistoryAdapter")

# Check if apple_screentime adapter's dependencies are available
if importlib.util.find_spec("httpx") is not None:
    from context_library.adapters.apple_screentime import (
        AppleScreenTimeAdapter as AppleScreenTimeAdapter,
    )

    __all__.append("AppleScreenTimeAdapter")

# Check if apple_location adapter's dependencies are available
if importlib.util.find_spec("httpx") is not None:
    from context_library.adapters.apple_location import (
        AppleLocationAdapter as AppleLocationAdapter,
    )

    __all__.append("AppleLocationAdapter")

# Check if vcard adapter's dependencies are available
if importlib.util.find_spec("vobject") is not None:
    from context_library.adapters.vcard import (
        VCardAdapter as VCardAdapter,
    )

    __all__.append("VCardAdapter")
