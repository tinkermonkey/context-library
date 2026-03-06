"""Domain module: domain-specific chunking strategies for various content types.

Exports:
- Domain chunker classes (MessagesDomain, NotesDomain, etc.)
- Domain registry for looking up chunkers by Domain enum
"""

from context_library.domains.messages import MessagesDomain
from context_library.domains.notes import NotesDomain
from context_library.domains.registry import get_domain_chunker, list_registered_domains

__all__ = [
    "MessagesDomain",
    "NotesDomain",
    "get_domain_chunker",
    "list_registered_domains",
]
