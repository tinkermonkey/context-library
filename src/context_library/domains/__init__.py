"""Domain module: domain-specific chunking strategies for various content types.

Exports:
- Domain chunker classes (MessagesDomain, NotesDomain, EventsDomain, TasksDomain, etc.)
- Domain registry for looking up chunkers by Domain enum
"""

from context_library.domains.documents import DocumentsDomain
from context_library.domains.events import EventsDomain
from context_library.domains.health import HealthDomain
from context_library.domains.messages import MessagesDomain
from context_library.domains.notes import NotesDomain
from context_library.domains.people import PeopleDomain
from context_library.domains.tasks import TasksDomain
from context_library.domains.registry import get_domain_chunker, list_registered_domains

__all__ = [
    "MessagesDomain",
    "NotesDomain",
    "EventsDomain",
    "TasksDomain",
    "HealthDomain",
    "DocumentsDomain",
    "PeopleDomain",
    "get_domain_chunker",
    "list_registered_domains",
]
