"""Input validation and sanitisation for BlindSpot AI."""

from __future__ import annotations

import re
import unicodedata

# Control characters to strip (keep standard whitespace: space, tab, newline)
_CONTROL_CHAR_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


def strip_control_chars(value: str) -> str:
    """
    Remove ASCII control characters from a string.

    Preserves normal whitespace (space, tab, newline) while stripping
    characters that have no legitimate role in decision text.

    Args:
        value: Raw user-supplied string.

    Returns:
        Cleaned string.
    """
    return _CONTROL_CHAR_RE.sub("", value)


def normalise_whitespace(value: str) -> str:
    """
    Collapse runs of whitespace to single spaces and strip leading/trailing whitespace.

    Args:
        value: Input string.

    Returns:
        Normalised string.
    """
    return " ".join(value.split())


def sanitise_field(value: str, max_length: int) -> str:
    """
    Sanitise a single user input field.

    Steps applied in order:
    1. Strip control characters.
    2. Normalise unicode to NFC.
    3. Truncate to max_length (as a safety net; primary validation is in Pydantic).

    Args:
        value: Raw field value.
        max_length: Maximum allowed character count.

    Returns:
        Sanitised string, guaranteed to be no longer than max_length.
    """
    cleaned = strip_control_chars(value)
    cleaned = unicodedata.normalize("NFC", cleaned)
    return cleaned[:max_length]
