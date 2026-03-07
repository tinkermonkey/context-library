"""Tests for the domain registry module."""

import pytest

from context_library.domains.base import BaseDomain
from context_library.domains.messages import MessagesDomain
from context_library.domains.notes import NotesDomain
from context_library.domains.registry import (
    get_domain_chunker,
    list_registered_domains,
)
from context_library.storage.models import Domain


class TestGetDomainChunker:
    """Tests for get_domain_chunker function."""

    def test_get_messages_chunker(self):
        """get_domain_chunker returns MessagesDomain for MESSAGES domain."""
        chunker = get_domain_chunker(Domain.MESSAGES)

        assert isinstance(chunker, MessagesDomain)
        assert isinstance(chunker, BaseDomain)

    def test_get_notes_chunker(self):
        """get_domain_chunker returns NotesDomain for NOTES domain."""
        chunker = get_domain_chunker(Domain.NOTES)

        assert isinstance(chunker, NotesDomain)
        assert isinstance(chunker, BaseDomain)

    def test_unregistered_domain_raises_error(self):
        """get_domain_chunker raises ValueError for unregistered domains."""
        with pytest.raises(ValueError, match="Domain .* is not yet registered or implemented"):
            get_domain_chunker(Domain.EVENTS)

    def test_unregistered_domain_error_message(self):
        """ValueError message includes the unregistered domain name."""
        with pytest.raises(ValueError) as exc_info:
            get_domain_chunker(Domain.TASKS)

        assert "Domain.TASKS" in str(exc_info.value) or "tasks" in str(exc_info.value)

    def test_each_call_returns_new_instance(self):
        """get_domain_chunker returns a new instance on each call."""
        chunker1 = get_domain_chunker(Domain.MESSAGES)
        chunker2 = get_domain_chunker(Domain.MESSAGES)

        assert chunker1 is not chunker2
        assert isinstance(chunker1, MessagesDomain)
        assert isinstance(chunker2, MessagesDomain)

    def test_return_type_annotation(self):
        """get_domain_chunker has proper return type annotation."""
        chunker = get_domain_chunker(Domain.NOTES)

        # Verify return type is BaseDomain or subclass
        assert isinstance(chunker, BaseDomain)


class TestListRegisteredDomains:
    """Tests for list_registered_domains function."""

    def test_returns_list(self):
        """list_registered_domains returns a list."""
        domains = list_registered_domains()

        assert isinstance(domains, list)

    def test_contains_messages_domain(self):
        """list_registered_domains includes Domain.MESSAGES."""
        domains = list_registered_domains()

        assert Domain.MESSAGES in domains

    def test_contains_notes_domain(self):
        """list_registered_domains includes Domain.NOTES."""
        domains = list_registered_domains()

        assert Domain.NOTES in domains

    def test_does_not_contain_events_domain(self):
        """list_registered_domains does not include unregistered Domain.EVENTS."""
        domains = list_registered_domains()

        assert Domain.EVENTS not in domains

    def test_does_not_contain_tasks_domain(self):
        """list_registered_domains does not include unregistered Domain.TASKS."""
        domains = list_registered_domains()

        assert Domain.TASKS not in domains

    def test_expected_count(self):
        """list_registered_domains returns exactly two registered domains."""
        domains = list_registered_domains()

        assert len(domains) == 2

    def test_all_returned_domains_are_enum_values(self):
        """All values returned are valid Domain enum members."""
        domains = list_registered_domains()

        for domain in domains:
            assert isinstance(domain, Domain)

    def test_get_chunker_works_for_all_listed_domains(self):
        """get_domain_chunker works for all domains returned by list_registered_domains."""
        domains = list_registered_domains()

        for domain in domains:
            chunker = get_domain_chunker(domain)
            assert isinstance(chunker, BaseDomain)


class TestRegistryConsistency:
    """Tests for consistency between registry functions."""

    def test_registry_is_synchronized(self):
        """get_domain_chunker and list_registered_domains stay in sync.

        This ensures there are no hidden domains in get_domain_chunker that aren't
        listed in list_registered_domains, and vice versa.
        """
        registered_domains = list_registered_domains()

        # Verify each registered domain can be instantiated
        for domain in registered_domains:
            chunker = get_domain_chunker(domain)
            assert isinstance(chunker, BaseDomain)

        # Verify all main Domain enum values are either registered or explicitly unsupported
        for domain in Domain:
            if domain in registered_domains:
                # Should work
                chunker = get_domain_chunker(domain)
                assert isinstance(chunker, BaseDomain)
            else:
                # Should raise ValueError
                with pytest.raises(ValueError):
                    get_domain_chunker(domain)
