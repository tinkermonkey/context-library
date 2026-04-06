"""Adapters module for content normalization from various sources."""

import importlib.util

from context_library.adapters.base import BaseAdapter, EndpointFetchError, PartialFetchError, AllEndpointsFailedError
from context_library.adapters.filesystem import FilesystemAdapter
from context_library.adapters.serve import serve_adapter as serve_adapter  # noqa: F401

__all__ = [
    "BaseAdapter",
    "EndpointFetchError",
    "PartialFetchError",
    "AllEndpointsFailedError",
    "FilesystemAdapter",
    "serve_adapter",
]

# Check if obsidian adapter's dependencies are available
if importlib.util.find_spec("obsidiantools") is not None:
    from context_library.adapters.obsidian import ObsidianAdapter as ObsidianAdapter  # noqa: F401

    __all__.append("ObsidianAdapter")

# Check if obsidian tasks adapter's dependencies are available
if importlib.util.find_spec("frontmatter") is not None:
    from context_library.adapters.obsidian_tasks import (  # noqa: F401
        ObsidianTasksAdapter as ObsidianTasksAdapter,
    )

    __all__.append("ObsidianTasksAdapter")

# Check if email adapter's dependencies are available
if (
    importlib.util.find_spec("httpx") is not None
    and importlib.util.find_spec("html2text") is not None
):
    from context_library.adapters.email import EmailAdapter as EmailAdapter  # noqa: F401

    __all__.append("EmailAdapter")

# Check if caldav adapter's dependencies are available
if (
    importlib.util.find_spec("caldav") is not None
    and importlib.util.find_spec("icalendar") is not None
):
    from context_library.adapters.caldav import CalDAVAdapter as CalDAVAdapter  # noqa: F401

    __all__.append("CalDAVAdapter")

# Check if apple_calendar adapter's dependencies are available
if importlib.util.find_spec("httpx") is not None:
    from context_library.adapters.apple_calendar import (  # noqa: F401
        AppleCalendarAdapter as AppleCalendarAdapter,
    )

    __all__.append("AppleCalendarAdapter")

# Check if apple_reminders adapter's dependencies are available
if importlib.util.find_spec("httpx") is not None:
    from context_library.adapters.apple_reminders import (  # noqa: F401
        AppleRemindersAdapter as AppleRemindersAdapter,
    )

    __all__.append("AppleRemindersAdapter")

# Check if apple_health adapter's dependencies are available
if importlib.util.find_spec("httpx") is not None:
    from context_library.adapters.apple_health import (  # noqa: F401
        AppleHealthAdapter as AppleHealthAdapter,
    )

    __all__.append("AppleHealthAdapter")

# Check if remote adapter's dependencies are available
if importlib.util.find_spec("httpx") is not None:
    from context_library.adapters.remote import (  # noqa: F401
        RemoteAdapter as RemoteAdapter,
    )

    __all__.append("RemoteAdapter")

# Check if oura adapter's dependencies are available
if importlib.util.find_spec("httpx") is not None:
    from context_library.adapters.oura import (  # noqa: F401
        OuraAdapter as OuraAdapter,
    )

    __all__.append("OuraAdapter")

# Check if apple_music_library adapter's dependencies are available
if importlib.util.find_spec("httpx") is not None:
    from context_library.adapters.apple_music_library import (  # noqa: F401
        AppleMusicLibraryAdapter as AppleMusicLibraryAdapter,
    )

    __all__.append("AppleMusicLibraryAdapter")

# Check if apple_contacts adapter's dependencies are available
if importlib.util.find_spec("httpx") is not None:
    from context_library.adapters.apple_contacts import (  # noqa: F401
        AppleContactsAdapter as AppleContactsAdapter,
    )

    __all__.append("AppleContactsAdapter")

# Check if apple_imessage adapter's dependencies are available
if importlib.util.find_spec("httpx") is not None:
    from context_library.adapters.apple_imessage import (  # noqa: F401
        AppleiMessageAdapter as AppleiMessageAdapter,
    )

    __all__.append("AppleiMessageAdapter")

# Check if apple_notes adapter's dependencies are available
if importlib.util.find_spec("httpx") is not None:
    from context_library.adapters.apple_notes import (  # noqa: F401
        AppleNotesAdapter as AppleNotesAdapter,
    )

    __all__.append("AppleNotesAdapter")

# Check if apple_podcasts adapter's dependencies are available
if importlib.util.find_spec("httpx") is not None:
    from context_library.adapters.apple_podcasts import (  # noqa: F401
        ApplePodcastsAdapter as ApplePodcastsAdapter,
    )

    __all__.append("ApplePodcastsAdapter")

# Check if apple_browser_history adapter's dependencies are available
if importlib.util.find_spec("httpx") is not None:
    from context_library.adapters.apple_browser_history import (  # noqa: F401
        AppleBrowserHistoryAdapter as AppleBrowserHistoryAdapter,
    )

    __all__.append("AppleBrowserHistoryAdapter")

# Check if vcard adapter's dependencies are available
if importlib.util.find_spec("vobject") is not None:
    from context_library.adapters.vcard import (  # noqa: F401
        VCardAdapter as VCardAdapter,
    )

    __all__.append("VCardAdapter")
