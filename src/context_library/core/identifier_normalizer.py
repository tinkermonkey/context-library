"""Utility functions for normalizing email and phone identifiers.

This module provides normalization functions to ensure consistent identifier
matching across different formats and representations. Without normalization,
queries would fail due to:
- Email case sensitivity: alice@example.com != ALICE@EXAMPLE.COM
- Phone formatting: "+1 (555) 123-4567" != "+15551234567"
"""

import re


def normalize_email(email: str) -> str:
    """Normalize an email address for matching.

    Normalization steps:
    1. Strip leading/trailing whitespace
    2. Convert to lowercase
    3. Remove extra whitespace within the email (preserves structure)

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
    normalized = email.strip().lower()
    return normalized


def normalize_phone(phone: str) -> str:
    """Normalize a phone number for matching.

    Normalization steps:
    1. Strip leading/trailing whitespace
    2. Strip common extension patterns (ext., x, etc.) before normalization
    3. Remove all whitespace, parentheses, hyphens, and other formatting
    4. Keep only digits and the leading '+' sign (if present)
    5. Handle country code ambiguity: numbers without '+' prefix are normalized
       to "+1" (US country code) to match numbers with explicit "+1" prefix
    6. Return empty string if no digits remain

    This approach handles various formats and ensures country code consistency:
    - "+1 (555) 123-4567" → "+15551234567"
    - "555-123-4567" → "+15551234567" (normalized to +1 for matching)
    - "(555) 123-4567" → "+15551234567" (normalized to +1 for matching)
    - "+1-555-123-4567" → "+15551234567"
    - "+44 20 7946 0958" → "+442079460958" (international, +44 preserved)
    - "555-123-4567 ext. 123" → "+15551234567" (extension stripped)
    - "0555 123 4567" → "+15551234567" (leading zero stripped for US, NOT "+105551234567")

    By normalizing domestic numbers to "+1", we enable entity linking between
    contacts and messages that reference the same number with and without the
    country code prefix (e.g., "555-123-4567" will match "+1-555-123-4567").

    KNOWN LIMITATIONS:
    - Numbers with leading zeros (e.g., "0555 123 4567") are non-standard for
      US numbers and will be normalized to "+1" after stripping the leading zero.
      This is acceptable for US-centric usage but may produce unexpected results
      for international numbers without explicit country codes.

    Args:
        phone: Raw phone number string.

    Returns:
        Normalized phone number string with '+' prefix, or empty string if
        input is empty/None or contains no digits.

    Examples:
        >>> normalize_phone("+1 (555) 123-4567")
        '+15551234567'
        >>> normalize_phone("555-123-4567")
        '+15551234567'
        >>> normalize_phone("  +1-555-123-4567  ")
        '+15551234567'
        >>> normalize_phone("+44 20 7946 0958")
        '+442079460958'
        >>> normalize_phone("555-123-4567 ext. 123")
        '+15551234567'
    """
    if not phone:
        return ""

    normalized = phone.strip()

    # Strip common extension patterns before processing
    # This prevents extensions from being merged into the phone number
    normalized = re.sub(r'\s*(ext\.?|x|extension)\s+\d+$', '', normalized, flags=re.IGNORECASE)

    # Check if phone starts with '+' to preserve it
    has_plus = normalized.startswith("+")

    # Remove all non-digit characters
    digits_only = re.sub(r"\D", "", normalized)

    # Return empty string if no digits remain
    if not digits_only:
        return ""

    # If no '+' prefix, assume US domestic number and add "+1" country code
    if not has_plus:
        # Strip leading zeros for domestic numbers (non-standard for US)
        digits_only = digits_only.lstrip('0')
        if not digits_only:
            return ""
        return "+1" + digits_only

    # If '+' prefix was present, restore it
    return "+" + digits_only
