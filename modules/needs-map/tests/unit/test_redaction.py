"""PII redaction unit tests [T057].

US6 spec FR-027 — student IDs (10 digits) and roster names must be
masked before sentiment inference.

Spec: 003-needs-map-v0-1-1/tasks.md T057.
"""

from __future__ import annotations


def test_redact_pii_masks_ten_digit_student_id() -> None:
    """A 10-digit number sequence MUST be replaced by ``[ID]``."""
    from needs_map.free_text.redaction import redact_pii

    text = "학번 2026194567 입니다. 시험 점수가 걱정돼요."
    result = redact_pii(text)
    assert "2026194567" not in result
    assert "[ID]" in result
    assert "시험 점수가 걱정돼요" in result  # rest of text intact


def test_redact_pii_does_not_mask_short_numbers() -> None:
    """Sequences shorter than 10 digits MUST stay verbatim (e.g. 시험 점수)."""
    from needs_map.free_text.redaction import redact_pii

    text = "9월 7일에 시험이 있어요. 점수는 85점입니다."
    result = redact_pii(text)
    assert result == text  # no 10-digit sequence


def test_redact_pii_masks_roster_names_long_first() -> None:
    """Longer name MUST be masked first to prevent partial leakage."""
    from needs_map.free_text.redaction import redact_pii

    text = "김민수 학생이 김민에게 도와달라고 했다."
    result = redact_pii(text, names=("김민", "김민수"))
    # Both names masked; "김민수" masked as one unit (no "수" leftover)
    assert "김민수" not in result
    assert "김민" not in result
    assert "[NAME]" in result


def test_redact_pii_empty_string_passthrough() -> None:
    """Empty / whitespace input is returned verbatim (no error)."""
    from needs_map.free_text.redaction import redact_pii

    assert redact_pii("") == ""
    assert redact_pii("   ") == "   "


def test_redact_pii_idempotent() -> None:
    """Running twice on already-redacted text MUST be a no-op."""
    from needs_map.free_text.redaction import redact_pii

    text = "학번 2026194567 김민수입니다."
    once = redact_pii(text, names=("김민수",))
    twice = redact_pii(once, names=("김민수",))
    assert once == twice
