"""Integration test — `--retry-skipped` 발송 보고서 동작 변화 안내 (T012, RED).

spec.md Edge Cases / SC-008:

운영자가 `--retry-skipped` 모드로 재시도할 때, 직전 발송 로그에 `failed`
status 인 학생이 존재하면 v0.1.0 과 달리 v0.1.1 에서는 *건너뜀(skip)* 된다.
이 동작 변화를 운영자가 발송 직후 인지할 수 있도록 ``메일_발송보고서.md``
하단에 다음 한글 안내 문구가 포함되어야 한다::

    v0.1.1 동작 변화: 발송 실패(failed) 상태인 학생 N명은 건너뜀(skip) — \
        `--retry-failed` 모드를 사용해야 재시도됩니다.

여기서 ``N`` 은 직전 로그의 ``failed`` status 학생 수.

RED 단계:
    v0.1.0 의 ``report.py`` 는 이 안내를 출력하지 않으므로 두 단언 모두 실패
    한다 (positive scenario). T016 에서 ``report.py`` 가 안내 라인을 emit 하
    도록 구현되면 GREEN 된다.
"""

from __future__ import annotations

import argparse
import io
from datetime import datetime, timezone, timedelta

import pytest

from immersio.email.log import append_dispatch_log_rows
from immersio.email.pipeline import run_email_dispatch
from paideia_shared.schemas import (
    CohortLabel,
    DispatchLogRow,
    DispatchMode,
    DispatchStatus,
)

KST = timezone(timedelta(hours=9))


def _args() -> argparse.Namespace:
    args = argparse.Namespace(
        profile="alpha-prof",
        semester="2026-1",
        course="anatomy",
        exam_name="중간고사",
        sent_date="2026-05-01",
        send=True,
        self_test=None,
        retry_failed=False,
        retry_skipped=True,
        rate_per_min=None,
        cohort="all",
        confirm_sample=3,
        bronze_csv=None,
        gold_pdf_dir=None,
        silver_master=None,
        silver_student_metrics=None,
        quiet=False,
        verbose=False,
    )
    args._stdin = io.StringIO("yes\n")
    args._stdout = io.StringIO()
    return args


class _CountingDispatcher:
    captured: list = []

    def __init__(self, profile, **kwargs):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return None

    def send_one(self, draft, *, pdf_bytes):
        from immersio.email.sender import SendResult

        type(self).captured.append(draft.student_id)
        return SendResult(
            status=DispatchStatus.SUCCESS,
            error_kind="",
            error_detail="",
            gmail_server_message_id=f"id-{draft.student_id}",
        )


def _seed_row(
    sid: str, status: DispatchStatus, error_kind: str = ""
) -> DispatchLogRow:
    return DispatchLogRow(
        student_id=sid,
        name_kr="홍길동",
        email="ok@example.com" if status != DispatchStatus.SKIPPED else "",
        pdf_filename=f"{sid}_홍길동.pdf",
        pdf_sha256="a" * 64 if status != DispatchStatus.SKIPPED else "",
        attempt_at_kst=datetime(2026, 4, 30, 12, 0, 0, tzinfo=KST),
        mode=DispatchMode.PRODUCTION,
        status=status,
        smtp_message_id="<x@example.ac.kr>"
        if status == DispatchStatus.SUCCESS
        else "",
        error_kind=error_kind,
        error_detail="",
        exam_name="중간고사",
        cohort=CohortLabel.ALL,
    )


def test_retry_skipped_notice_present_when_failed_exist(
    email_fixture, monkeypatch
) -> None:
    """Positive: ≥1 failed student + ``--retry-skipped`` → notice in md.

    Seed: 2 success + 2 failed + 1 skipped. ``--retry-skipped`` 모드는
    skipped 1 명만 재시도하지만, 보고서 md 에는 failed 2 명이 건너뜀(skip)
    되었다는 v0.1.1 동작 변화 안내가 명시적으로 포함되어야 한다 (SC-008).
    """
    sids = [s[0] for s in email_fixture["students"]]
    log_path = email_fixture["gold_email_dir"] / "메일_발송로그.csv"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    append_dispatch_log_rows(
        log_path,
        [
            _seed_row(sids[0], DispatchStatus.SUCCESS),
            _seed_row(sids[1], DispatchStatus.SUCCESS),
            _seed_row(
                sids[2], DispatchStatus.FAILED, error_kind="gmail_api_unknown"
            ),
            _seed_row(
                sids[3], DispatchStatus.FAILED, error_kind="gmail_api_unknown"
            ),
            _seed_row(
                sids[4], DispatchStatus.SKIPPED, error_kind="invalid_email"
            ),
        ],
    )

    _CountingDispatcher.captured = []
    monkeypatch.setattr(
        "immersio.email.sender.GmailAPIDispatcher", _CountingDispatcher
    )
    rc = run_email_dispatch(_args())
    assert rc == 0

    report_path = email_fixture["gold_email_dir"] / "메일_발송보고서.md"
    assert report_path.exists(), (
        f"메일_발송보고서.md 가 생성되지 않음: {report_path}"
    )
    content = report_path.read_text(encoding="utf-8")

    # Two resilient substring checks rather than full-line equality —
    # tolerant to whitespace / formatting variation in T016 implementation.
    assert "v0.1.1 동작 변화" in content, (
        "발송 보고서 md 에 v0.1.1 동작 변화 안내 도입부가 누락됨 (SC-008). "
        f"보고서 내용:\n{content}"
    )
    assert "`--retry-failed` 모드를 사용해야 재시도됩니다" in content, (
        "발송 보고서 md 에 `--retry-failed` 모드 안내 후미부가 누락됨 "
        f"(SC-008). 보고서 내용:\n{content}"
    )
    # N=2 (failed students count) 가 본문에 명시적으로 포함되어야 함.
    assert "2명" in content, (
        "발송 보고서 md 에 failed 학생 수(2명)가 명시되지 않음. "
        f"보고서 내용:\n{content}"
    )


def test_retry_skipped_notice_absent_when_no_failed(
    email_fixture, monkeypatch
) -> None:
    """Negative: 0 failed students + ``--retry-skipped`` → notice NOT emitted.

    Seed: 3 success + 2 skipped (failed 0 명). 동작 변화 안내는 운영자가 실제로
    영향받는 케이스에서만 노출되어야 하므로 보고서 md 에 출력되지 않아야 한다.
    """
    sids = [s[0] for s in email_fixture["students"]]
    log_path = email_fixture["gold_email_dir"] / "메일_발송로그.csv"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    append_dispatch_log_rows(
        log_path,
        [
            _seed_row(sids[0], DispatchStatus.SUCCESS),
            _seed_row(sids[1], DispatchStatus.SUCCESS),
            _seed_row(sids[2], DispatchStatus.SUCCESS),
            _seed_row(
                sids[3], DispatchStatus.SKIPPED, error_kind="invalid_email"
            ),
            _seed_row(
                sids[4], DispatchStatus.SKIPPED, error_kind="email_not_found"
            ),
        ],
    )

    _CountingDispatcher.captured = []
    monkeypatch.setattr(
        "immersio.email.sender.GmailAPIDispatcher", _CountingDispatcher
    )
    rc = run_email_dispatch(_args())
    assert rc == 0

    report_path = email_fixture["gold_email_dir"] / "메일_발송보고서.md"
    assert report_path.exists(), (
        f"메일_발송보고서.md 가 생성되지 않음: {report_path}"
    )
    content = report_path.read_text(encoding="utf-8")

    assert "v0.1.1 동작 변화" not in content, (
        "failed 학생이 0 명일 때는 동작 변화 안내가 출력되지 않아야 함 — "
        f"불필요한 노출 발생. 보고서 내용:\n{content}"
    )
