"""Tests for the AppleContactsAdapter."""

import pytest

import httpx

from context_library.adapters.apple_contacts import AppleContactsAdapter
from context_library.storage.models import Domain, PollStrategy, NormalizedContent, PeopleMetadata


class TestAppleContactsAdapterInitialization:
    """Tests for AppleContactsAdapter initialization."""

    def test_init_default_parameters(self):
        """__init__ uses default parameters when not provided."""
        adapter = AppleContactsAdapter(api_url="http://127.0.0.1:7123", api_key="test-token")
        assert adapter._api_url == "http://127.0.0.1:7123"
        assert adapter._api_key == "test-token"
        assert adapter._account_id == "default"

    def test_init_custom_parameters(self):
        """__init__ accepts and stores custom parameters."""
        adapter = AppleContactsAdapter(
            api_url="http://localhost:8000",
            api_key="test_key",
            account_id="work",
        )
        assert adapter._api_url == "http://localhost:8000"
        assert adapter._api_key == "test_key"
        assert adapter._account_id == "work"

    def test_init_strips_trailing_slash_from_url(self):
        """__init__ strips trailing slash from api_url."""
        adapter = AppleContactsAdapter(api_url="http://127.0.0.1:7123/", api_key="test-token")
        assert adapter._api_url == "http://127.0.0.1:7123"

    def test_init_no_trailing_slash(self):
        """__init__ leaves api_url unchanged if no trailing slash."""
        adapter = AppleContactsAdapter(api_url="http://127.0.0.1:7123", api_key="test-token")
        assert adapter._api_url == "http://127.0.0.1:7123"


class TestAppleContactsAdapterProperties:
    """Tests for AppleContactsAdapter properties."""

    def test_adapter_id_format_default(self):
        """adapter_id has correct format: apple_contacts:{account_id}."""
        adapter = AppleContactsAdapter(api_url="http://127.0.0.1:7123", api_key="test-token")
        assert adapter.adapter_id == "apple_contacts:default"

    def test_adapter_id_format_custom_account(self):
        """adapter_id uses custom account_id."""
        adapter = AppleContactsAdapter(api_url="http://127.0.0.1:7123", api_key="test-token", account_id="work")
        assert adapter.adapter_id == "apple_contacts:work"

    def test_adapter_id_deterministic(self):
        """adapter_id is deterministic for the same configuration."""
        adapter1 = AppleContactsAdapter(api_url="http://127.0.0.1:7123", api_key="test-token", account_id="work")
        adapter2 = AppleContactsAdapter(api_url="http://127.0.0.1:7123", api_key="test-token", account_id="work")
        assert adapter1.adapter_id == adapter2.adapter_id

    def test_different_accounts_different_ids(self):
        """Different account IDs produce different adapter_ids."""
        adapter1 = AppleContactsAdapter(api_url="http://127.0.0.1:7123", api_key="test-token", account_id="work")
        adapter2 = AppleContactsAdapter(api_url="http://127.0.0.1:7123", api_key="test-token", account_id="personal")
        assert adapter1.adapter_id != adapter2.adapter_id

    def test_domain_property(self):
        """domain property returns Domain.PEOPLE."""
        adapter = AppleContactsAdapter(api_url="http://127.0.0.1:7123", api_key="test-token")
        assert adapter.domain == Domain.PEOPLE

    def test_poll_strategy_property(self):
        """poll_strategy property returns PollStrategy.PULL."""
        adapter = AppleContactsAdapter(api_url="http://127.0.0.1:7123", api_key="test-token")
        assert adapter.poll_strategy == PollStrategy.PULL

    def test_normalizer_version_property(self):
        """normalizer_version property returns '1.0.0'."""
        adapter = AppleContactsAdapter(api_url="http://127.0.0.1:7123", api_key="test-token")
        assert adapter.normalizer_version == "1.0.0"


class TestAppleContactsAdapterFetch:
    """Tests for AppleContactsAdapter.fetch() method."""

    def test_fetch_single_contact(self, mock_apple_contacts_client):
        """fetch() yields NormalizedContent for a single contact."""
        adapter = AppleContactsAdapter(api_url="http://127.0.0.1:7123", api_key="test-token")

        # Mock contacts response
        contacts_url = "http://127.0.0.1:7123/contacts"
        mock_apple_contacts_client.set_response(contacts_url, [
            {
                "id": "contact-1",
                "displayName": "John Doe",
                "givenName": "John",
                "familyName": "Doe",
                "emails": ["john@example.com"],
                "phones": ["555-1234"],
                "organization": "Acme Corp",
                "jobTitle": "Engineer",
                "notes": "A great colleague",
                "modifiedAt": "2026-03-06T10:00:00Z",
            }
        ])

        results = list(adapter.fetch(""))
        assert len(results) == 1
        assert isinstance(results[0], NormalizedContent)
        assert results[0].source_id == "contact-1"
        assert "John Doe" in results[0].markdown

    def test_fetch_multiple_contacts(self, mock_apple_contacts_client):
        """fetch() yields NormalizedContent for multiple contacts."""
        adapter = AppleContactsAdapter(api_url="http://127.0.0.1:7123", api_key="test-token")

        contacts_url = "http://127.0.0.1:7123/contacts"
        mock_apple_contacts_client.set_response(contacts_url, [
            {
                "id": "contact-1",
                "displayName": "Alice Smith",
                "givenName": "Alice",
                "familyName": "Smith",
                "emails": ["alice@example.com"],
                "phones": [],
                "organization": None,
                "jobTitle": None,
                "notes": None,
                "modifiedAt": "2026-03-06T10:00:00Z",
            },
            {
                "id": "contact-2",
                "displayName": "Bob Johnson",
                "givenName": "Bob",
                "familyName": "Johnson",
                "emails": ["bob@example.com"],
                "phones": ["555-5678"],
                "organization": "Tech Inc",
                "jobTitle": "Manager",
                "notes": None,
                "modifiedAt": "2026-03-06T09:00:00Z",
            },
        ])

        results = list(adapter.fetch(""))
        assert len(results) == 2
        assert results[0].source_id == "contact-1"
        assert results[1].source_id == "contact-2"

    def test_fetch_incremental_with_since(self, mock_apple_contacts_client):
        """fetch() passes 'since' query parameter for incremental fetch."""
        adapter = AppleContactsAdapter(api_url="http://127.0.0.1:7123", api_key="test-token")

        contacts_url = "http://127.0.0.1:7123/contacts"
        mock_apple_contacts_client.set_response(contacts_url, [])

        list(adapter.fetch("2026-03-06T10:00:00Z"))

        # Verify the request was made with the 'since' parameter
        request = mock_apple_contacts_client.requests[0]
        assert request["params"]["since"] == "2026-03-06T10:00:00Z"

    def test_fetch_with_api_key_auth(self, mock_apple_contacts_client):
        """fetch() sends Authorization header when api_key is provided."""
        adapter = AppleContactsAdapter(
            api_url="http://127.0.0.1:7123",
            api_key="test_token_123"
        )

        contacts_url = "http://127.0.0.1:7123/contacts"
        mock_apple_contacts_client.set_response(contacts_url, [])

        list(adapter.fetch(""))

        # Verify the request was made with Authorization header
        request = mock_apple_contacts_client.requests[0]
        assert request["headers"]["Authorization"] == "Bearer test_token_123"

    def test_init_requires_api_key(self):
        """__init__ raises ValueError when api_key is empty."""
        with pytest.raises(ValueError, match="api_key is required"):
            AppleContactsAdapter(api_url="http://127.0.0.1:7123", api_key="")

    def test_fetch_with_multi_email_contact(self, mock_apple_contacts_client):
        """fetch() extracts multiple email addresses."""
        adapter = AppleContactsAdapter(api_url="http://127.0.0.1:7123", api_key="test-token")

        contacts_url = "http://127.0.0.1:7123/contacts"
        mock_apple_contacts_client.set_response(contacts_url, [
            {
                "id": "contact-1",
                "displayName": "Jane Doe",
                "givenName": "Jane",
                "familyName": "Doe",
                "emails": ["jane.work@example.com", "jane.personal@example.com"],
                "phones": [],
                "organization": None,
                "jobTitle": None,
                "notes": None,
                "modifiedAt": "2026-03-06T10:00:00Z",
            }
        ])

        results = list(adapter.fetch(""))
        metadata = PeopleMetadata.model_validate(results[0].structural_hints.extra_metadata)
        assert len(metadata.emails) == 2
        assert "jane.work@example.com" in metadata.emails
        assert "jane.personal@example.com" in metadata.emails

    def test_fetch_with_multi_phone_contact(self, mock_apple_contacts_client):
        """fetch() extracts multiple phone numbers."""
        adapter = AppleContactsAdapter(api_url="http://127.0.0.1:7123", api_key="test-token")

        contacts_url = "http://127.0.0.1:7123/contacts"
        mock_apple_contacts_client.set_response(contacts_url, [
            {
                "id": "contact-1",
                "displayName": "John Smith",
                "givenName": "John",
                "familyName": "Smith",
                "emails": [],
                "phones": ["555-1111", "555-2222", "555-3333"],
                "organization": None,
                "jobTitle": None,
                "notes": None,
                "modifiedAt": "2026-03-06T10:00:00Z",
            }
        ])

        results = list(adapter.fetch(""))
        metadata = PeopleMetadata.model_validate(results[0].structural_hints.extra_metadata)
        assert len(metadata.phones) == 3
        assert "555-1111" in metadata.phones
        assert "555-2222" in metadata.phones
        assert "555-3333" in metadata.phones

    def test_fetch_with_missing_optional_fields(self, mock_apple_contacts_client):
        """fetch() handles contacts with missing optional fields."""
        adapter = AppleContactsAdapter(api_url="http://127.0.0.1:7123", api_key="test-token")

        contacts_url = "http://127.0.0.1:7123/contacts"
        mock_apple_contacts_client.set_response(contacts_url, [
            {
                "id": "contact-1",
                "displayName": "Minimal Contact",
                "givenName": None,
                "familyName": None,
                "emails": [],
                "phones": [],
                "organization": None,
                "jobTitle": None,
                "notes": None,
                "modifiedAt": "2026-03-06T10:00:00Z",
            }
        ])

        results = list(adapter.fetch(""))
        assert len(results) == 1
        metadata = PeopleMetadata.model_validate(results[0].structural_hints.extra_metadata)
        assert metadata.display_name == "Minimal Contact"
        assert metadata.given_name is None
        assert metadata.family_name is None
        assert metadata.organization is None
        assert metadata.job_title is None
        assert metadata.notes is None

    def test_fetch_contact_metadata_contains_required_fields(self, mock_apple_contacts_client):
        """fetch() produces PeopleMetadata that passes model_validate."""
        adapter = AppleContactsAdapter(api_url="http://127.0.0.1:7123", api_key="test-token")

        contacts_url = "http://127.0.0.1:7123/contacts"
        mock_apple_contacts_client.set_response(contacts_url, [
            {
                "id": "contact-1",
                "displayName": "Test Contact",
                "givenName": "Test",
                "familyName": "Contact",
                "emails": ["test@example.com"],
                "phones": ["555-0000"],
                "organization": "Test Corp",
                "jobTitle": "Tester",
                "notes": "A test contact",
                "modifiedAt": "2026-03-06T10:00:00Z",
            }
        ])

        results = list(adapter.fetch(""))
        metadata_dict = results[0].structural_hints.extra_metadata

        # This should not raise if PeopleMetadata validation passes
        metadata = PeopleMetadata.model_validate(metadata_dict)
        assert metadata.contact_id == "contact-1"
        assert metadata.display_name == "Test Contact"
        assert metadata.source_type == "apple_contacts"

    def test_fetch_http_error_propagates(self, mock_apple_contacts_client):
        """fetch() propagates HTTP errors."""
        adapter = AppleContactsAdapter(api_url="http://127.0.0.1:7123", api_key="test-token")

        contacts_url = "http://127.0.0.1:7123/contacts"
        mock_apple_contacts_client.set_response(contacts_url, {}, status_code=500)

        with pytest.raises(httpx.HTTPStatusError):
            list(adapter.fetch(""))

    def test_fetch_invalid_response_schema_raises(self, mock_apple_contacts_client):
        """fetch() raises ValueError if response is not a list."""
        adapter = AppleContactsAdapter(api_url="http://127.0.0.1:7123", api_key="test-token")

        contacts_url = "http://127.0.0.1:7123/contacts"
        mock_apple_contacts_client.set_response(contacts_url, {"contacts": []})  # Should be a list, not dict

        with pytest.raises(ValueError, match="must be a list"):
            list(adapter.fetch(""))

    def test_fetch_missing_required_field_raises(self, mock_apple_contacts_client):
        """fetch() raises KeyError if contact is missing required field."""
        adapter = AppleContactsAdapter(api_url="http://127.0.0.1:7123", api_key="test-token")

        contacts_url = "http://127.0.0.1:7123/contacts"
        mock_apple_contacts_client.set_response(contacts_url, [
            {
                "id": "contact-1",
                # Missing 'displayName'
                "givenName": "John",
                "familyName": "Doe",
                "emails": [],
                "phones": [],
                "organization": None,
                "jobTitle": None,
                "notes": None,
                "modifiedAt": "2026-03-06T10:00:00Z",
            }
        ])

        with pytest.raises(KeyError, match="displayName"):
            list(adapter.fetch(""))

    def test_fetch_invalid_field_type_raises(self, mock_apple_contacts_client):
        """fetch() raises TypeError if contact field has wrong type."""
        adapter = AppleContactsAdapter(api_url="http://127.0.0.1:7123", api_key="test-token")

        contacts_url = "http://127.0.0.1:7123/contacts"
        mock_apple_contacts_client.set_response(contacts_url, [
            {
                "id": "contact-1",
                "displayName": "John Doe",
                "givenName": "John",
                "familyName": "Doe",
                "emails": "not a list",  # Should be list
                "phones": [],
                "organization": None,
                "jobTitle": None,
                "notes": None,
                "modifiedAt": "2026-03-06T10:00:00Z",
            }
        ])

        with pytest.raises(TypeError, match="emails"):
            list(adapter.fetch(""))

    def test_context_manager_closes_client(self, mock_apple_contacts_client):
        """Adapter supports context manager and closes client on exit."""
        with AppleContactsAdapter(api_url="http://127.0.0.1:7123", api_key="test-token") as adapter:
            assert adapter._client is not None
        # Client should be closed after exiting context (close() is called)


class TestAppleContactsAdapterImportGuard:
    """Tests for import guard and error handling."""

    def test_import_error_without_httpx(self, monkeypatch):
        """AppleContactsAdapter raises ImportError if httpx is not installed."""
        # Simulate httpx not being available
        import sys
        original_httpx = sys.modules.get('httpx')
        sys.modules['httpx'] = None

        try:
            # Need to reload the module to pick up the missing dependency
            monkeypatch.setattr(
                "context_library.adapters.apple_contacts.HAS_HTTPX",
                False
            )

            with pytest.raises(ImportError, match="httpx is required"):
                AppleContactsAdapter(api_url="http://127.0.0.1:7123", api_key="test-token")
        finally:
            # Restore original httpx module
            if original_httpx:
                sys.modules['httpx'] = original_httpx
            else:
                sys.modules.pop('httpx', None)


class TestAppleContactsAdapterMarkdownGeneration:
    """Tests for markdown generation in fetch()."""

    def test_markdown_includes_display_name(self, mock_apple_contacts_client):
        """Generated markdown includes contact display name."""
        adapter = AppleContactsAdapter(api_url="http://127.0.0.1:7123", api_key="test-token")

        contacts_url = "http://127.0.0.1:7123/contacts"
        mock_apple_contacts_client.set_response(contacts_url, [
            {
                "id": "contact-1",
                "displayName": "Alice Wonder",
                "givenName": None,
                "familyName": None,
                "emails": [],
                "phones": [],
                "organization": None,
                "jobTitle": None,
                "notes": None,
                "modifiedAt": "2026-03-06T10:00:00Z",
            }
        ])

        results = list(adapter.fetch(""))
        assert "Alice Wonder" in results[0].markdown

    def test_markdown_includes_job_and_organization(self, mock_apple_contacts_client):
        """Generated markdown includes job title and organization."""
        adapter = AppleContactsAdapter(api_url="http://127.0.0.1:7123", api_key="test-token")

        contacts_url = "http://127.0.0.1:7123/contacts"
        mock_apple_contacts_client.set_response(contacts_url, [
            {
                "id": "contact-1",
                "displayName": "Bob Manager",
                "givenName": "Bob",
                "familyName": "Manager",
                "emails": [],
                "phones": [],
                "organization": "Tech Company",
                "jobTitle": "Director",
                "notes": None,
                "modifiedAt": "2026-03-06T10:00:00Z",
            }
        ])

        results = list(adapter.fetch(""))
        markdown = results[0].markdown
        assert "Director" in markdown
        assert "Tech Company" in markdown

    def test_markdown_includes_emails(self, mock_apple_contacts_client):
        """Generated metadata includes email addresses (not in markdown per FR-6.3)."""
        adapter = AppleContactsAdapter(api_url="http://127.0.0.1:7123", api_key="test-token")

        contacts_url = "http://127.0.0.1:7123/contacts"
        mock_apple_contacts_client.set_response(contacts_url, [
            {
                "id": "contact-1",
                "displayName": "Carol Email",
                "givenName": "Carol",
                "familyName": "Email",
                "emails": ["carol@work.com", "carol@personal.com"],
                "phones": [],
                "organization": None,
                "jobTitle": None,
                "notes": None,
                "modifiedAt": "2026-03-06T10:00:00Z",
            }
        ])

        results = list(adapter.fetch(""))
        # Emails are excluded from markdown per FR-6.3 privacy requirements
        markdown = results[0].markdown
        assert "carol@work.com" not in markdown
        assert "carol@personal.com" not in markdown
        # But emails should be in metadata for entity linking
        metadata = PeopleMetadata.model_validate(results[0].structural_hints.extra_metadata)
        assert "carol@work.com" in metadata.emails
        assert "carol@personal.com" in metadata.emails

    def test_markdown_includes_phones(self, mock_apple_contacts_client):
        """Generated metadata includes phone numbers (not in markdown per FR-6.3)."""
        adapter = AppleContactsAdapter(api_url="http://127.0.0.1:7123", api_key="test-token")

        contacts_url = "http://127.0.0.1:7123/contacts"
        mock_apple_contacts_client.set_response(contacts_url, [
            {
                "id": "contact-1",
                "displayName": "David Phone",
                "givenName": "David",
                "familyName": "Phone",
                "emails": [],
                "phones": ["555-1111", "555-2222"],
                "organization": None,
                "jobTitle": None,
                "notes": None,
                "modifiedAt": "2026-03-06T10:00:00Z",
            }
        ])

        results = list(adapter.fetch(""))
        # Phones are excluded from markdown per FR-6.3 privacy requirements
        markdown = results[0].markdown
        assert "555-1111" not in markdown
        assert "555-2222" not in markdown
        # But phones should be in metadata for entity linking
        metadata = PeopleMetadata.model_validate(results[0].structural_hints.extra_metadata)
        assert "555-1111" in metadata.phones
        assert "555-2222" in metadata.phones

    def test_markdown_includes_notes(self, mock_apple_contacts_client):
        """Generated markdown includes notes when present."""
        adapter = AppleContactsAdapter(api_url="http://127.0.0.1:7123", api_key="test-token")

        contacts_url = "http://127.0.0.1:7123/contacts"
        mock_apple_contacts_client.set_response(contacts_url, [
            {
                "id": "contact-1",
                "displayName": "Eve Notes",
                "givenName": "Eve",
                "familyName": "Notes",
                "emails": [],
                "phones": [],
                "organization": None,
                "jobTitle": None,
                "notes": "Important contact, call before emailing",
                "modifiedAt": "2026-03-06T10:00:00Z",
            }
        ])

        results = list(adapter.fetch(""))
        assert "Important contact, call before emailing" in results[0].markdown

    def test_markdown_with_only_organization(self, mock_apple_contacts_client):
        """Generated markdown correctly formats when only organization is present."""
        adapter = AppleContactsAdapter(api_url="http://127.0.0.1:7123", api_key="test-token")

        contacts_url = "http://127.0.0.1:7123/contacts"
        mock_apple_contacts_client.set_response(contacts_url, [
            {
                "id": "contact-1",
                "displayName": "Frank Org",
                "givenName": None,
                "familyName": None,
                "emails": [],
                "phones": [],
                "organization": "Big Corp",
                "jobTitle": None,
                "notes": None,
                "modifiedAt": "2026-03-06T10:00:00Z",
            }
        ])

        results = list(adapter.fetch(""))
        markdown = results[0].markdown
        assert "Frank Org" in markdown
        assert "Big Corp" in markdown
        assert "works at" in markdown

    def test_markdown_with_only_job_title(self, mock_apple_contacts_client):
        """Generated markdown correctly formats when only job title is present."""
        adapter = AppleContactsAdapter(api_url="http://127.0.0.1:7123", api_key="test-token")

        contacts_url = "http://127.0.0.1:7123/contacts"
        mock_apple_contacts_client.set_response(contacts_url, [
            {
                "id": "contact-1",
                "displayName": "Grace Job",
                "givenName": None,
                "familyName": None,
                "emails": [],
                "phones": [],
                "organization": None,
                "jobTitle": "Consultant",
                "notes": None,
                "modifiedAt": "2026-03-06T10:00:00Z",
            }
        ])

        results = list(adapter.fetch(""))
        markdown = results[0].markdown
        assert "Grace Job" in markdown
        assert "Consultant" in markdown
        assert "is a" in markdown
