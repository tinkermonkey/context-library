"""Tests for the VCardAdapter."""

import pytest
from pathlib import Path

from context_library.adapters.vcard import VCardAdapter
from context_library.storage.models import Domain, PollStrategy, NormalizedContent, PeopleMetadata


class TestVCardAdapterInitialization:
    """Tests for VCardAdapter initialization."""

    def test_init_with_default_account_id(self, tmp_path):
        """__init__ uses default account_id when not provided."""
        adapter = VCardAdapter(vcf_directory=str(tmp_path))
        assert adapter._vcf_directory == tmp_path
        assert adapter._account_id == "default"

    def test_init_with_custom_account_id(self, tmp_path):
        """__init__ accepts and stores custom account_id."""
        adapter = VCardAdapter(vcf_directory=str(tmp_path), account_id="work")
        assert adapter._vcf_directory == tmp_path
        assert adapter._account_id == "work"

    def test_init_converts_string_to_path(self, tmp_path):
        """__init__ converts vcf_directory string to Path."""
        adapter = VCardAdapter(vcf_directory=str(tmp_path))
        assert isinstance(adapter._vcf_directory, Path)

    def test_init_import_error_without_vobject(self, monkeypatch, tmp_path):
        """__init__ raises ImportError if vobject is not installed."""
        monkeypatch.setattr(
            "context_library.adapters.vcard.HAS_VOBJECT",
            False
        )
        with pytest.raises(ImportError, match="vobject is required"):
            VCardAdapter(vcf_directory=str(tmp_path))


class TestVCardAdapterProperties:
    """Tests for VCardAdapter properties."""

    def test_adapter_id_format_default(self, tmp_path):
        """adapter_id has correct format: vcard:{account_id}."""
        adapter = VCardAdapter(vcf_directory=str(tmp_path))
        assert adapter.adapter_id == "vcard:default"

    def test_adapter_id_format_custom_account(self, tmp_path):
        """adapter_id uses custom account_id."""
        adapter = VCardAdapter(vcf_directory=str(tmp_path), account_id="work")
        assert adapter.adapter_id == "vcard:work"

    def test_adapter_id_deterministic(self, tmp_path):
        """adapter_id is deterministic for the same configuration."""
        adapter1 = VCardAdapter(vcf_directory=str(tmp_path), account_id="work")
        adapter2 = VCardAdapter(vcf_directory=str(tmp_path), account_id="work")
        assert adapter1.adapter_id == adapter2.adapter_id

    def test_different_accounts_different_ids(self, tmp_path):
        """Different account IDs produce different adapter_ids."""
        adapter1 = VCardAdapter(vcf_directory=str(tmp_path), account_id="work")
        adapter2 = VCardAdapter(vcf_directory=str(tmp_path), account_id="personal")
        assert adapter1.adapter_id != adapter2.adapter_id

    def test_domain_property(self, tmp_path):
        """domain property returns Domain.PEOPLE."""
        adapter = VCardAdapter(vcf_directory=str(tmp_path))
        assert adapter.domain == Domain.PEOPLE

    def test_poll_strategy_property(self, tmp_path):
        """poll_strategy property returns PollStrategy.PULL."""
        adapter = VCardAdapter(vcf_directory=str(tmp_path))
        assert adapter.poll_strategy == PollStrategy.PULL

    def test_normalizer_version_property(self, tmp_path):
        """normalizer_version property returns '1.0.0'."""
        adapter = VCardAdapter(vcf_directory=str(tmp_path))
        assert adapter.normalizer_version == "1.0.0"


class TestVCardAdapterFetch:
    """Tests for VCardAdapter.fetch() method."""

    def _create_vcard_file(self, directory: Path, filename: str, vcard_content: str) -> Path:
        """Helper to create a vCard file with given content."""
        file_path = directory / filename
        file_path.write_text(vcard_content, encoding="utf-8")
        return file_path

    def test_fetch_single_contact(self, tmp_path):
        """fetch() yields NormalizedContent for a single contact."""
        adapter = VCardAdapter(vcf_directory=str(tmp_path))

        vcard_content = """BEGIN:VCARD
VERSION:3.0
FN:John Doe
N:Doe;John;;;
EMAIL;TYPE=WORK:john@example.com
TEL;TYPE=WORK:555-1234
ORG:Acme Corp
TITLE:Engineer
NOTE:A great colleague
UID:john-doe-1
END:VCARD"""

        self._create_vcard_file(tmp_path, "contacts.vcf", vcard_content)

        results = list(adapter.fetch(""))
        assert len(results) == 1
        assert isinstance(results[0], NormalizedContent)
        assert results[0].source_id == "john-doe-1"
        assert "John Doe" in results[0].markdown

    def test_fetch_multiple_contacts_in_single_file(self, tmp_path):
        """fetch() yields multiple contacts from a single .vcf file."""
        adapter = VCardAdapter(vcf_directory=str(tmp_path))

        vcard_content = """BEGIN:VCARD
VERSION:3.0
FN:Alice Smith
N:Smith;Alice;;;
EMAIL:alice@example.com
UID:alice-smith-1
END:VCARD
BEGIN:VCARD
VERSION:3.0
FN:Bob Johnson
N:Johnson;Bob;;;
EMAIL:bob@example.com
UID:bob-johnson-1
END:VCARD"""

        self._create_vcard_file(tmp_path, "contacts.vcf", vcard_content)

        results = list(adapter.fetch(""))
        assert len(results) == 2
        assert results[0].source_id == "alice-smith-1"
        assert results[1].source_id == "bob-johnson-1"

    def test_fetch_multiple_files(self, tmp_path):
        """fetch() processes multiple .vcf files in sorted order."""
        adapter = VCardAdapter(vcf_directory=str(tmp_path))

        vcard1 = """BEGIN:VCARD
VERSION:3.0
FN:Carol White
EMAIL:carol@example.com
UID:carol-1
END:VCARD"""

        vcard2 = """BEGIN:VCARD
VERSION:3.0
FN:David Black
EMAIL:david@example.com
UID:david-1
END:VCARD"""

        self._create_vcard_file(tmp_path, "a_contacts.vcf", vcard1)
        self._create_vcard_file(tmp_path, "b_contacts.vcf", vcard2)

        results = list(adapter.fetch(""))
        assert len(results) == 2
        # Files are sorted by name, so 'a_contacts.vcf' comes first
        assert results[0].source_id == "carol-1"
        assert results[1].source_id == "david-1"

    def test_fetch_with_multi_email_contact(self, tmp_path):
        """fetch() extracts multiple email addresses."""
        adapter = VCardAdapter(vcf_directory=str(tmp_path))

        vcard_content = """BEGIN:VCARD
VERSION:3.0
FN:Jane Doe
EMAIL;TYPE=WORK:jane.work@example.com
EMAIL;TYPE=HOME:jane.personal@example.com
UID:jane-1
END:VCARD"""

        self._create_vcard_file(tmp_path, "contacts.vcf", vcard_content)

        results = list(adapter.fetch(""))
        metadata = PeopleMetadata.model_validate(results[0].structural_hints.extra_metadata)
        assert len(metadata.emails) == 2
        assert "jane.work@example.com" in metadata.emails
        assert "jane.personal@example.com" in metadata.emails

    def test_fetch_with_multi_phone_contact(self, tmp_path):
        """fetch() extracts multiple phone numbers."""
        adapter = VCardAdapter(vcf_directory=str(tmp_path))

        vcard_content = """BEGIN:VCARD
VERSION:3.0
FN:John Smith
TEL;TYPE=WORK:555-1111
TEL;TYPE=HOME:555-2222
TEL;TYPE=CELL:555-3333
UID:john-smith-1
END:VCARD"""

        self._create_vcard_file(tmp_path, "contacts.vcf", vcard_content)

        results = list(adapter.fetch(""))
        metadata = PeopleMetadata.model_validate(results[0].structural_hints.extra_metadata)
        assert len(metadata.phones) == 3
        assert "555-1111" in metadata.phones
        assert "555-2222" in metadata.phones
        assert "555-3333" in metadata.phones

    def test_fetch_with_missing_optional_fields(self, tmp_path):
        """fetch() handles contacts with missing optional fields."""
        adapter = VCardAdapter(vcf_directory=str(tmp_path))

        vcard_content = """BEGIN:VCARD
VERSION:3.0
FN:Minimal Contact
UID:minimal-1
END:VCARD"""

        self._create_vcard_file(tmp_path, "contacts.vcf", vcard_content)

        results = list(adapter.fetch(""))
        assert len(results) == 1
        metadata = PeopleMetadata.model_validate(results[0].structural_hints.extra_metadata)
        assert metadata.display_name == "Minimal Contact"
        assert metadata.given_name is None
        assert metadata.family_name is None
        assert metadata.organization is None
        assert metadata.job_title is None
        assert metadata.notes is None
        assert len(metadata.emails) == 0
        assert len(metadata.phones) == 0

    def test_fetch_with_structured_name(self, tmp_path):
        """fetch() extracts given and family names from N field."""
        adapter = VCardAdapter(vcf_directory=str(tmp_path))

        vcard_content = """BEGIN:VCARD
VERSION:3.0
FN:Alice Johnson
N:Johnson;Alice;;;
EMAIL:alice@example.com
UID:alice-johnson-1
END:VCARD"""

        self._create_vcard_file(tmp_path, "contacts.vcf", vcard_content)

        results = list(adapter.fetch(""))
        metadata = PeopleMetadata.model_validate(results[0].structural_hints.extra_metadata)
        assert metadata.given_name == "Alice"
        assert metadata.family_name == "Johnson"

    def test_fetch_uid_as_contact_id(self, tmp_path):
        """fetch() uses UID as source_id when present."""
        adapter = VCardAdapter(vcf_directory=str(tmp_path))

        vcard_content = """BEGIN:VCARD
VERSION:3.0
FN:John Doe
EMAIL:john@example.com
UID:unique-id-12345
END:VCARD"""

        self._create_vcard_file(tmp_path, "contacts.vcf", vcard_content)

        results = list(adapter.fetch(""))
        assert results[0].source_id == "unique-id-12345"

    def test_fetch_without_uid_uses_hash(self, tmp_path):
        """fetch() uses deterministic UUID when UID is missing."""
        adapter = VCardAdapter(vcf_directory=str(tmp_path))

        vcard_content = """BEGIN:VCARD
VERSION:3.0
FN:Jane Smith
EMAIL:jane@example.com
END:VCARD"""

        self._create_vcard_file(tmp_path, "contacts.vcf", vcard_content)

        results = list(adapter.fetch(""))
        source_id = results[0].source_id

        # Verify it's a UUID (36 chars: 8-4-4-4-12 with hyphens)
        assert len(source_id) == 36
        # UUID format check: 8 hex, dash, 4 hex, dash, 4 hex, dash, 4 hex, dash, 12 hex
        assert source_id.count("-") == 4

        # Verify it's deterministic by rescanning
        results_rescan = list(adapter.fetch(""))
        assert results_rescan[0].source_id == source_id

    def test_fetch_without_uid_without_email_still_stable(self, tmp_path):
        """fetch() generates stable ID even without email."""
        adapter = VCardAdapter(vcf_directory=str(tmp_path))

        vcard_content = """BEGIN:VCARD
VERSION:3.0
FN:Contact No Email
END:VCARD"""

        self._create_vcard_file(tmp_path, "contacts.vcf", vcard_content)

        results = list(adapter.fetch(""))
        source_id = results[0].source_id

        # Should be a valid UUID
        assert len(source_id) == 36
        assert source_id.count("-") == 4

    def test_fetch_directory_not_found(self):
        """fetch() raises FileNotFoundError if vcf_directory doesn't exist."""
        adapter = VCardAdapter(vcf_directory="/nonexistent/path")
        with pytest.raises(FileNotFoundError):
            list(adapter.fetch(""))

    def test_fetch_empty_directory(self, tmp_path):
        """fetch() yields no results from empty directory."""
        adapter = VCardAdapter(vcf_directory=str(tmp_path))
        results = list(adapter.fetch(""))
        assert len(results) == 0


class TestVCardAdapterMarkdownGeneration:
    """Tests for markdown generation in fetch()."""

    def _create_vcard_file(self, directory: Path, filename: str, vcard_content: str) -> Path:
        """Helper to create a vCard file with given content."""
        file_path = directory / filename
        file_path.write_text(vcard_content, encoding="utf-8")
        return file_path

    def test_markdown_includes_display_name(self, tmp_path):
        """Generated markdown includes contact display name."""
        adapter = VCardAdapter(vcf_directory=str(tmp_path))

        vcard_content = """BEGIN:VCARD
VERSION:3.0
FN:Alice Wonder
UID:alice-1
END:VCARD"""

        self._create_vcard_file(tmp_path, "contacts.vcf", vcard_content)

        results = list(adapter.fetch(""))
        assert "Alice Wonder" in results[0].markdown

    def test_markdown_includes_job_and_organization(self, tmp_path):
        """Generated markdown includes job title and organization."""
        adapter = VCardAdapter(vcf_directory=str(tmp_path))

        vcard_content = """BEGIN:VCARD
VERSION:3.0
FN:Bob Manager
TITLE:Director
ORG:Tech Company
UID:bob-1
END:VCARD"""

        self._create_vcard_file(tmp_path, "contacts.vcf", vcard_content)

        results = list(adapter.fetch(""))
        markdown = results[0].markdown
        assert "Director" in markdown
        assert "Tech Company" in markdown

    def test_markdown_includes_emails(self, tmp_path):
        """Generated markdown includes email addresses."""
        adapter = VCardAdapter(vcf_directory=str(tmp_path))

        vcard_content = """BEGIN:VCARD
VERSION:3.0
FN:Carol Email
EMAIL;TYPE=WORK:carol@work.com
EMAIL;TYPE=HOME:carol@personal.com
UID:carol-1
END:VCARD"""

        self._create_vcard_file(tmp_path, "contacts.vcf", vcard_content)

        results = list(adapter.fetch(""))
        markdown = results[0].markdown
        assert "carol@work.com" in markdown
        assert "carol@personal.com" in markdown

    def test_markdown_includes_phones(self, tmp_path):
        """Generated markdown includes phone numbers."""
        adapter = VCardAdapter(vcf_directory=str(tmp_path))

        vcard_content = """BEGIN:VCARD
VERSION:3.0
FN:David Phone
TEL;TYPE=WORK:555-1111
TEL;TYPE=HOME:555-2222
UID:david-1
END:VCARD"""

        self._create_vcard_file(tmp_path, "contacts.vcf", vcard_content)

        results = list(adapter.fetch(""))
        markdown = results[0].markdown
        assert "555-1111" in markdown
        assert "555-2222" in markdown

    def test_markdown_includes_notes(self, tmp_path):
        """Generated markdown includes notes when present."""
        adapter = VCardAdapter(vcf_directory=str(tmp_path))

        # Note: commas in vCard NOTE field must be escaped with backslash per RFC 6350
        vcard_content = """BEGIN:VCARD
VERSION:3.0
FN:Eve Notes
NOTE:Important contact\\, call before emailing
UID:eve-1
END:VCARD"""

        self._create_vcard_file(tmp_path, "contacts.vcf", vcard_content)

        results = list(adapter.fetch(""))
        assert "Important contact, call before emailing" in results[0].markdown

    def test_markdown_with_only_organization(self, tmp_path):
        """Generated markdown correctly formats when only organization is present."""
        adapter = VCardAdapter(vcf_directory=str(tmp_path))

        vcard_content = """BEGIN:VCARD
VERSION:3.0
FN:Frank Org
ORG:Big Corp
UID:frank-1
END:VCARD"""

        self._create_vcard_file(tmp_path, "contacts.vcf", vcard_content)

        results = list(adapter.fetch(""))
        markdown = results[0].markdown
        assert "Frank Org" in markdown
        assert "Big Corp" in markdown
        assert "works at" in markdown

    def test_markdown_with_only_job_title(self, tmp_path):
        """Generated markdown correctly formats when only job title is present."""
        adapter = VCardAdapter(vcf_directory=str(tmp_path))

        vcard_content = """BEGIN:VCARD
VERSION:3.0
FN:Grace Job
TITLE:Consultant
UID:grace-1
END:VCARD"""

        self._create_vcard_file(tmp_path, "contacts.vcf", vcard_content)

        results = list(adapter.fetch(""))
        markdown = results[0].markdown
        assert "Grace Job" in markdown
        assert "Consultant" in markdown
        assert "is a" in markdown


class TestVCardAdapterMetadata:
    """Tests for PeopleMetadata extraction."""

    def _create_vcard_file(self, directory: Path, filename: str, vcard_content: str) -> Path:
        """Helper to create a vCard file with given content."""
        file_path = directory / filename
        file_path.write_text(vcard_content, encoding="utf-8")
        return file_path

    def test_metadata_source_type_is_vcard(self, tmp_path):
        """PeopleMetadata has source_type='vcard'."""
        adapter = VCardAdapter(vcf_directory=str(tmp_path))

        vcard_content = """BEGIN:VCARD
VERSION:3.0
FN:Test Contact
UID:test-1
END:VCARD"""

        self._create_vcard_file(tmp_path, "contacts.vcf", vcard_content)

        results = list(adapter.fetch(""))
        metadata = PeopleMetadata.model_validate(results[0].structural_hints.extra_metadata)
        assert metadata.source_type == "vcard"

    def test_metadata_validates_correctly(self, tmp_path):
        """Generated PeopleMetadata passes model_validate."""
        adapter = VCardAdapter(vcf_directory=str(tmp_path))

        vcard_content = """BEGIN:VCARD
VERSION:3.0
FN:Full Name
N:Name;Full;;;
EMAIL;TYPE=WORK:full@work.com
TEL;TYPE=CELL:555-1234
ORG:Company Inc
TITLE:Manager
NOTE:Test notes
UID:test-id-123
END:VCARD"""

        self._create_vcard_file(tmp_path, "contacts.vcf", vcard_content)

        results = list(adapter.fetch(""))
        metadata_dict = results[0].structural_hints.extra_metadata

        # This should not raise if PeopleMetadata validation passes
        metadata = PeopleMetadata.model_validate(metadata_dict)
        assert metadata.contact_id == "test-id-123"
        assert metadata.display_name == "Full Name"
        assert metadata.given_name == "Full"
        assert metadata.family_name == "Name"
        assert len(metadata.emails) == 1
        assert len(metadata.phones) == 1
        assert metadata.organization == "Company Inc"
        assert metadata.job_title == "Manager"
        assert metadata.notes == "Test notes"
        assert metadata.source_type == "vcard"

    def test_deterministic_rescan_produces_same_source_id(self, tmp_path):
        """Re-scanning same vCard without UID produces identical source_id."""
        adapter = VCardAdapter(vcf_directory=str(tmp_path))

        vcard_content = """BEGIN:VCARD
VERSION:3.0
FN:Alice Smith
EMAIL:alice@example.com
END:VCARD"""

        self._create_vcard_file(tmp_path, "contacts.vcf", vcard_content)

        # First scan
        results1 = list(adapter.fetch(""))
        source_id_1 = results1[0].source_id

        # Second scan (simulating re-ingestion)
        results2 = list(adapter.fetch(""))
        source_id_2 = results2[0].source_id

        assert source_id_1 == source_id_2

    def test_name_change_preserves_contact_id(self, tmp_path):
        """Contact ID remains stable even if display name or email changes.

        This tests the core fix for identity instability: if a contact's name
        or first email changes, the ID should remain constant to preserve entity
        links and prevent duplicate person chunks.
        """
        adapter = VCardAdapter(vcf_directory=str(tmp_path))

        # Initial vCard
        vcard_content_v1 = """BEGIN:VCARD
VERSION:3.0
FN:John Smith
EMAIL:john@example.com
END:VCARD"""

        vcard_file = self._create_vcard_file(tmp_path, "contacts.vcf", vcard_content_v1)

        # First scan
        results1 = list(adapter.fetch(""))
        original_id = results1[0].source_id

        # Simulate contact name change (updating the vCard)
        vcard_content_v2 = """BEGIN:VCARD
VERSION:3.0
FN:John Q Smith
EMAIL:john@example.com
END:VCARD"""

        vcard_file.write_text(vcard_content_v2, encoding="utf-8")

        # Rescan after name change
        results2 = list(adapter.fetch(""))
        new_id = results2[0].source_id

        # ID should remain stable across name change
        assert original_id == new_id

    def test_email_change_preserves_contact_id(self, tmp_path):
        """Contact ID remains stable even if email changes.

        Tests that email changes don't invalidate the contact identity, preserving
        entity links from old email addresses.
        """
        adapter = VCardAdapter(vcf_directory=str(tmp_path))

        # Initial vCard with email
        vcard_content_v1 = """BEGIN:VCARD
VERSION:3.0
FN:Jane Doe
EMAIL:jane.old@example.com
END:VCARD"""

        vcard_file = self._create_vcard_file(tmp_path, "contacts.vcf", vcard_content_v1)

        # First scan
        results1 = list(adapter.fetch(""))
        original_id = results1[0].source_id

        # Simulate email change
        vcard_content_v2 = """BEGIN:VCARD
VERSION:3.0
FN:Jane Doe
EMAIL:jane.new@example.com
END:VCARD"""

        vcard_file.write_text(vcard_content_v2, encoding="utf-8")

        # Rescan after email change
        results2 = list(adapter.fetch(""))
        new_id = results2[0].source_id

        # ID should remain stable across email change
        assert original_id == new_id

    def test_no_collision_for_same_name_without_email(self, tmp_path):
        """Two contacts with same name and no email get different IDs.

        Tests the collision problem: previously, contacts with same name
        and no email would collide to the same identity.
        """
        adapter = VCardAdapter(vcf_directory=str(tmp_path))

        # Two contacts with same name, no email
        vcard_content = """BEGIN:VCARD
VERSION:3.0
FN:Common Name
END:VCARD
BEGIN:VCARD
VERSION:3.0
FN:Common Name
END:VCARD"""

        self._create_vcard_file(tmp_path, "contacts.vcf", vcard_content)

        results = list(adapter.fetch(""))
        assert len(results) == 2

        # IDs should be different despite having same name
        id1 = results[0].source_id
        id2 = results[1].source_id

        assert id1 != id2

    def test_separate_files_prevent_collision(self, tmp_path):
        """Same contact name in different files gets different IDs.

        Tests that using file path + index for ID generation prevents
        collisions between identical contact names in different files.
        """
        adapter = VCardAdapter(vcf_directory=str(tmp_path))

        vcard_content = """BEGIN:VCARD
VERSION:3.0
FN:Same Name
EMAIL:same@example.com
END:VCARD"""

        # Create same contact in two different files
        self._create_vcard_file(tmp_path, "file1.vcf", vcard_content)
        self._create_vcard_file(tmp_path, "file2.vcf", vcard_content)

        results = list(adapter.fetch(""))
        assert len(results) == 2

        # IDs should be different due to different file paths
        id1 = results[0].source_id
        id2 = results[1].source_id

        assert id1 != id2
