"""Adapters module for content normalization from various sources."""

import importlib.util

from context_library.adapters.base import BaseAdapter
from context_library.adapters.filesystem import FilesystemAdapter

__all__ = [
    "BaseAdapter",
    "FilesystemAdapter",
]

# Check if obsidian adapter's dependencies are available
if importlib.util.find_spec("obsidiantools") is not None:
    from context_library.adapters.obsidian import ObsidianAdapter as ObsidianAdapter  # noqa: F401

    __all__.append("ObsidianAdapter")

# Check if email adapter's dependencies are available
if (
    importlib.util.find_spec("httpx") is not None
    and importlib.util.find_spec("html2text") is not None
):
    from context_library.adapters.email import EmailAdapter as EmailAdapter  # noqa: F401

    __all__.append("EmailAdapter")
