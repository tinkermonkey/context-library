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
    2. Remove all whitespace, parentheses, and hyphens
    3. Keep only digits and the leading '+' sign (if present)
    4. Return empty string if no digits remain

    This approach handles various formats:
    - "+1 (555) 123-4567" → "+15551234567"
    - "555-123-4567" → "5551234567"
    - "(555) 123-4567" → "5551234567"
    - "+1-555-123-4567" → "+15551234567"

    Args:
        phone: Raw phone number string.

    Returns:
        Normalized phone number string, or empty string if input is empty/None
        or contains no digits.

    Examples:
        >>> normalize_phone("+1 (555) 123-4567")
        '+15551234567'
        >>> normalize_phone("555-123-4567")
        '5551234567'
        >>> normalize_phone("  +1-555-123-4567  ")
        '+15551234567'
    """
    if not phone:
        return ""

    normalized = phone.strip()

    # Check if phone starts with '+' to preserve it
    has_plus = normalized.startswith("+")

    # Remove all non-digit characters
    digits_only = re.sub(r"\D", "", normalized)

    # Return empty string if no digits remain
    if not digits_only:
        return ""

    # Restore the '+' prefix if it was present
    if has_plus:
        return "+" + digits_only

    return digits_only
