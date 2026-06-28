"""PII redaction for LLM payloads (T024, FR-PII-002 / FR-PII-003).

Strips high-confidence personal identifiers from a free-text payload before it
is sent to an external LLM provider (security finding PII-01). Scrubbed, in
order: phone numbers (dashed or continuous 11-digit mobile), Korean resident
registration numbers (RRN), separator-bearing birthdates, email addresses,
3rd-party Korean surname+role mentions (``박교수``), 10-digit student IDs
(``\\d{10}``), and any literal name tokens listed in ``StudentMaster.name``.
All are replaced with ``[REDACTED]``.

Returns a ``(redacted_text, validation_flag)`` pair where ``validation_flag`` is
True only if NONE of the high-confidence patterns (phone, email, RRN, birthdate,
surname+role, ``\\d{10}``) remain after scrubbing. A False flag is the
fail-closed backstop: the caller MUST then block the LLM call (the
``LLMCallTracker`` records this as ``failure_kind="pii_block"``, adversary H-8).

The phone scrub runs BEFORE the ``\\d{10}`` student-id scrub so an 11-digit
continuous mobile is removed whole, with no stray trailing digit left behind.

Known deterministic-detection residuals (accepted, deferred to a future
``006-redaction-hardening`` effort): bare given names without a role token, and
separator-less 6-digit ``YYMMDD`` birthdates. A generic "any 2-4 Hangul run"
heuristic is intentionally NOT used — it would false-block ordinary student
prose.
"""

from __future__ import annotations

import re
from collections.abc import Iterable

_STUDENT_ID_RE = re.compile(r"\d{10}")
_EMAIL_PATTERN = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}")
# 3rd-party Korean surname+role pattern. Mirrors metric-codex
# ``generate/bundle.py`` but DROPS the trailing ``(?![가-힣])`` lookahead the
# label-oriented metric-codex pattern carries: needs-map scrubs free-text
# student prose where the honorific ``님`` and josa (``께``/``이``/``은``…) attach
# directly to the role token (``박교수님께``), so a right Hangul-boundary
# assertion would never fire and the mention would leak. The leading lookbehind
# ``(?<![가-힣])`` is kept (prevents left mid-word slices like ``대박사건``). The
# tradeoff is safe over-redaction of rare noun+role compounds (``방사선생물학``)
# — the conservative bias for an LLM-facing redactor (the model only ever sees
# ``[REDACTED]``; no leak, no crash).
_THIRD_PARTY_NAME_ROLE_PATTERN = re.compile(
    r"(?<![가-힣])[가-힣]{1,2}(?:교수|선생님|선생|박사|쌤|조교)"
)
_PHONE_PATTERN = re.compile(r"0\d{1,2}[-.\s]?\d{3,4}[-.\s]?\d{4}")
_RRN_PATTERN = re.compile(r"\b\d{6}-\d{7}\b")
_BIRTHDATE_PATTERN = re.compile(r"\b\d{2,4}[-./]\d{1,2}[-./]\d{1,2}\b")

# High-confidence patterns whose presence in the OUTPUT flips validation_flag
# to False (fail-closed). Order here is irrelevant; scrub order is fixed below.
_HIGH_CONFIDENCE_PATTERNS = (
    _PHONE_PATTERN,
    _EMAIL_PATTERN,
    _RRN_PATTERN,
    _BIRTHDATE_PATTERN,
    _THIRD_PARTY_NAME_ROLE_PATTERN,
    _STUDENT_ID_RE,
)

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
        the post-redaction text contains no remaining high-confidence PII
        pattern (phone, email, RRN, birthdate, surname+role, ``\\d{10}``).

    Raises:
        TypeError: If ``text`` is not a ``str``.
    """
    if not isinstance(text, str):
        raise TypeError(f"redact: expected str text, got {type(text).__name__}.")

    # Phone BEFORE student-id so an 11-digit mobile is consumed whole and does
    # not leave a stray trailing digit for a partial \d{10} match.
    redacted = _PHONE_PATTERN.sub(_REDACTED_TOKEN, text)
    redacted = _RRN_PATTERN.sub(_REDACTED_TOKEN, redacted)
    redacted = _BIRTHDATE_PATTERN.sub(_REDACTED_TOKEN, redacted)
    redacted = _EMAIL_PATTERN.sub(_REDACTED_TOKEN, redacted)
    redacted = _THIRD_PARTY_NAME_ROLE_PATTERN.sub(_REDACTED_TOKEN, redacted)
    redacted = _STUDENT_ID_RE.sub(_REDACTED_TOKEN, redacted)
    for name in names:
        if not isinstance(name, str) or not name:
            continue
        redacted = redacted.replace(name, _REDACTED_TOKEN)

    validation_flag = not any(p.search(redacted) for p in _HIGH_CONFIDENCE_PATTERNS)
    return redacted, validation_flag
