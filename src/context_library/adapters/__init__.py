"""Adapters module for content normalization from various sources."""

import importlib.util

from context_library.adapters.base import BaseAdapter
from context_library.adapters.filesystem import FilesystemAdapter
from context_library.adapters.obsidian import ObsidianAdapter

__all__ = [
    "BaseAdapter",
    "FilesystemAdapter",
    "ObsidianAdapter",
]

# Check if email adapter is available
if importlib.util.find_spec("context_library.adapters.email") is not None:
    from context_library.adapters.email import EmailAdapter as EmailAdapter  # noqa: F401

    __all__.append("EmailAdapter")
