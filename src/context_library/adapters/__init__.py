"""Adapters module for content normalization from various sources."""

from context_library.adapters.base import BaseAdapter
from context_library.adapters.filesystem import FilesystemAdapter

# Try to import optional adapters
HAS_EMAIL = False
HAS_OBSIDIAN = False

try:
    from context_library.adapters.email import EmailAdapter

    HAS_EMAIL = True
except ImportError:
    pass

try:
    from context_library.adapters.obsidian import ObsidianAdapter

    HAS_OBSIDIAN = True
except ImportError:
    pass

__all__ = ["BaseAdapter", "FilesystemAdapter"]

if HAS_EMAIL:
    __all__.append("EmailAdapter")
if HAS_OBSIDIAN:
    __all__.append("ObsidianAdapter")
