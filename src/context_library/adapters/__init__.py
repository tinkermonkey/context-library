"""Adapters module for content normalization from various sources."""

from context_library.adapters.base import BaseAdapter
from context_library.adapters.filesystem import FilesystemAdapter
from context_library.adapters.obsidian import ObsidianAdapter

__all__ = [
    "BaseAdapter",
    "FilesystemAdapter",
    "ObsidianAdapter",
]
