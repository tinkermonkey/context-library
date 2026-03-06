"""Adapters module for content normalization from various sources."""

from context_library.adapters.base import BaseAdapter
from context_library.adapters.filesystem import FilesystemAdapter
from context_library.adapters.obsidian import ObsidianAdapter

# Try to import optional adapters
HAS_EMAIL = False

try:
    from context_library.adapters.email import EmailAdapter

    HAS_EMAIL = True
except ImportError:
    pass

__all__ = [
    "BaseAdapter",
    "FilesystemAdapter",
    "ObsidianAdapter",
]

if HAS_EMAIL:
    __all__.append("EmailAdapter")
