"""Domain registry for mapping Domain enum values to domain chunker instances.

Provides a lookup mechanism to instantiate and retrieve domain chunkers by Domain enum.
Uses lazy imports to avoid circular dependencies.
"""

from context_library.domains.base import BaseDomain
from context_library.storage.models import Domain

# Registry mapping Domain enum values to their corresponding domain chunker classes
_DOMAIN_REGISTRY = {
    Domain.MESSAGES: ("context_library.domains.messages", "MessagesDomain"),
    Domain.NOTES: ("context_library.domains.notes", "NotesDomain"),
}


def get_domain_chunker(domain: Domain) -> BaseDomain:
    """Get a domain chunker instance for the specified domain.

    Uses lazy imports to avoid circular dependencies at module load time.

    Args:
        domain: The Domain enum value to get a chunker for

    Returns:
        An instance of the corresponding domain chunker class

    Raises:
        ValueError: If the domain is not registered or not yet implemented
    """
    if domain not in _DOMAIN_REGISTRY:
        raise ValueError(f"Domain {domain} is not yet registered or implemented")

    module_name, class_name = _DOMAIN_REGISTRY[domain]
    module = __import__(module_name, fromlist=[class_name])
    chunker_class = getattr(module, class_name)
    return chunker_class()


def list_registered_domains() -> list[Domain]:
    """List all registered domains.

    Returns:
        A list of all Domain enum values that have registered chunkers
    """
    return list(_DOMAIN_REGISTRY.keys())
