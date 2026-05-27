"""production gate count + 학번 명단 confirm_gate stdout 단언 (T022 — spec 007 immersio/email-v0.1.1).

FR-C04a / FR-C04b / FR-C04c — production 모드 (``is_self_test=False``)
PreSendSummary 를 ``confirm_first_n`` 에 전달했을 때:

1. 4-bucket 카운트 줄 (정확한 텍스트, contracts/confirm_gate_output.md §3 기준).
2. 학번 명단 줄 (``idempotent_skipped_count > 0`` 일 때만 출력, 3건 cap).
3. 명단 라인 학번 ASC 정렬·쉼표+공백 구분.
4. PII invariant (FR-C04c) — 학생 이름/이메일은 표본 라인에만 (다른 라인 0건).
5. self-test 강조 키워드 (``*** 주의:``, ``*** 본인``, ``(수신자=본인)``) 0건.

contracts/confirm_gate_output.md §8.1·§8.2·§8.3 의 4 시나리오 매트릭스
(skip 0건 → 명단 미출력, skip 5건 → 3건 cap, skip 2건 → cap 미작동,
skip 3건 → cap 경계) 를 parametrize.

본 테스트는 T023 (production 분기 구현) 의 RED 단계 — 현재
``confirm_first_n`` body 는 ``summary is not None and not summary.is_self_test``
케이스에서 v0.1.0 backward-compat fallthrough 만 emit 하므로 *반드시 FAIL*
해야 한다.
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


def _profile() -> ProfessorProfile:
    """테스트용 ProfessorProfile (test_confirm_gate_self_test.py 와 동일 구조)."""
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
    # ALLOW_HARDCODING: SC-005 PII-leak invariant fixture — synthetic but
    # intentionally real-shape so leak-detection assertions exercise the
    # production-shape masking path.
    ("2021000001", "홍길동", "hong@bhug.ac.kr"),  # ALLOW_HARDCODING: SC-005 fixture
    ("2021000002", "김철수", "kim@bhug.ac.kr"),  # ALLOW_HARDCODING: SC-005 fixture
    ("2021000003", "이영희", "lee@bhug.ac.kr"),  # ALLOW_HARDCODING: SC-005 fixture
]


def _make_drafts(tmp_path: Path, n: int):
    """첫 n 명의 (draft, bundle) 쌍 생성. n ≤ len(_STUDENT_FIXTURE)."""
    assert n <= len(_STUDENT_FIXTURE), (
        f"fixture only covers {len(_STUDENT_FIXTURE)} students"
    )
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


# Parametrize the 4 scenarios from contracts/confirm_gate_output.md §8.1·§8.2·§8.3
# plus the cap boundary at skip=3.
@pytest.mark.parametrize(
    (
        "scenario_id",
        "sendable_count",
        "idempotent_skipped_sids",
        "cohort_outside_count",
        "total_targets",
        "expected_sid_line_present",
        "expected_sids_in_line",
    ),
    [
        # (a) §8.1 — skip 0건 → 명단 줄 미출력
        (
            "8.1_skip0_no_list_line",
            184,
            [],
            0,
            184,
            False,
            [],
        ),
        # (b) §8.2 — skip 5건 → 명단 줄 3건 cap (학번 ASC 의 첫 3건만)
        (
            "8.2_skip5_cap3",
            89,
            [
                "0000000001",
                "0000000002",
                "0000000003",
                "0000000004",
                "0000000005",
            ],
            90,
            184,
            True,
            ["0000000001", "0000000002", "0000000003"],
        ),
        # (c) §8.3 — skip 2건 → 명단 줄 2건 (cap 미작동, 1~3 range)
        (
            "8.3_skip2_no_cap",
            92,
            ["0000000010", "0000000020"],
            90,
            184,
            True,
            ["0000000010", "0000000020"],
        ),
        # (d) cap 경계 — skip 3건 → 명단 줄 3건 (cap 작동 직전)
        (
            "skip3_cap_boundary",
            91,
            ["0000000100", "0000000200", "0000000300"],
            90,
            184,
            True,
            ["0000000100", "0000000200", "0000000300"],
        ),
    ],
)
def test_production_gate_count_and_skip_list(
    tmp_path: Path,
    scenario_id: str,
    sendable_count: int,
    idempotent_skipped_sids: list[str],
    cohort_outside_count: int,
    total_targets: int,
    expected_sid_line_present: bool,
    expected_sids_in_line: list[str],
) -> None:
    """production 모드 stdout 의 카운트 줄·학번 명단 줄·PII invariant 단언.

    contracts/confirm_gate_output.md §3·§8.1·§8.2·§8.3 의 *byte-level* 라인
    형식을 재현한다. T023 (production 분기 구현) 의 RED 단계 — confirm_first_n
    body 가 v0.1.0 backward-compat fallthrough 만 emit 하는 동안 본 테스트는
    FAIL.
    """
    # ── 0. fixture 사전 invariant (PreSendSummary validator 가 강제하지만 명시) ─
    assert (
        sendable_count + len(idempotent_skipped_sids) + cohort_outside_count
        == total_targets
    ), (
        f"[{scenario_id}] fixture bucket sum invariant violated: "
        f"sendable({sendable_count}) + skip({len(idempotent_skipped_sids)}) "
        f"+ outside({cohort_outside_count}) != total({total_targets})"
    )
    assert idempotent_skipped_sids == sorted(idempotent_skipped_sids), (
        f"[{scenario_id}] fixture skip ids must be ASC sorted"
    )

    drafts = _make_drafts(tmp_path, 3)  # 표본은 첫 3 명만
    summary = PreSendSummary(
        sendable_count=sendable_count,
        idempotent_skipped_sids=idempotent_skipped_sids,
        cohort_outside_count=cohort_outside_count,
        total_targets=total_targets,
        is_self_test=False,
        operator_email=None,
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

    # ── 1. 헤더 줄 ────────────────────────────────────────────────────
    assert "[immersio email] 확인 게이트" in lines, (
        f"[{scenario_id}] 헤더 줄 부재.\n"
        f"--- stdout ---\n{text}\n--- end ---"
    )

    # ── 2. 4-bucket 카운트 줄 — 정확한 텍스트 ─────────────────────────
    expected_count_line = (
        f"  발송 예정: {sendable_count}건 / "
        f"이미 발송됨(skip): {len(idempotent_skipped_sids)}건 / "
        f"코호트 범위 밖: {cohort_outside_count}건 / "
        f"합계: {total_targets}건"
    )
    assert expected_count_line in lines, (
        f"[{scenario_id}] 카운트 줄 부재.\n"
        f"  expected: {expected_count_line!r}\n"
        f"  actual lines:\n" + "\n".join(f"    {ln!r}" for ln in lines)
    )

    # ── 3. 학번 명단 줄 — skip 카운트별 분기 ──────────────────────────
    if expected_sid_line_present:
        # 형식: "  이미 발송된 첫 3 학번: sid1, sid2, sid3"
        expected_sid_line = (
            "  이미 발송된 첫 3 학번: " + ", ".join(expected_sids_in_line)
        )
        assert expected_sid_line in lines, (
            f"[{scenario_id}] 학번 명단 줄 부재.\n"
            f"  expected: {expected_sid_line!r}\n"
            f"  actual lines:\n" + "\n".join(f"    {ln!r}" for ln in lines)
        )
        # 5건 cap 시 학번 0000000004·0000000005 는 학번 라인에 들어가면 안 됨
        # (단, 라인 전체 검사 — 표본 라인 에도 안 들어가야 하지만 표본은
        # _STUDENT_FIXTURE 의 2021000001~2021000003 이므로 자연히 부재).  # ALLOW_HARDCODING: comment refers to SC-005 fixture IDs
        if scenario_id == "8.2_skip5_cap3":
            assert "0000000004" not in expected_sid_line
            assert "0000000005" not in expected_sid_line
            # 더 강한 단언 — 명단 줄을 lines 에서 직접 찾아 cap 검증.
            matching = [ln for ln in lines if "이미 발송된 첫" in ln]
            assert len(matching) == 1, (
                f"[{scenario_id}] 학번 명단 줄이 0건 또는 2건 이상: "
                f"{len(matching)}\n  matched: {matching!r}"
            )
            assert "0000000004" not in matching[0], (
                f"[{scenario_id}] cap 위반 — 학번 4번째가 명단 줄에 노출:\n"
                f"  line: {matching[0]!r}"
            )
            assert "0000000005" not in matching[0], (
                f"[{scenario_id}] cap 위반 — 학번 5번째가 명단 줄에 노출:\n"
                f"  line: {matching[0]!r}"
            )
    else:
        # skip 0건 — 명단 줄이 *어떤 형식으로도* 나타나면 안 됨 (§3 + FR-C04b).
        assert "이미 발송된 첫" not in text, (
            f"[{scenario_id}] skip 0건임에도 학번 명단 줄 노출:\n"
            f"--- stdout ---\n{text}\n--- end ---"
        )

    # ── 4. self-test 키워드 0건 (production 모드 단언) ────────────────
    assert "*** 주의:" not in text, (
        f"[{scenario_id}] production 모드에 self-test 강조 키워드 노출:\n"
        f"--- stdout ---\n{text}\n--- end ---"
    )
    assert "*** 본인" not in text, (
        f"[{scenario_id}] production 모드에 self-test 강조 키워드 노출:\n"
        f"--- stdout ---\n{text}\n--- end ---"
    )
    assert "(수신자=본인)" not in text, (
        f"[{scenario_id}] production 모드에 self-test 표본 prefix 노출:\n"
        f"--- stdout ---\n{text}\n--- end ---"
    )

    # ── 5. 표본 prefix 줄 — v0.1.0 형식 "첫 N 건 표본:" (production) ────
    sample_n = min(3, len(drafts))
    expected_sample_prefix = f"첫 {sample_n} 건 표본:"
    assert expected_sample_prefix in lines, (
        f"[{scenario_id}] 표본 prefix 줄 부재.\n"
        f"  expected: {expected_sample_prefix!r}\n"
        f"  actual lines:\n" + "\n".join(f"    {ln!r}" for ln in lines)
    )

    # ── 6. PII invariant (FR-C04c) — 표본 외 라인에 학생 이름·이메일 0건 ──
    # 표본 행 ("  학번=... 이름=... 이메일=... pdf=...") 이외의 라인에
    # 학생 이름·이메일이 0 건 노출되어야 한다. 카운트 줄·학번 명단 줄·
    # 확인 안내 줄은 학번만 (또는 0) 노출 (contracts/confirm_gate_output.md §5).
    non_sample_lines = [ln for ln in lines if "학번=" not in ln]
    for _sid, name_kr, email in _STUDENT_FIXTURE:
        for ln in non_sample_lines:
            assert name_kr not in ln, (
                f"[{scenario_id}] FR-C04c 위반 — 표본 외 라인에 학생 이름 노출:\n"
                f"  name: {name_kr!r}\n  line: {ln!r}"
            )
            assert email not in ln, (
                f"[{scenario_id}] FR-C04c 위반 — 표본 외 라인에 학생 이메일 노출:\n"
                f"  email: {email!r}\n  line: {ln!r}"
            )
