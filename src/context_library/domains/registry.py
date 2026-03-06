"""Domain registry for mapping Domain enum values to domain chunker instances.

Provides a lookup mechanism to instantiate and retrieve domain chunkers by Domain enum.
Uses lazy imports to avoid circular dependencies.
"""

from context_library.storage.models import Domain


def get_domain_chunker(domain: Domain):
    """Get a domain chunker instance for the specified domain.

    Uses lazy imports to avoid circular dependencies at module load time.

    Args:
        domain: The Domain enum value to get a chunker for

    Returns:
        An instance of the corresponding domain chunker class

    Raises:
        ValueError: If the domain is not registered or not yet implemented
    """
    if domain == Domain.MESSAGES:
        from context_library.domains.messages import MessagesDomain
        return MessagesDomain()
    elif domain == Domain.NOTES:
        from context_library.domains.notes import NotesDomain
        return NotesDomain()
    else:
        raise ValueError(f"Domain {domain} is not yet registered or implemented")


def list_registered_domains() -> list[Domain]:
    """List all registered domains.

    Returns:
        A list of all Domain enum values that have registered chunkers
    """
    return [Domain.MESSAGES, Domain.NOTES]
