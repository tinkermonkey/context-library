"""Tests for identifier normalization functions."""

import pytest

from context_library.core.identifier_normalizer import normalize_email, normalize_phone


class TestNormalizeEmail:
    """Test email normalization."""

    def test_lowercase_conversion(self):
        """Convert uppercase emails to lowercase."""
        assert normalize_email("ALICE@EXAMPLE.COM") == "alice@example.com"
        assert normalize_email("Alice@Example.COM") == "alice@example.com"

    def test_whitespace_stripping(self):
        """Strip leading and trailing whitespace."""
        assert normalize_email("  alice@example.com  ") == "alice@example.com"
        assert normalize_email("\talice@example.com\n") == "alice@example.com"

    def test_combined_normalization(self):
        """Apply multiple normalizations."""
        assert normalize_email("  ALICE@EXAMPLE.COM  ") == "alice@example.com"
        assert normalize_email("\n  Bob@Company.CO.UK  \t") == "bob@company.co.uk"

    def test_empty_strings(self):
        """Handle empty and None inputs."""
        assert normalize_email("") == ""
        assert normalize_email(None) == ""

    def test_email_with_plus_addressing(self):
        """Handle plus-addressed emails."""
        assert normalize_email("alice+tag@example.com") == "alice+tag@example.com"
        assert normalize_email("ALICE+TAG@EXAMPLE.COM") == "alice+tag@example.com"

    def test_email_with_subdomain(self):
        """Handle emails with subdomains."""
        assert normalize_email("alice@mail.example.co.uk") == "alice@mail.example.co.uk"
        assert normalize_email("ALICE@MAIL.EXAMPLE.CO.UK") == "alice@mail.example.co.uk"

    def test_email_single_word_domain(self):
        """Handle emails with single-word domains."""
        assert normalize_email("alice@localhost") == "alice@localhost"
        assert normalize_email("ALICE@LOCALHOST") == "alice@localhost"


class TestNormalizePhone:
    """Test phone number normalization."""

    def test_remove_parentheses_and_hyphens(self):
        """Remove formatting characters."""
        assert normalize_phone("(555) 123-4567") == "5551234567"
        assert normalize_phone("555-123-4567") == "5551234567"
        assert normalize_phone("(555)123-4567") == "5551234567"

    def test_preserve_leading_plus(self):
        """Preserve international '+' prefix."""
        assert normalize_phone("+1 (555) 123-4567") == "+15551234567"
        assert normalize_phone("+1-555-123-4567") == "+15551234567"
        assert normalize_phone("+44 20 7946 0958") == "+442079460958"

    def test_various_phone_formats(self):
        """Handle various international phone formats."""
        assert normalize_phone("+33 1 42 34 56 78") == "+33142345678"  # French
        assert normalize_phone("+49 30 12345678") == "+493012345678"  # German
        assert normalize_phone("+81-3-1234-5678") == "+81312345678"  # Japanese

    def test_remove_whitespace(self):
        """Remove all whitespace."""
        assert normalize_phone("555 123 4567") == "5551234567"
        assert normalize_phone("  555-123-4567  ") == "5551234567"
        assert normalize_phone("\t555.123.4567\n") == "5551234567"

    def test_remove_extensions(self):
        """Handle extensions (ext, x, etc)."""
        # Note: extensions with text are stripped; only numeric digits remain
        assert normalize_phone("555-123-4567 ext. 123") == "5551234567123"
        assert normalize_phone("555-123-4567x123") == "5551234567123"

    def test_no_digits_returns_empty(self):
        """Return empty string if no digits found."""
        assert normalize_phone("") == ""
        assert normalize_phone(None) == ""
        assert normalize_phone("   ") == ""
        assert normalize_phone("abc") == ""
        assert normalize_phone("()--") == ""

    def test_only_plus_no_digits_returns_empty(self):
        """Return empty string if only '+' and no digits."""
        assert normalize_phone("+") == ""
        assert normalize_phone("+ - ()") == ""

    def test_single_digit(self):
        """Handle single-digit phone numbers."""
        assert normalize_phone("9") == "9"
        assert normalize_phone("+9") == "+9"

    def test_long_phone_numbers(self):
        """Handle long phone numbers."""
        long_number = "+1 (555) 123-4567 ext. 8901"
        # All digits extracted: 1 + 555 + 123 + 4567 + 8901
        assert normalize_phone(long_number) == "+155512345678901"

    def test_phone_with_dots(self):
        """Handle phone numbers with dots."""
        assert normalize_phone("555.123.4567") == "5551234567"
        assert normalize_phone("+1.555.123.4567") == "+15551234567"

    def test_phone_leading_zeros(self):
        """Preserve leading zeros in phone numbers."""
        assert normalize_phone("0555 123 4567") == "05551234567"
        assert normalize_phone("+44 0207 946 0958") == "+4402079460958"


class TestNormalizationIntegration:
    """Integration tests for email and phone normalization."""

    def test_extract_and_match_email_variations(self):
        """Verify emails with different cases match."""
        email1 = normalize_email("alice@example.com")
        email2 = normalize_email("ALICE@EXAMPLE.COM")
        email3 = normalize_email("  Alice@Example.COM  ")
        assert email1 == email2 == email3

    def test_extract_and_match_phone_variations(self):
        """Verify phones with different formatting match."""
        phone1 = normalize_phone("+1 (555) 123-4567")
        phone2 = normalize_phone("+1-555-123-4567")
        phone3 = normalize_phone("+15551234567")
        phone4 = normalize_phone("(555) 123-4567")  # Without country code
        assert phone1 == phone2 == phone3
        # Without country code differs
        assert phone4 == "5551234567"
        assert phone4 != phone1

    def test_mixed_identifier_normalization(self):
        """Test both emails and phones in a list."""
        identifiers = [
            ("ALICE@EXAMPLE.COM", "alice@example.com"),
            ("+1 (555) 123-4567", "+15551234567"),
            ("  Bob@Company.org  ", "bob@company.org"),
            ("555.987.6543", "5559876543"),
        ]
        for raw, normalized in identifiers:
            if "@" in raw:
                result = normalize_email(raw)
            else:
                result = normalize_phone(raw)
            assert result == normalized, f"Failed for {raw}: got {result}, expected {normalized}"
