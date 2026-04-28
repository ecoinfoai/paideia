"""PII redaction for freetext sentiment inference [T057].

US6 spec FR-027: redact 10-digit student IDs and roster-derived names
before feeding text into the RoBERTa tokenizer. Redaction is *content*
masking — the resulting text retains structure (other characters and
punctuation unchanged) so RoBERTa can still classify the underlying
emotion.

The redaction strings (`[ID]`, `[NAME]`) are intentionally short so
char_start / char_end token offsets stay close to the original text
positions; downstream consumers (``write_freetext_audit``) record
char_start/char_end on the *redacted* text per data-model.md §9.

This is separate from the v0.1.0 LLM-side redaction in
``needs_map.llm.redaction`` (which sanitises text just before the
Anthropic API call). Both must run because they target different
surfaces; calling them is idempotent on already-redacted strings.
"""

from __future__ import annotations

import re
from collections.abc import Iterable

# 10-digit Korean student ID pattern (e.g. "2026194567"). Year prefix is
# typically 4 digits + 6-digit student suffix; we keep a generic
# 10-digit guard so all valid IDs are caught.
_STUDENT_ID_PATTERN = re.compile(r"\b\d{10}\b")

_ID_REPLACEMENT = "[ID]"
_NAME_REPLACEMENT = "[NAME]"


def redact_pii(text: str, names: Iterable[str] = ()) -> str:
    """Mask 10-digit student IDs and roster names in ``text``.

    Args:
        text: Korean / English freetext from a single response cell.
        names: Iterable of student names (Korean) to mask. Order matters
            only for tie-breaking; longer names are masked first to avoid
            partial substring leakage on names that share a surname.

    Returns:
        ``text`` with student IDs replaced by ``[ID]`` and roster names
        replaced by ``[NAME]``. Empty / whitespace-only input is returned
        verbatim.
    """
    if not text or not text.strip():
        return text
    redacted = _STUDENT_ID_PATTERN.sub(_ID_REPLACEMENT, text)
    # Mask longer names first so "김민수" doesn't leak when "김민" is also
    # in the roster (rare but defensive).
    sorted_names = sorted({n for n in names if n}, key=len, reverse=True)
    for name in sorted_names:
        redacted = redacted.replace(name, _NAME_REPLACEMENT)
    return redacted


__all__ = ["redact_pii"]
