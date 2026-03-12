"""Adapters module for content normalization from various sources."""

import importlib.util

from context_library.adapters.base import BaseAdapter
from context_library.adapters.filesystem import FilesystemAdapter
from context_library.adapters.serve import serve_adapter as serve_adapter  # noqa: F401

__all__ = [
    "BaseAdapter",
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

# Check if apple reminders/health adapters' dependencies are available
if importlib.util.find_spec("httpx") is not None:
    from context_library.adapters.apple_reminders import (  # noqa: F401
        AppleRemindersAdapter as AppleRemindersAdapter,
    )
    from context_library.adapters.apple_health import (  # noqa: F401
        AppleHealthAdapter as AppleHealthAdapter,
    )
    from context_library.adapters.remote import (  # noqa: F401
        RemoteAdapter as RemoteAdapter,
    )

    __all__.append("AppleRemindersAdapter")
    __all__.append("AppleHealthAdapter")
    __all__.append("RemoteAdapter")
