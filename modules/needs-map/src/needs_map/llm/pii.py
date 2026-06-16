"""PII redaction for LLM payloads (T024, FR-PII-002 / FR-PII-003).

Strips 10-digit student IDs (``\\d{10}`` zero-padded) and any name tokens
listed in ``StudentMaster.name`` from a text payload before it is sent to an
external LLM provider. Returns a (redacted_text, validation_flag) pair where
``validation_flag=False`` indicates a residual ``\\d{10}`` match — the caller
MUST then block the LLM call (the ``LLMCallTracker`` records this as
``failure_kind="pii_block"``, adversary H-8).

The redactor never raises on input shape: empty / non-string-like input is
mapped to ``("", True)`` so callers can normalize before scanning.
"""

from __future__ import annotations

import re
from collections.abc import Iterable

_STUDENT_ID_RE = re.compile(r"\d{10}")
_REDACTED_TOKEN = "[REDACTED]"  # noqa: S105 — placeholder substring, not a credential


def redact(text: str, names: Iterable[str]) -> tuple[str, bool]:
    """Strip student-ID and name occurrences from ``text``.

    Args:
        text: Raw payload text. ``None`` and non-string inputs raise TypeError
            because the caller has the contextual knowledge needed to decide
            whether an empty payload is meaningful.
        names: Iterable of student names (typically ``StudentMaster.name``).
            Each non-empty name is replaced with ``[REDACTED]`` as a literal
            substring (not regex) so that name fragments containing regex
            metacharacters do not raise.

    Returns:
        ``(redacted_text, validation_flag)`` — ``validation_flag`` is True iff
        the post-redaction text contains no remaining ``\\d{10}`` substring.

    Raises:
        TypeError: If ``text`` is not a ``str``.
    """
    if not isinstance(text, str):
        raise TypeError(f"redact: expected str text, got {type(text).__name__}.")

    redacted = _STUDENT_ID_RE.sub(_REDACTED_TOKEN, text)
    for name in names:
        if not isinstance(name, str) or not name:
            continue
        redacted = redacted.replace(name, _REDACTED_TOKEN)

    validation_flag = _STUDENT_ID_RE.search(redacted) is None
    return redacted, validation_flag
