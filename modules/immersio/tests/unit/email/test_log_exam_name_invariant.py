"""read_dispatch_log() exam_name distinct invariant tests (T008) — FR-C02a-1.

v0.1.1 은 한 학기·과목당 단일 exam_name 만 지원한다. 운영 invariant 로서
csv 안에 2종 이상의 exam_name 이 섞여 있을 경우 ``ExamNameInvariantError``
를 raise 하여 idempotent skip 키 (학번 단독) 의 안전성을 보장한다.
"""

from __future__ import annotations

from datetime import datetime, timezone, timedelta
from pathlib import Path

import pytest

from immersio.email.log import (
    ExamNameInvariantError,
    append_dispatch_log_rows,
    read_dispatch_log,
)
from paideia_shared.schemas import (
    CohortLabel,
    DispatchLogRow,
    DispatchMode,
    DispatchStatus,
)

KST = timezone(timedelta(hours=9))


def _row(
    sid: str,
    *,
    exam_name: str = "중간고사_진단",
    minute: int = 0,
) -> DispatchLogRow:
    return DispatchLogRow(
        student_id=sid,
        name_kr="홍길동",
        email="ok@example.com",
        pdf_filename=f"{sid}_홍길동.pdf",
        pdf_sha256="a" * 64,
        attempt_at_kst=datetime(2026, 5, 1, 12, minute, 0, tzinfo=KST),
        mode=DispatchMode.PRODUCTION,
        status=DispatchStatus.SUCCESS,
        smtp_message_id="<deterministic@example.ac.kr>",
        error_kind="",
        error_detail="",
        exam_name=exam_name,
        cohort=CohortLabel.ALL,
    )


# ---------------------------------------------------------------------------
# Violation: 2종 exam_name → ExamNameInvariantError
# ---------------------------------------------------------------------------


def test_two_distinct_exam_names_raises(tmp_path: Path) -> None:
    """csv 에 2종 exam_name 섞임 → ExamNameInvariantError raise (FR-C02a-1)."""
    log = tmp_path / "log.csv"
    rows = [
        _row("1234567001", exam_name="중간고사_진단", minute=0),
        _row("1234567002", exam_name="기말고사_진단", minute=1),
    ]
    append_dispatch_log_rows(log, rows)

    with pytest.raises(ExamNameInvariantError) as exc_info:
        read_dispatch_log(log)

    msg = str(exc_info.value)
    # 한글 안내 메시지 포함
    assert "운영 invariant 위반" in msg
    # sorted 한글 — '기말고사_진단' < '중간고사_진단' (유니코드 codepoint 기준)
    assert "기말고사_진단" in msg
    assert "중간고사_진단" in msg
    # sorted 순서 보존 (sorted([...]) 의 list repr 안에서 '기말' 이 '중간' 보다 앞)
    assert msg.index("기말고사_진단") < msg.index("중간고사_진단")
    # log_path 가 메시지에 포함
    assert str(log) in msg


def test_invariant_error_is_value_error(tmp_path: Path) -> None:
    """ExamNameInvariantError 는 ValueError 의 서브클래스여야 한다."""
    log = tmp_path / "log.csv"
    append_dispatch_log_rows(
        log,
        [
            _row("1234567001", exam_name="A_진단", minute=0),
            _row("1234567002", exam_name="B_진단", minute=1),
        ],
    )
    with pytest.raises(ValueError):
        read_dispatch_log(log)


def test_three_distinct_exam_names_sorted_in_message(tmp_path: Path) -> None:
    """3종 이상이면 모두 sorted list 로 메시지에 포함되어야 한다."""
    log = tmp_path / "log.csv"
    append_dispatch_log_rows(
        log,
        [
            _row("1234567001", exam_name="중간고사_진단", minute=0),
            _row("1234567002", exam_name="기말고사_진단", minute=1),
            _row("1234567003", exam_name="쪽지시험_진단", minute=2),
        ],
    )
    with pytest.raises(ExamNameInvariantError) as exc_info:
        read_dispatch_log(log)
    msg = str(exc_info.value)
    # 모두 포함
    assert "기말고사_진단" in msg
    assert "중간고사_진단" in msg
    assert "쪽지시험_진단" in msg
    # sorted 순서: 기말 < 쪽지 < 중간 (유니코드 codepoint)
    sorted_names = sorted(["중간고사_진단", "기말고사_진단", "쪽지시험_진단"])
    last_idx = -1
    for name in sorted_names:
        idx = msg.index(name)
        assert idx > last_idx, (
            f"exam_name '{name}' 가 sorted 순서대로 메시지에 등장하지 않음"
        )
        last_idx = idx


# ---------------------------------------------------------------------------
# Pass cases: 단일 exam_name / 빈 csv
# ---------------------------------------------------------------------------


def test_single_exam_name_passes(tmp_path: Path) -> None:
    """csv 전체가 동일 exam_name → 정상 통과 + 모든 row 반환."""
    log = tmp_path / "log.csv"
    rows = [
        _row("1234567001", exam_name="중간고사_진단", minute=0),
        _row("1234567002", exam_name="중간고사_진단", minute=1),
        _row("1234567003", exam_name="중간고사_진단", minute=2),
    ]
    append_dispatch_log_rows(log, rows)

    result = read_dispatch_log(log)
    assert len(result) == 3
    assert {r.student_id for r in result} == {
        "1234567001",
        "1234567002",
        "1234567003",
    }
    assert {r.exam_name for r in result} == {"중간고사_진단"}


def test_single_row_passes(tmp_path: Path) -> None:
    """csv 에 row 1개만 있어도 정상 통과 (distinct 1종)."""
    log = tmp_path / "log.csv"
    append_dispatch_log_rows(
        log, [_row("1234567001", exam_name="중간고사_진단")]
    )
    result = read_dispatch_log(log)
    assert len(result) == 1
    assert result[0].exam_name == "중간고사_진단"


def test_missing_file_returns_empty(tmp_path: Path) -> None:
    """파일 부재 → []. invariant check 진입 전에 short-circuit."""
    log = tmp_path / "does_not_exist.csv"
    assert read_dispatch_log(log) == []


def test_header_only_returns_empty(tmp_path: Path) -> None:
    """header 만 있는 빈 csv → [] (regression guard: distinct set is empty)."""
    log = tmp_path / "log.csv"
    # append_dispatch_log_rows 의 헤더-생성 경로를 이용하여 헤더만 있는 csv 작성
    header = ",".join(DispatchLogRow.COLUMN_ORDER) + "\n"
    log.write_text(header, encoding="utf-8")
    result = read_dispatch_log(log)
    assert result == []
