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

    def test_get_events_chunker(self):
        """get_domain_chunker returns EventsDomain for EVENTS domain."""
        chunker = get_domain_chunker(Domain.EVENTS)

        assert isinstance(chunker, BaseDomain)
        assert chunker.__class__.__name__ == "EventsDomain"

    def test_get_tasks_chunker(self):
        """get_domain_chunker returns TasksDomain for TASKS domain."""
        chunker = get_domain_chunker(Domain.TASKS)

        assert isinstance(chunker, BaseDomain)
        assert chunker.__class__.__name__ == "TasksDomain"

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

    def test_contains_events_domain(self):
        """list_registered_domains includes Domain.EVENTS."""
        domains = list_registered_domains()

        assert Domain.EVENTS in domains

    def test_contains_tasks_domain(self):
        """list_registered_domains includes Domain.TASKS."""
        domains = list_registered_domains()

        assert Domain.TASKS in domains

    def test_contains_health_domain(self):
        """list_registered_domains includes Domain.HEALTH."""
        domains = list_registered_domains()

        assert Domain.HEALTH in domains

    def test_expected_count(self):
        """list_registered_domains returns exactly five registered domains."""
        domains = list_registered_domains()

        assert len(domains) == 5

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
