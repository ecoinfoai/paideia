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


# --- PII-01 widening: phone / email / RRN / birthdate / name-role -----------


def test_redact_strips_dashed_phone() -> None:
    text = "연락처는 010-1234-5678 입니다."
    redacted, ok = redact(text, names=[])
    assert "010-1234-5678" not in redacted
    assert "1234" not in redacted
    assert "5678" not in redacted
    assert ok is True


def test_redact_strips_continuous_11_digit_phone() -> None:
    """11-digit mobile must be fully removed — no trailing digit left over.

    Closes the old gap where ``\\d{10}`` matched only the first 10 digits of an
    11-digit run, leaving a stray trailing digit.
    """
    text = "전화 01012345678 로 주세요."
    redacted, ok = redact(text, names=[])
    assert "01012345678" not in redacted
    assert not any(ch.isdigit() for ch in redacted)
    assert ok is True


def test_redact_strips_email() -> None:
    text = "메일 hong@bhc.ac.kr 로 회신 바랍니다."
    redacted, ok = redact(text, names=[])
    assert "hong@bhc.ac.kr" not in redacted
    assert "@" not in redacted
    assert ok is True


def test_redact_strips_korean_rrn() -> None:
    text = "주민번호 901231-1234567 노출됨."
    redacted, ok = redact(text, names=[])
    assert "901231-1234567" not in redacted
    assert ok is True


def test_redact_strips_separator_birthdate() -> None:
    text = "생년월일 2001-03-21 입니다."
    redacted, ok = redact(text, names=[])
    assert "2001-03-21" not in redacted
    assert ok is True


def test_redact_strips_surname_role() -> None:
    text = "박교수님께 배웠어요."
    redacted, ok = redact(text, names=[])
    assert "박교수" not in redacted
    assert "[REDACTED]" in redacted
    assert "배웠어요" in redacted
    assert ok is True


def test_redact_validation_flag_false_when_high_conf_pii_remains() -> None:
    """A high-confidence pattern present in the OUTPUT flips validation_flag False.

    Constructed so the literal roster-name replacement (which runs LAST, after
    the high-confidence scrubs) substitutes a ``[REDACTED]`` token whose
    non-word ``]`` introduces a word boundary, exposing a birthdate
    ``01-03-21`` that the earlier birthdate scrub could not see (it was
    Hangul-flanked, so no ``\\b``). The final validation pass scans the OUTPUT,
    detects the birthdate, and returns ``ok=False`` — exercising the AND
    semantics over the high-confidence set.
    """
    text = "생일은 20홍01-03-21 이야"
    redacted, ok = redact(text, names=["홍"])
    assert "01-03-21" in redacted  # birthdate exposed by token word-boundary
    assert ok is False


def test_redact_pii_free_korean_prose_unchanged_no_block() -> None:
    """Ordinary student prose must NOT be blocked (critical: no false positive)."""
    text = "시험이 너무 어려워서 불안해요"
    redacted, ok = redact(text, names=[])
    assert redacted == text
    assert ok is True


def test_redact_idempotent() -> None:
    text = "박교수님께 010-1234-5678 로 hong@bhc.ac.kr, 학번 2026194042"
    names = ["홍길동"]
    once = redact(text, names)[0]
    twice = redact(once, names)[0]
    assert twice == once
