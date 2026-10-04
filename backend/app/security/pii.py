"""PII detection for BlindSpot AI.

Detects email addresses and phone numbers in user input so that the
frontend can display a warning. No PII is stored or logged.
"""

from __future__ import annotations

import re

# Broad email regex (detects most common patterns)
_EMAIL_RE = re.compile(
    r"\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b"
)

# Phone number regex — matches common formats across regions:
# +1 (555) 555-5555, 555-555-5555, 0044 7700 900000, etc.
_PHONE_RE = re.compile(
    r"""
    (?:
        \+?\d{1,3}[\s\-.]?       # optional country code
    )?
    (?:
        \(?\d{2,4}\)?[\s\-.]?    # area code
    )?
    \d{3,4}[\s\-.]?\d{3,4}       # main number
    \b
    """,
    re.VERBOSE,
)


def contains_pii(text: str) -> bool:
    """
    Return True if the text appears to contain an email address or phone number.

    This is a best-effort heuristic; it may have false positives or negatives.
    It is used only to trigger a user-facing warning, not to block input.

    Args:
        text: Combined user input string.

    Returns:
        True if a potential PII pattern is detected.
    """
    if _EMAIL_RE.search(text):
        return True
    # Require at least 10 digits to reduce noise from short numeric strings
    phone_matches = _PHONE_RE.findall(text)
    for match in phone_matches:
        digits = re.sub(r"\D", "", match)
        if len(digits) >= 10:
            return True
    return False
