"""SC-005 PII gate invariant regression test (T030 — spec 007 immersio/email-v0.1.1).

FR-C04c / SC-005 — confirm_gate stdout 의 *모든 출력 라인* (카운트 줄 · 학번 명단
줄 · self-test 강조 라인 · 확인 안내 줄 — 표본 라인 제외) 에서 학생 *이름·이메일*
이 0건 노출되어야 한다는 invariant 를 6 시나리오 매트릭스로 자동 회귀 단언한다.

contracts/confirm_gate_output.md §8 의 6 케이스를 그대로 재현:

    §8.1  production, skip 0건 (명단 줄 미출력)
    §8.2  production, skip 5건 (4건 이상 cap 3)
    §8.3  production, skip 2건 (1~3 range, cap 미작동)
    §8.4  self-test 모드, cohort low_score 결합
    §8.5  self-test 모드, cohort all
    §8.6  v0.1.0 backward-compat (summary=None)

T017 (test_confirm_gate_self_test.py) 와 T022 (test_confirm_gate_summary_count.py)
는 *시나리오별* PII 부재를 단언한다. T030 은 위 단언들을 *6 시나리오 매트릭스*
로 consolidate 하여 SC-005 자동 회귀 테스트로 재사용 가능하게 한다 (contracts
/confirm_gate_output.md §9 + spec.md SC-005).

표본 라인 (학번=... 이름=... 이메일=... pdf=... | 또는 self-test 의 (수신자=...))
은 v0.1.0 그대로 PII 를 포함하므로 본 단언에서 *제외* — `"학번="` substring 으로
필터링.
"""

from __future__ import annotations

import hashlib
import io
import re
from datetime import UTC, date, datetime
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

OPERATOR_EMAIL = "kjeong@bhug.ac.kr"  # ALLOW_HARDCODING: SC-005 leak-test operator fixture (real-domain by design)


def _profile() -> ProfessorProfile:
    """테스트용 ProfessorProfile (T017/T022 와 동일 구조)."""
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
# 본 fixture 는 5명을 정의하지만 표본은 첫 3명만 사용한다 — 표본 외 라인의 PII
# 부재 invariant 는 *전체 5명* 의 이름·이메일에 대해 단언 (잠재적 leak 의 더 강한
# super-set 검증).
_STUDENT_FIXTURE: list[tuple[str, str, str]] = [
    # (학번, 이름_kr, 이메일)
    # ALLOW_HARDCODING: SC-005 PII-leak invariant fixture — synthetic but
    # intentionally real-shape so the leak-detection assertions exercise the
    # production-shape masking path (matches `\b20\d{8}\b` + `@bhug.ac.kr`).
    ("2021000001", "홍길동", "hong@bhug.ac.kr"),  # ALLOW_HARDCODING: SC-005 fixture
    ("2021000002", "김철수", "kim@bhug.ac.kr"),  # ALLOW_HARDCODING: SC-005 fixture
    ("2021000003", "이영희", "lee@bhug.ac.kr"),  # ALLOW_HARDCODING: SC-005 fixture
    ("2021000004", "박민수", "park@bhug.ac.kr"),  # ALLOW_HARDCODING: SC-005 fixture
    ("2021000005", "최지원", "choi@bhug.ac.kr"),  # ALLOW_HARDCODING: SC-005 fixture
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
            original_timestamp=datetime(2026, 5, 1, 9, 0, 0, tzinfo=UTC),
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


def _build_summary(scenario: str) -> PreSendSummary | None:
    """contracts/confirm_gate_output.md §8 의 6 케이스 PreSendSummary 빌더.

    §8.6 는 v0.1.0 backward-compat 이므로 ``None`` 반환.
    """
    if scenario == "8.1_production_skip_0":
        # production, skip 0건 — 명단 줄 미출력
        return PreSendSummary(
            sendable_count=184,
            idempotent_skipped_sids=[],
            cohort_outside_count=0,
            total_targets=184,
            is_self_test=False,
            operator_email=None,
        )
    if scenario == "8.2_production_skip_5_cap":
        # production, skip 5건 — 명단 줄 3건 cap
        return PreSendSummary(
            sendable_count=89,
            idempotent_skipped_sids=[
                "0000000001",
                "0000000002",
                "0000000003",
                "0000000004",
                "0000000005",
            ],
            cohort_outside_count=90,
            total_targets=184,
            is_self_test=False,
            operator_email=None,
        )
    if scenario == "8.3_production_skip_2_no_cap":
        # production, skip 2건 — 1~3 range, cap 미작동
        return PreSendSummary(
            sendable_count=92,
            idempotent_skipped_sids=["0000000010", "0000000020"],
            cohort_outside_count=90,
            total_targets=184,
            is_self_test=False,
            operator_email=None,
        )
    if scenario == "8.4_self_test_low_score":
        # self-test 모드, cohort low_score 결합
        return PreSendSummary(
            sendable_count=5,
            idempotent_skipped_sids=[],
            cohort_outside_count=179,
            total_targets=184,
            is_self_test=True,
            operator_email=OPERATOR_EMAIL,
        )
    if scenario == "8.5_self_test_all":
        # self-test 모드, cohort all (전체 184 narrow 후 첫 5)
        # quickstart §8.5 — sendable=5, outside=179, total=184
        return PreSendSummary(
            sendable_count=5,
            idempotent_skipped_sids=[],
            cohort_outside_count=179,
            total_targets=184,
            is_self_test=True,
            operator_email=OPERATOR_EMAIL,
        )
    if scenario == "8.6_v010_backward_compat":
        # v0.1.0 backward-compat — summary 미전달 (None)
        return None
    raise ValueError(f"unknown scenario: {scenario!r}")


@pytest.mark.parametrize(
    "scenario",
    [
        "8.1_production_skip_0",
        "8.2_production_skip_5_cap",
        "8.3_production_skip_2_no_cap",
        "8.4_self_test_low_score",
        "8.5_self_test_all",
        "8.6_v010_backward_compat",
    ],
)
def test_pii_invariant_across_all_scenarios(
    tmp_path: Path,
    scenario: str,
) -> None:
    """SC-005 회귀 — 6 시나리오 매트릭스 PII gate invariant.

    confirm_first_n 의 stdout 라인 중 *표본 라인 제외* 모든 라인 (헤더 · 강조 라인
    · 카운트 줄 · 학번 명단 줄 · 표본 prefix · 확인 안내 줄) 에 학생 *이름·이메일*
    이 0건 노출되어야 한다 (contracts/confirm_gate_output.md §5 · §8 · §9).

    표본 라인은 v0.1.0 그대로 (학번·이름·이메일·pdf 모두 표시) — 본 invariant 의
    *기대 leak 채널* 이 아니므로 ``"학번="`` substring 으로 필터링.
    """
    summary = _build_summary(scenario)
    drafts = _make_drafts(tmp_path, 3)  # 표본은 첫 3 명만 (sample_size=3)

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

    # ── 0. 헤더 줄 sanity check (실제로 게이트가 출력했는지 확인) ────────────
    assert any("[immersio email] 확인 게이트" in ln for ln in lines), (
        f"[{scenario}] 헤더 줄 부재 — confirm_first_n 가 출력하지 않음?\n"
        f"--- stdout ---\n{text}\n--- end ---"
    )

    # ── 1. 표본 라인 (학번=... 으로 식별) 을 분리 ──────────────────────────
    # 표본 라인은 PII 노출이 의도된 채널 (FR-C04c — 표본은 v0.1.0 그대로). 따라서
    # 본 invariant 대상에서 *제외* 한다. 식별 키 = ``"학번="`` substring.
    non_sample_lines = [ln for ln in lines if "학번=" not in ln]

    # 비-표본 라인이 *적어도 1 줄* 있어야 한다 — 헤더 줄 + 확인 안내 줄은
    # 모든 시나리오에서 항상 출력됨. (8.6 v0.1.0 backward-compat 에서도 헤더 1 +
    # 확인 안내 줄 1 = 최소 2 줄)
    assert len(non_sample_lines) >= 2, (
        f"[{scenario}] 비-표본 라인 수 부족: {len(non_sample_lines)}\n"
        f"--- stdout ---\n{text}\n--- end ---"
    )

    # ── 2. 비-표본 라인의 PII (이름·이메일) 0건 단언 ────────────────────────
    # _STUDENT_FIXTURE 전체 (5명) 의 이름·이메일에 대해 비-표본 라인 1줄씩 검사.
    # 표본은 첫 3명만 들어가지만, *우연한 leak* 도 잡기 위해 전체 5명 검사.
    for sid, name_kr, email in _STUDENT_FIXTURE:
        # 이름 substring leak 검사
        for ln in non_sample_lines:
            assert name_kr not in ln, (
                f"[{scenario}] SC-005 위반 — 비-표본 라인에 학생 이름 노출:\n"
                f"  student_id={sid} name={name_kr!r}\n"
                f"  line: {ln!r}\n"
                f"  --- full stdout ---\n{text}\n  --- end ---"
            )
        # 이메일 substring leak 검사
        for ln in non_sample_lines:
            assert email not in ln, (
                f"[{scenario}] SC-005 위반 — 비-표본 라인에 학생 이메일 노출:\n"
                f"  student_id={sid} email={email!r}\n"
                f"  line: {ln!r}\n"
                f"  --- full stdout ---\n{text}\n  --- end ---"
            )

    # ── 3. 강한 추가 단언 — 이름·이메일 정규식 매칭 0건 ─────────────────────
    # _STUDENT_FIXTURE 의 이름은 한글 3자, 이메일은 ASCII alphanum + "@bhug.ac.kr"
    # 패턴. 비-표본 라인에 이 패턴 *전체 가족* 이 0 건이어야 한다 (장래 fixture
    # 가 확장되어도 PII leak 을 자동 캐치).
    name_re = re.compile(
        "|".join(re.escape(s[1]) for s in _STUDENT_FIXTURE)
    )
    email_re = re.compile(
        "|".join(re.escape(s[2]) for s in _STUDENT_FIXTURE)
    )
    for ln in non_sample_lines:
        m_name = name_re.search(ln)
        assert m_name is None, (
            f"[{scenario}] SC-005 정규식 위반 — 비-표본 라인에 학생 이름 매칭:\n"
            f"  matched: {m_name.group(0)!r}\n  line: {ln!r}"
        )
        m_email = email_re.search(ln)
        assert m_email is None, (
            f"[{scenario}] SC-005 정규식 위반 — 비-표본 라인에 학생 이메일 매칭:\n"
            f"  matched: {m_email.group(0)!r}\n  line: {ln!r}"
        )
