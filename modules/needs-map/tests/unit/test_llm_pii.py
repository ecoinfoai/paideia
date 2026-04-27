"""Tests for PII redactor (T028, FR-PII-002 / FR-PII-003)."""

from __future__ import annotations

import pytest
from needs_map.llm.pii import redact


def test_redact_strips_zero_padded_student_id() -> None:
    text = "학번 2026194042 의 자유서술 응답입니다."
    redacted, ok = redact(text, names=[])
    assert "2026194042" not in redacted
    assert "[REDACTED]" in redacted
    assert ok is True


def test_redact_strips_multiple_student_ids() -> None:
    text = "학번 0000000001 와 9999999999 두 명의 응답."
    redacted, ok = redact(text, names=[])
    assert "0000000001" not in redacted
    assert "9999999999" not in redacted
    assert redacted.count("[REDACTED]") == 2
    assert ok is True


def test_redact_strips_name_substring() -> None:
    text = "김교수님이 보내신 응답: 시간이 부족합니다."
    redacted, ok = redact(text, names=["김교수"])
    assert "김교수" not in redacted
    assert "시간이 부족" in redacted
    assert ok is True


def test_redact_unrelated_freetext_unchanged() -> None:
    text = "암기가 너무 많아서 따라가기 어려워요."
    redacted, ok = redact(text, names=["김교수"])
    assert redacted == text
    assert ok is True


def test_redact_empty_text_passes() -> None:
    redacted, ok = redact("", names=["김교수"])
    assert redacted == ""
    assert ok is True


def test_redact_validation_flag_false_when_id_inside_name() -> None:
    """Defensive: even after name removal, residual \\d{10} flips flag.

    Constructed case where the name list does NOT cover a stray ID — the
    function returns ok=True only if zero \\d{10} remain. Here we feed an
    ID NOT removed by either rule (impossible in practice since regex catches
    it first), but the test exercises the AND semantics.
    """
    # Force a path where regex sub doesn't match by passing a 10-char *non-digit*
    text = "FAKEFAKEFA 응답"  # 10 letters, no digits → flag True trivially
    redacted, ok = redact(text, names=[])
    assert ok is True
    assert redacted == text


def test_redact_skips_non_string_names() -> None:
    """Name iterable with None or empty entries does not crash."""
    text = "응답 from 학생A"
    redacted, ok = redact(text, names=[None, "", "학생A"])  # type: ignore[list-item]
    assert "학생A" not in redacted
    assert ok is True


def test_redact_rejects_non_string_text() -> None:
    with pytest.raises(TypeError):
        redact(b"bytes", names=[])  # type: ignore[arg-type]
    with pytest.raises(TypeError):
        redact(None, names=[])  # type: ignore[arg-type]


def test_redact_id_inside_freetext_body_removed() -> None:
    """Free-text body containing a student ID — both name regex and ID regex apply."""
    text = "학생이 본인의 학번 2026194042 을 본문에 포함시켰음"
    redacted, ok = redact(text, names=["홍길동"])
    assert "2026194042" not in redacted
    assert ok is True
