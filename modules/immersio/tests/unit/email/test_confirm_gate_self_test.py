"""self-test 모드 confirm_gate stdout 단언 (T017 — spec 007 immersio/email-v0.1.1).

FR-C04d / FR-C04e — `is_self_test=True` PreSendSummary 를 ``confirm_first_n`` 에
전달했을 때:

1. 최상단 강조 라인 2 줄 (정확한 텍스트, contracts/confirm_gate_output.md §4 기준).
2. 3-bucket 카운트 줄 (idempotent skip 카운트 *없음* — production gate 와의 차이).
3. 표본 prefix "(수신자=본인)" + 각 학번 행 끝 "(수신자=<operator_email>)".
4. PII invariant (FR-C04c) — 학생 이름/이메일은 표본 라인에만 (다른 라인 0건).

contracts/confirm_gate_output.md §8.4 (cohort low_score 결합) 와 §8.5 (cohort all)
2 시나리오를 parametrize.

본 테스트는 T018 (confirm_first_n self-test 분기 구현) 의 RED 단계 — 현재
``confirm_first_n`` body 는 v0.1.0 출력만 emit 하므로 *반드시 FAIL* 해야 한다.
"""

from __future__ import annotations

import hashlib
import io
from datetime import date, datetime, timezone
from pathlib import Path

import pytest
import yaml

from immersio.email.composer import build_email_draft
from immersio.email.confirm_gate import confirm_first_n
from paideia_shared.schemas import (
    DispatchMode,
    EmailMappingEntry,
    PreSendSummary,
    ProfessorProfile,
    StudentPDFBundle,
)

OPERATOR_EMAIL = "kjeong@bhug.ac.kr"


def _profile() -> ProfessorProfile:
    """테스트용 ProfessorProfile (v0.1.0 test_confirm_gate.py 와 동일 구조)."""
    return ProfessorProfile.model_validate(
        yaml.safe_load(
            """
profile_kind: operator
profile_name: alpha-prof
sender:
  display_name: 알파교수
  email: alpha@example.ac.kr
send_account:
  email: noreply@example.ac.kr
institution:
  university_name: 알파대학교
  department_name: 알파학과
booking:
  google_calendar_url: https://calendar.google.com/calendar/u/0/appointments/abc
gmail_api:
  service_account_subject: noreply@example.ac.kr
  scopes:
    - https://www.googleapis.com/auth/gmail.send
secrets_ref:
  service_account_json_path_env: PAIDEIA_GCP_SA_JSON_PATH_ALPHA
operational_defaults:
  rate_per_minute: 20
  confirm_sample_size: 3
  attachment_max_bytes: 104857600
"""
        )
    )


# 표본 라인에 등장할 (그리고 그 외에는 등장하지 않을) 학생 이름·이메일.
_STUDENT_FIXTURE: list[tuple[str, str, str]] = [
    # (학번, 이름_kr, 이메일)
    ("2021000001", "홍길동", "hong@bhug.ac.kr"),
    ("2021000002", "김철수", "kim@bhug.ac.kr"),
    ("2021000003", "이영희", "lee@bhug.ac.kr"),
    ("2021000004", "박민수", "park@bhug.ac.kr"),
    ("2021000005", "최지원", "choi@bhug.ac.kr"),
]


def _make_drafts(tmp_path: Path, n: int):
    """첫 n 명의 (draft, bundle) 쌍 생성. n ≤ 5."""
    assert n <= len(_STUDENT_FIXTURE), "fixture only covers 5 students"
    drafts = []
    profile = _profile()
    for i, (sid, name_kr, email) in enumerate(_STUDENT_FIXTURE[:n]):
        pdf = tmp_path / f"{sid}_{name_kr}.pdf"
        pdf.write_bytes(b"%PDF-1.4\nfake\n%%EOF\n")
        bundle = StudentPDFBundle(
            student_id=sid,
            name_kr=name_kr,
            pdf_path=pdf,
            pdf_filename=pdf.name,
            pdf_size_bytes=pdf.stat().st_size,
            pdf_sha256=hashlib.sha256(pdf.read_bytes()).hexdigest(),
            body_first_page_text_normalized=f"학번{sid}",
            body_contains_student_id=True,
        )
        entry = EmailMappingEntry(
            student_id=sid,
            email=email,
            source_row_index=i,
            original_timestamp=datetime(2026, 5, 1, 9, 0, 0, tzinfo=timezone.utc),
        )
        draft = build_email_draft(
            profile=profile,
            mapping_entry=entry,
            pdf_bundle=bundle,
            course_name_kr="인체구조와기능",
            course_slug="anatomy",
            semester="2026-1",
            exam_name="중간고사",
            sent_date=date(2026, 5, 1),
            mode=DispatchMode.PRODUCTION,
        )
        drafts.append((draft, bundle))
    return drafts


@pytest.mark.parametrize(
    ("cohort_outside_count", "total_targets", "scenario_id"),
    [
        # §8.4 — self-test + cohort low_score (179 명 좁힘)
        (179, 184, "8.4_cohort_low_score"),
        # §8.5 — self-test + cohort all (좁힘 없음, 전체 184 narrow 후 첫 5)
        (0, 5, "8.5_cohort_all"),
    ],
)
def test_self_test_gate_output(
    tmp_path: Path,
    cohort_outside_count: int,
    total_targets: int,
    scenario_id: str,
) -> None:
    """self-test 모드 stdout 의 강조 라인·카운트·표본 prefix·표본 suffix 단언.

    contracts/confirm_gate_output.md §4·§8.4·§8.5 의 *byte-level* 라인 형식을
    재현한다. T018 (self-test 분기 구현) 의 RED 단계 — confirm_first_n body 가
    v0.1.0 출력만 emit 하는 동안 본 테스트는 FAIL.
    """
    sendable_count = 5
    # invariant: sendable + skip(0) + outside == total
    assert sendable_count + 0 + cohort_outside_count == total_targets, (
        f"fixture invariant violated for scenario {scenario_id}"
    )

    drafts = _make_drafts(tmp_path, 3)  # 표본은 첫 3 명만
    summary = PreSendSummary(
        sendable_count=sendable_count,
        idempotent_skipped_sids=[],
        cohort_outside_count=cohort_outside_count,
        total_targets=total_targets,
        is_self_test=True,
        operator_email=OPERATOR_EMAIL,
    )

    stdin = io.StringIO("yes\n")
    stdout = io.StringIO()
    confirm_first_n(
        drafts,
        sample_size=3,
        summary=summary,
        stdin=stdin,
        stdout=stdout,
    )
    text = stdout.getvalue()
    lines = text.splitlines()

    # ── 1. 헤더 + 강조 라인 2 줄 (정확한 텍스트, 최상단 3 줄) ────────────
    assert len(lines) >= 3, (
        f"[{scenario_id}] stdout 라인 수 부족: got {len(lines)} lines\n"
        f"--- stdout ---\n{text}\n--- end ---"
    )
    assert lines[0] == "[immersio email] 확인 게이트", (
        f"[{scenario_id}] line 0 mismatch: {lines[0]!r}"
    )
    assert lines[1] == (
        "*** 주의: 현재 본인 테스트(SELF-TEST) 모드입니다. "
        "학생 메일함 도달 0건. ***"
    ), (
        f"[{scenario_id}] line 1 (강조 라인 1) mismatch: {lines[1]!r}"
    )
    assert lines[2] == f"*** 본인({OPERATOR_EMAIL}) 메일함으로만 발송됩니다. ***", (
        f"[{scenario_id}] line 2 (강조 라인 2) mismatch: {lines[2]!r}"
    )

    # ── 2. 카운트 줄 — 3 버킷, idempotent skip 카운트 *없음* ──────────────
    expected_count_line = (
        f"  본인 발송 예정: {sendable_count}건 / "
        f"코호트 범위 밖: {cohort_outside_count}건 / "
        f"합계: {total_targets}건"
    )
    assert expected_count_line in lines, (
        f"[{scenario_id}] 카운트 줄 부재.\n"
        f"  expected: {expected_count_line!r}\n"
        f"  actual lines:\n" + "\n".join(f"    {ln!r}" for ln in lines)
    )

    # idempotent skip 의 production 키워드는 *어디에도* 나타나면 안 됨.
    assert "이미 발송됨(skip)" not in text, (
        f"[{scenario_id}] self-test 모드에 production idempotent skip 키워드 노출:\n"
        f"--- stdout ---\n{text}\n--- end ---"
    )
    assert "이미 발송된 첫" not in text, (
        f"[{scenario_id}] self-test 모드에 production skip 명단 줄 노출:\n"
        f"--- stdout ---\n{text}\n--- end ---"
    )

    # ── 3. 표본 prefix — "(수신자=본인)" 표시 ──────────────────────────
    expected_sample_prefix = "첫 3 건 표본 (수신자=본인):"
    assert expected_sample_prefix in lines, (
        f"[{scenario_id}] 표본 prefix 줄 부재.\n"
        f"  expected: {expected_sample_prefix!r}\n"
        f"  actual lines:\n" + "\n".join(f"    {ln!r}" for ln in lines)
    )

    # ── 4. 표본 학번 행 — 각 행 끝에 "(수신자=<operator_email>)" ──────────
    operator_suffix = f"(수신자={OPERATOR_EMAIL})"
    for sid, name_kr, email in _STUDENT_FIXTURE[:3]:
        # 해당 학번의 표본 행을 찾는다.
        matching = [ln for ln in lines if f"학번={sid}" in ln]
        assert len(matching) == 1, (
            f"[{scenario_id}] 학번 {sid} 의 표본 행 검색 실패: "
            f"matched {len(matching)} lines (expected 1)\n"
            f"  actual lines:\n" + "\n".join(f"    {ln!r}" for ln in lines)
        )
        row = matching[0]
        assert row.endswith(operator_suffix), (
            f"[{scenario_id}] 학번 {sid} 행이 {operator_suffix!r} 로 끝나지 않음:\n"
            f"  row: {row!r}"
        )
        # 표본 라인은 학생 이름·이메일을 포함 (v0.1.0 그대로).
        assert f"이름={name_kr}" in row, (
            f"[{scenario_id}] 학번 {sid} 행에 이름={name_kr} 누락: {row!r}"
        )
        assert f"이메일={email}" in row, (
            f"[{scenario_id}] 학번 {sid} 행에 이메일={email} 누락: {row!r}"
        )

    # ── 5. PII invariant (FR-C04c) — 학생 이름·이메일은 표본 라인에만 ────
    # 표본 행 (학번=... 이름=... 이메일=... 으로 시작) 이외의 라인에
    # 학생 이름·이메일이 0 건 노출되어야 한다.
    non_sample_lines = [ln for ln in lines if "학번=" not in ln]
    for _sid, name_kr, email in _STUDENT_FIXTURE[:3]:
        for ln in non_sample_lines:
            assert name_kr not in ln, (
                f"[{scenario_id}] FR-C04c 위반 — 표본 외 라인에 학생 이름 노출:\n"
                f"  name: {name_kr!r}\n  line: {ln!r}"
            )
            assert email not in ln, (
                f"[{scenario_id}] FR-C04c 위반 — 표본 외 라인에 학생 이메일 노출:\n"
                f"  email: {email!r}\n  line: {ln!r}"
            )
