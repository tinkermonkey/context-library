"""Tests for the VCardAdapter."""

import logging
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


class TestVCardAdapterContextManager:
    """Tests for VCardAdapter context manager protocol."""

    def test_context_manager_enter_returns_self(self, tmp_path):
        """__enter__ returns the adapter instance for use in with statement."""
        adapter = VCardAdapter(vcf_directory=str(tmp_path))
        result = adapter.__enter__()
        assert result is adapter

    def test_context_manager_with_statement(self, tmp_path):
        """Adapter can be used with 'with' statement."""
        with VCardAdapter(vcf_directory=str(tmp_path)) as adapter:
            assert isinstance(adapter, VCardAdapter)
            assert adapter._account_id == "default"

    def test_context_manager_exit_returns_false(self, tmp_path):
        """__exit__ returns False to allow exception propagation."""
        adapter = VCardAdapter(vcf_directory=str(tmp_path))
        result = adapter.__exit__(None, None, None)
        assert result is False

    def test_context_manager_exit_does_not_suppress_exceptions(self, tmp_path):
        """__exit__ returning False allows exceptions to propagate."""
        with pytest.raises(ValueError):
            with VCardAdapter(vcf_directory=str(tmp_path)):
                raise ValueError("Test exception")

    def test_context_manager_del_no_error(self, tmp_path):
        """__del__ can be called without error."""
        adapter = VCardAdapter(vcf_directory=str(tmp_path))
        # This should not raise any exception
        adapter.__del__()


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

    def test_fetch_empty_uid_falls_back_to_hash(self, tmp_path):
        """fetch() falls back to SHA-256 hash when UID is empty string.

        Per the fix for empty UID acceptance, an empty string UID should NOT be used
        as contact_id. Instead, the adapter falls back to the deterministic SHA-256
        hash of FN + first EMAIL, preventing collisions with other empty-UID contacts.
        """
        adapter = VCardAdapter(vcf_directory=str(tmp_path))

        vcard_content = """BEGIN:VCARD
VERSION:3.0
FN:Jane Smith
EMAIL:jane@example.com
UID:
END:VCARD"""

        self._create_vcard_file(tmp_path, "contacts.vcf", vcard_content)

        results = list(adapter.fetch(""))
        source_id = results[0].source_id

        # Should be a SHA-256 hash (64 hex characters), NOT the empty string
        assert len(source_id) == 64
        assert all(c in "0123456789abcdef" for c in source_id)
        assert source_id != ""

    def test_fetch_without_uid_uses_hash(self, tmp_path):
        """fetch() uses deterministic SHA-256 hash of FN + first EMAIL when UID is missing."""
        adapter = VCardAdapter(vcf_directory=str(tmp_path))

        vcard_content = """BEGIN:VCARD
VERSION:3.0
FN:Jane Smith
EMAIL:jane@example.com
END:VCARD"""

        self._create_vcard_file(tmp_path, "contacts.vcf", vcard_content)

        results = list(adapter.fetch(""))
        source_id = results[0].source_id

        # Verify it's a SHA-256 hash (64 hex characters)
        assert len(source_id) == 64
        # SHA-256 hex format check: all hexadecimal characters
        assert all(c in "0123456789abcdef" for c in source_id)

        # Verify it's deterministic by rescanning
        results_rescan = list(adapter.fetch(""))
        assert results_rescan[0].source_id == source_id

    def test_fetch_without_uid_without_email_still_stable(self, tmp_path):
        """fetch() generates stable SHA-256 hash ID even without email (hashing FN only)."""
        adapter = VCardAdapter(vcf_directory=str(tmp_path))

        vcard_content = """BEGIN:VCARD
VERSION:3.0
FN:Contact No Email
END:VCARD"""

        self._create_vcard_file(tmp_path, "contacts.vcf", vcard_content)

        results = list(adapter.fetch(""))
        source_id = results[0].source_id

        # Should be a valid SHA-256 hash (64 hex characters)
        assert len(source_id) == 64
        assert all(c in "0123456789abcdef" for c in source_id)

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

    def test_name_change_changes_contact_id(self, tmp_path):
        """Contact ID changes when display name changes (spec-compliant FN + EMAIL hash).

        Per spec FR-5.4, the fallback contact ID is a deterministic hash of
        FN + first EMAIL. When the name changes, the hash changes, reflecting
        that this is semantically a different person identity per RFC 6350.
        Upstream systems should handle entity resolution via UID or other means.
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

        # ID should change because the hash of FN changed
        assert original_id != new_id

    def test_email_change_changes_contact_id(self, tmp_path):
        """Contact ID changes when first email changes (spec-compliant FN + EMAIL hash).

        Per spec FR-5.4, the fallback contact ID is a deterministic hash of
        FN + first EMAIL. When the first email address changes, the hash
        changes, reflecting a change in the contact's identity. Upstream
        systems should handle entity resolution via UID or other means.
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

        # ID should change because the hash of first EMAIL changed
        assert original_id != new_id

    def test_collision_for_same_name_without_email_skips_duplicate(self, tmp_path, caplog):
        """Two contacts with identical name and no email: first retained, second skipped.

        Per spec FR-5.4, the fallback ID is hash(FN + first_email). When two contacts
        have identical FN and no email, they hash to the same ID. To prevent silent data
        loss, the second contact is skipped and a collision warning is logged. Upstream
        systems must use explicit UIDs to distinguish between contacts with identical
        names and emails.
        """
        adapter = VCardAdapter(vcf_directory=str(tmp_path))

        # Two contacts with same name, no email (in same file to test within-file collision)
        vcard_content = """BEGIN:VCARD
VERSION:3.0
FN:Common Name
END:VCARD
BEGIN:VCARD
VERSION:3.0
FN:Common Name
END:VCARD"""

        self._create_vcard_file(tmp_path, "contacts.vcf", vcard_content)

        with caplog.at_level(logging.WARNING):
            results = list(adapter.fetch(""))

        # Only first contact retained; second skipped to prevent overwrite
        assert len(results) == 1
        assert any("collision" in record.message.lower() for record in caplog.records)

    def test_identical_contacts_collision_skips_second(self, tmp_path):
        """Identical contacts in different files: first is retained, second is skipped to prevent overwrite.

        When two identical contacts (same FN and EMAIL) are found, the adapter detects
        the collision, logs a warning, and skips the second contact to prevent silent
        data loss. Upstream systems should use explicit UIDs to distinguish logically
        separate contacts and avoid this scenario.
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
        # Only first contact is retained; second is skipped to prevent overwrite
        assert len(results) == 1

        # Single contact retained from file1
        assert "Same Name" in results[0].markdown

    def test_collision_detection_logs_warning_and_skips_second(self, tmp_path, caplog):
        """fetch() detects collision and skips second contact to prevent silent overwrite.

        When two distinct contacts produce the same source_id (due to identical FN
        and first EMAIL), a warning is logged and the second contact is skipped
        to prevent data loss from the first contact being overwritten.
        """
        adapter = VCardAdapter(vcf_directory=str(tmp_path))

        # Two identical contacts in different files
        vcard_content = """BEGIN:VCARD
VERSION:3.0
FN:Alice Smith
EMAIL:alice@example.com
END:VCARD"""

        self._create_vcard_file(tmp_path, "file1.vcf", vcard_content)
        self._create_vcard_file(tmp_path, "file2.vcf", vcard_content)

        # Fetch and capture logs
        with caplog.at_level(logging.WARNING):
            results = list(adapter.fetch(""))

        # Only first contact should be yielded; second is skipped to prevent overwrite
        assert len(results) == 1
        assert any("collision" in record.message.lower() for record in caplog.records)
        assert any("Alice Smith" in record.message for record in caplog.records)
        assert any("Skipping this contact to prevent data loss" in record.message for record in caplog.records)


class TestVCardAdapterPerContactErrorIsolation:
    """Tests for per-contact error isolation when parsing vCard files."""

    def _create_vcard_file(self, directory: Path, filename: str, vcard_content: str) -> Path:
        """Helper to create a vCard file with given content."""
        file_path = directory / filename
        file_path.write_text(vcard_content, encoding="utf-8")
        return file_path

    def test_malformed_contact_skipped_valid_contacts_processed(self, tmp_path, caplog):
        """Per-contact error isolation: valid contacts before and after a malformed one are still processed."""
        adapter = VCardAdapter(vcf_directory=str(tmp_path))

        # File with valid contact, then malformed contact (missing FN), then valid contact
        vcard_content = """BEGIN:VCARD
VERSION:3.0
FN:Good Contact 1
EMAIL:good1@example.com
UID:good-1
END:VCARD
BEGIN:VCARD
VERSION:3.0
N:BadContact;NoFN;;;
EMAIL:badfn@example.com
UID:bad-fn
END:VCARD
BEGIN:VCARD
VERSION:3.0
FN:Good Contact 2
EMAIL:good2@example.com
UID:good-2
END:VCARD"""

        self._create_vcard_file(tmp_path, "mixed.vcf", vcard_content)

        with caplog.at_level(logging.ERROR):
            results = list(adapter.fetch(""))

        # Should have processed 2 valid contacts (skipped the malformed one)
        assert len(results) == 2
        assert results[0].source_id == "good-1"
        assert results[1].source_id == "good-2"

        # Error should have been logged
        assert any("Error processing contact" in record.message for record in caplog.records)

    def test_malformed_contact_does_not_stop_file_processing(self, tmp_path, caplog):
        """Per-contact error isolation: malformed contact in one file doesn't affect processing of next file."""
        adapter = VCardAdapter(vcf_directory=str(tmp_path))

        # First file with a valid contact
        vcard1 = """BEGIN:VCARD
VERSION:3.0
FN:From File 1
EMAIL:file1@example.com
UID:file1-contact
END:VCARD"""

        # Second file starts with malformed contact (missing FN) then valid contact
        vcard2 = """BEGIN:VCARD
VERSION:3.0
N:BadContact;NoFN;;;
EMAIL:bad@example.com
UID:bad-contact
END:VCARD
BEGIN:VCARD
VERSION:3.0
FN:From File 2
EMAIL:file2@example.com
UID:file2-contact
END:VCARD"""

        self._create_vcard_file(tmp_path, "a_file1.vcf", vcard1)
        self._create_vcard_file(tmp_path, "b_file2.vcf", vcard2)

        with caplog.at_level(logging.ERROR):
            results = list(adapter.fetch(""))

        # Should have processed contacts from both files (skipped malformed one in file2)
        assert len(results) == 2
        assert results[0].source_id == "file1-contact"
        assert results[1].source_id == "file2-contact"

        # Error should have been logged for the malformed contact
        assert any("Error processing contact" in record.message for record in caplog.records)


class TestVCardAdapterEncodingFallback:
    """Tests for encoding detection and fallback (UTF-8 with latin-1 fallback)."""

    def _create_vcard_file_with_encoding(self, directory: Path, filename: str, vcard_content: str, encoding: str) -> Path:
        """Helper to create a vCard file with a specific encoding."""
        file_path = directory / filename
        file_path.write_bytes(vcard_content.encode(encoding))
        return file_path

    def test_utf8_file_processes_normally(self, tmp_path):
        """UTF-8 encoded vCard file processes without warnings."""
        adapter = VCardAdapter(vcf_directory=str(tmp_path))

        vcard_content = """BEGIN:VCARD
VERSION:3.0
FN:UTF-8 Contact
EMAIL:utf8@example.com
UID:utf8-contact
END:VCARD"""

        self._create_vcard_file_with_encoding(tmp_path, "utf8.vcf", vcard_content, "utf-8")

        results = list(adapter.fetch(""))
        assert len(results) == 1
        assert results[0].source_id == "utf8-contact"

    def test_latin1_file_logs_encoding_warning(self, tmp_path, caplog):
        """Latin-1 encoded vCard triggers encoding warning and falls back to latin-1."""
        adapter = VCardAdapter(vcf_directory=str(tmp_path))

        # Latin-1 specific character (café with accented e)
        vcard_content = """BEGIN:VCARD
VERSION:3.0
FN:Jos\xe9 Garc\xeda
EMAIL:jose@example.com
UID:jose-contact
END:VCARD"""

        self._create_vcard_file_with_encoding(tmp_path, "latin1.vcf", vcard_content, "latin-1")

        with caplog.at_level(logging.WARNING):
            results = list(adapter.fetch(""))

        # Should have processed the contact
        assert len(results) == 1
        assert results[0].source_id == "jose-contact"

        # Should have logged encoding warning
        assert any("not valid UTF-8" in record.message for record in caplog.records)
        assert any("latin-1" in record.message for record in caplog.records)

    def test_unreadable_file_skipped_with_error_log(self, tmp_path, caplog):
        """File with unparseable vCard syntax triggers error log and file is skipped."""
        adapter = VCardAdapter(vcf_directory=str(tmp_path))

        # Create a file with content that is decodable but invalid vCard syntax
        # (latin-1 can decode any byte sequence, so we just create invalid vCard structure)
        bad_file = tmp_path / "bad_syntax.vcf"
        bad_file.write_bytes(b"NOT A VALID VCARD\xFF\xFE STRUCTURE")

        with caplog.at_level(logging.ERROR):
            results = list(adapter.fetch(""))

        # Should have skipped the file and logged parse error
        assert len(results) == 0
        # The parse error will be logged (from vobject parser)
        assert any("Parse error" in record.message for record in caplog.records)


class TestVCardAdapterNonStringValueWarnings:
    """Tests for explicit logging of non-string email/phone values."""

    def _create_vcard_file(self, directory: Path, filename: str, vcard_content: str) -> Path:
        """Helper to create a vCard file with given content."""
        file_path = directory / filename
        file_path.write_text(vcard_content, encoding="utf-8")
        return file_path

    def test_non_string_email_logged_and_skipped(self, tmp_path, caplog, monkeypatch):
        """Non-string email values trigger warning log and are skipped (not silently filtered)."""
        adapter = VCardAdapter(vcf_directory=str(tmp_path))

        vcard_content = """BEGIN:VCARD
VERSION:3.0
FN:Test Contact
EMAIL:string@example.com
UID:test-1
END:VCARD"""

        self._create_vcard_file(tmp_path, "contacts.vcf", vcard_content)

        # Mock vobject to return a non-string email value
        import vobject

        original_read = vobject.readComponents

        def mock_read_components(text):
            for vcard_obj in original_read(text):
                # Inject a non-string email value
                if hasattr(vcard_obj, "email"):
                    # Store original, we'll patch it

                    # Create a mock email entry with integer value (simulating malformed data)
                    class MockEmailComponent:
                        def __init__(self):
                            self.value = 12345  # Non-string value

                    # Replace email in contents
                    email_list = list(vcard_obj.contents.get("email", []))
                    email_list.append(MockEmailComponent())
                    vcard_obj.contents["email"] = email_list

                yield vcard_obj

        monkeypatch.setattr("vobject.readComponents", mock_read_components)

        with caplog.at_level(logging.WARNING):
            results = list(adapter.fetch(""))

        # Should still process the contact
        assert len(results) == 1

        # Should have logged warning about non-string email
        assert any("Skipping non-string email value" in record.message for record in caplog.records)
        assert any("Test Contact" in record.message for record in caplog.records)

    def test_non_string_phone_logged_and_skipped(self, tmp_path, caplog, monkeypatch):
        """Non-string phone values trigger warning log and are skipped (not silently filtered)."""
        adapter = VCardAdapter(vcf_directory=str(tmp_path))

        vcard_content = """BEGIN:VCARD
VERSION:3.0
FN:Phone Test Contact
TEL:555-1234
UID:phone-test-1
END:VCARD"""

        self._create_vcard_file(tmp_path, "contacts.vcf", vcard_content)

        # Mock vobject to return a non-string phone value
        import vobject

        original_read = vobject.readComponents

        def mock_read_components(text):
            for vcard_obj in original_read(text):
                # Inject a non-string phone value
                if hasattr(vcard_obj, "tel"):
                    # Create a mock tel entry with list value (simulating malformed data)
                    class MockPhoneComponent:
                        def __init__(self):
                            self.value = ["555-1234", "555-5678"]  # Non-string value

                    # Replace tel in contents
                    tel_list = list(vcard_obj.contents.get("tel", []))
                    tel_list.append(MockPhoneComponent())
                    vcard_obj.contents["tel"] = tel_list

                yield vcard_obj

        monkeypatch.setattr("vobject.readComponents", mock_read_components)

        with caplog.at_level(logging.WARNING):
            results = list(adapter.fetch(""))

        # Should still process the contact
        assert len(results) == 1

        # Should have logged warning about non-string phone
        assert any("Skipping non-string phone value" in record.message for record in caplog.records)
        assert any("Phone Test Contact" in record.message for record in caplog.records)
