"""Multiselect response splitting with deterministic option order."""

from __future__ import annotations


def expand_multiselect(value: str, separator: str = ";") -> list[str]:
    """Split a multiselect response into a list of option keys.

    Args:
        value: Raw response string (semicolon-separated by default).
        separator: Delimiter character.

    Returns:
        List of option keys in original order, with whitespace stripped
        and empty entries removed. Returns ``[]`` for empty input.

    Raises:
        TypeError: If value is not a str.
    """
    if not isinstance(value, str):
        raise TypeError(
            f"expand_multiselect: expected str, got {type(value).__name__} ({value!r})."
        )
    if not value:
        return []
    options: list[str] = []
    for token in value.split(separator):
        stripped = token.strip()
        if stripped:
            options.append(stripped)
    return options
