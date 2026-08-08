"""Shared phone/email normalization contract.

This module is the single source of truth for identifier normalization used
across ingestion (e.g. `PeopleMetadata` construction) and matching (the
entity linker's JSON-path comparisons). Without a shared, canonical form,
identifiers collected in different formats never compare equal:
- Email case sensitivity: alice@example.com != ALICE@EXAMPLE.COM
- Phone formatting: "(555) 123-4567" != "5551234567" != "+1 555 123 4567"

Phone numbers are canonicalized to E.164 (`+{country_code}{number}`, e.g.
`+15551234567`) via the `phonenumbers` library, which handles country-code
inference and international formats robustly. Numbers without an explicit
country code are assumed to be US/Canada (NANP) numbers.
"""

import phonenumbers

_DEFAULT_REGION = "US"


def normalize_email(email: str) -> str:
    """Normalize an email address for matching.

    Normalization steps:
    1. Strip leading/trailing whitespace
    2. Convert to lowercase

    Args:
        email: Raw email string.

    Returns:
        Normalized email string, or empty string if input is empty/None.

    Examples:
        >>> normalize_email("Alice@Example.COM")
        'alice@example.com'
        >>> normalize_email("  bob@company.co.uk  ")
        'bob@company.co.uk'
    """
    if not email:
        return ""
    return email.strip().lower()


def normalize_phone(phone: str) -> str:
    """Normalize a phone number to canonical E.164 form for matching.

    Numbers with an explicit '+' country code prefix are parsed using that
    country code; numbers without one are assumed to be US/Canada (NANP)
    numbers. Extensions (e.g. "ext. 123", "x123") are parsed out and dropped
    since E.164 has no extension component.

    Args:
        phone: Raw phone number string.

    Returns:
        E.164-formatted phone number (e.g. "+15551234567"), or an empty
        string if input is empty/None/blank, or if it cannot be parsed as a
        possible phone number.

    Examples:
        >>> normalize_phone("(555) 123-4567")
        '+15551234567'
        >>> normalize_phone("+1 (555) 123-4567")
        '+15551234567'
        >>> normalize_phone("+44 20 7946 0958")
        '+442079460958'
        >>> normalize_phone("555-123-4567 ext. 123")
        '+15551234567'
    """
    if not phone:
        return ""

    stripped = phone.strip()
    if not stripped:
        return ""

    try:
        parsed = phonenumbers.parse(stripped, _DEFAULT_REGION)
    except phonenumbers.NumberParseException:
        return ""

    if not phonenumbers.is_possible_number(parsed):
        return ""

    return phonenumbers.format_number(parsed, phonenumbers.PhoneNumberFormat.E164)
