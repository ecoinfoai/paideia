"""Cross-cutting integration test — dry-run + self-test 결합 edge case (T035).

Covers spec.md Edge Cases line: "dry-run + self-test 동시 사용 — dry-run 이 우선,
본인 발송도 발생하지 않음. eml preview 파일만 생성, 발송 로그 미터치."

Scenario: ``--cohort low_score --self-test 5`` 옵션으로 dry-run 실행 (``--send``
미지정). dry-run 이 우선이므로 학생/본인 어디로도 실제 발송은 발생하지 않으며,
산출은 dry-run 모드 산출 파일 + eml preview 만이어야 한다. self-test 의 의미
(`본인 메일함으로만 발송`) 는 preview 파일의 To 헤더가 운영자 본인을 가리키는 형태로
반영된다.

다섯 가지 단언:

(a) ``메일_발송로그.csv`` (send-mode log) — mtime·sha256 무변경 (FR-C03c).
(b) ``메일_발송로그_dryrun.csv`` — 5 행 (status=dry_run) 작성 (FR-C03a).
(c) eml preview 파일 5 건 (``tmp/immersio_email_preview/...``) 생성 — To 헤더가
    운영자 본인 이메일 (self-test 의미).
(d) manifest ``outputs.dispatch_log_path`` 가 ``_dryrun`` 접미사 path (FR-C03d).
(e) Gmail API 호출 0건 (``responses.calls`` mock 검증).

Expected state — v0.1.1 implementation (T014/T015/T019) 이 dry-run + self-test
조합을 허용하고 preview 의 To 헤더를 operator 로 redirect 하면 GREEN. 본 테스트는
spec edge case 의 source-of-truth 회귀 fixture.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
from pathlib import Path

import pytest
import responses

from .conftest import write_student_metrics_parquet
from immersio.email.pipeline import run_email_dispatch


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _args() -> argparse.Namespace:
    """Dry-run + self-test 5 + cohort low_score args.

    `--send` 미지정 (``send=False``) — dry-run 이 우선. ``self_test=5`` 는
    self-test 의도 표명 (preview To 헤더 redirect). ``cohort='low_score'`` 는
    cohort 좁힘 (저득점 학생만 대상).
    """
    args = argparse.Namespace(
        profile="alpha-prof",
        semester="2026-1",
        course="anatomy",
        exam_name="중간고사",
        sent_date="2026-05-01",
        send=False,  # dry-run wins
        self_test=5,  # self-test intent (preview To = operator)
        retry_failed=False,
        retry_skipped=False,
        rate_per_min=None,
        cohort="low_score",
        confirm_sample=None,
        bronze_csv=None,
        gold_pdf_dir=None,
        silver_master=None,
        silver_student_metrics=None,
        quiet=False,
        verbose=False,
        created_at_utc=None,
    )
    # confirm_gate may run in self-test path even under dry-run — provide
    # an affirmative stdin so the gate proceeds. Harmless if gate is
    # skipped under dry-run.
    args._stdin = io.StringIO("yes\n")
    return args


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


# ---------------------------------------------------------------------------
# Main combined test — 5 assertions in one scenario
# ---------------------------------------------------------------------------


@pytest.mark.xfail(
    reason=(
        "v0.1.1 pipeline.py (line ~113) still rejects ``--self-test`` without "
        "``--send`` with rc=2; T014/T015/T019 only branched dry-run csv/md/"
        "manifest paths and added PreSendSummary self-test fields, but did "
        "NOT lift the early rejection of the dry-run + self-test combo. "
        "Spec.md Edge Cases requires dry-run to win and produce preview "
        "files with operator-To headers; that branch is pending a follow-up "
        "(allow self_test under dry-run + propagate operator override into "
        "preview composition). Strict=False: this xfail unlocks when the "
        "pipeline grows the dry-run + self-test path; until then the test "
        "stays the source-of-truth fixture for the spec edge case."
    ),
    strict=False,
)
@responses.activate
def test_dry_run_plus_self_test_combined(email_fixture) -> None:
    """spec.md Edge Cases: dry-run + self-test → dry-run 우선, 5 단언 GREEN."""
    sids = [s[0] for s in email_fixture["students"]]
    operator_email = "alpha@example.ac.kr"  # ALLOW_HARDCODING: matches conftest make_profile_dir sender.email
    silver_dir = (
        email_fixture["base"] / "data" / "silver" / "immersio" / "2026-1-anatomy"
    )
    # All 5 students below the 60 threshold → cohort=low_score yields 5 students.
    # self_test=5 matches → preview 5 건 / dry-run csv 5 행.
    write_student_metrics_parquet(
        silver_dir,
        [
            (sids[0], "홍길동", 35.0),
            (sids[1], "김갑동", 40.0),
            (sids[2], "이순신", 45.0),
            (sids[3], "유관순", 50.0),
            (sids[4], "안중근", 55.0),
        ],
    )

    gold_dir = email_fixture["gold_email_dir"]
    send_log = gold_dir / "메일_발송로그.csv"
    dryrun_log = gold_dir / "메일_발송로그_dryrun.csv"
    manifest_path = gold_dir / "manifest_email.json"

    # Pre-condition: capture baseline state for send-mode log.
    # The send-mode csv does not exist before any --send run. Under
    # spec FR-C03c, dry-run must leave it untouched — assert it stays
    # absent (the strictest form of "mtime·sha256 unchanged" when the
    # baseline is "file does not exist").
    pre_send_log_exists = send_log.exists()
    pre_send_log_sig: tuple[int, str] | None = None
    if pre_send_log_exists:
        pre_send_log_sig = (
            send_log.stat().st_mtime_ns,
            _sha256(send_log),
        )

    rc = run_email_dispatch(_args())
    assert rc == 0, (
        f"dry-run + self-test should exit 0 (dry-run wins, no actual send "
        f"attempted); got rc={rc}"
    )

    # ------------------------------------------------------------------
    # (a) Send-mode csv mtime·sha256 무변경 (FR-C03c)
    # ------------------------------------------------------------------
    post_send_log_exists = send_log.exists()
    assert post_send_log_exists == pre_send_log_exists, (
        f"(a) dry-run + self-test must not create/delete the send-mode "
        f"csv. pre_exists={pre_send_log_exists} post_exists={post_send_log_exists}"
    )
    if pre_send_log_sig is not None:
        post_sig = (send_log.stat().st_mtime_ns, _sha256(send_log))
        assert post_sig == pre_send_log_sig, (
            f"(a) ``메일_발송로그.csv`` mtime·sha256 changed "
            f"(pre={pre_send_log_sig} post={post_sig}) — FR-C03c violated"
        )

    # ------------------------------------------------------------------
    # (b) ``메일_발송로그_dryrun.csv`` 에 5 행 (status=dry_run) 작성
    # ------------------------------------------------------------------
    assert dryrun_log.is_file(), (
        f"(b) ``메일_발송로그_dryrun.csv`` not created — FR-C03a violated"
    )
    dryrun_text = dryrun_log.read_text(encoding="utf-8")
    dryrun_lines = dryrun_text.splitlines()
    # header + 5 data rows
    assert len(dryrun_lines) == 1 + 5, (
        f"(b) dryrun csv has {len(dryrun_lines)} lines; expected 6 "
        f"(header + 5 dry_run rows for cohort=low_score)"
    )
    assert dryrun_text.count(",dry_run,") == 5, (
        f"(b) expected 5 ``dry_run`` rows in dryrun csv; got "
        f"{dryrun_text.count(',dry_run,')}"
    )

    # ------------------------------------------------------------------
    # (c) eml preview 5 건 생성, To 헤더 = 운영자 본인
    # ------------------------------------------------------------------
    preview_dir = email_fixture["preview_dir"]
    eml_files = sorted(preview_dir.glob("*.eml"))
    assert len(eml_files) == 5, (
        f"(c) expected 5 .eml preview files under {preview_dir}; got "
        f"{len(eml_files)} ({[f.name for f in eml_files]})"
    )
    for eml in eml_files:
        body = eml.read_text(encoding="utf-8", errors="replace")
        # RFC 5322 To header — first matching ``To:`` line in the headers.
        to_line: str | None = None
        for line in body.splitlines():
            if line.startswith("To:"):
                to_line = line
                break
        assert to_line is not None, (
            f"(c) eml file {eml.name} has no ``To:`` header"
        )
        assert operator_email in to_line, (
            f"(c) eml {eml.name} To header must be operator ({operator_email!r}); "
            f"got {to_line!r} — self-test meaning violated under dry-run"
        )

    # Student emails MUST NOT appear in any preview To header.
    student_emails = {s[2] for s in email_fixture["students"]}
    for eml in eml_files:
        body = eml.read_text(encoding="utf-8", errors="replace")
        to_line = next(
            (line for line in body.splitlines() if line.startswith("To:")),
            "",
        )
        for stu_email in student_emails:
            assert stu_email not in to_line, (
                f"(c) eml {eml.name} To header leaked student email "
                f"{stu_email!r} — self-test redirect failed"
            )

    # ------------------------------------------------------------------
    # (d) manifest outputs.dispatch_log_path 가 ``_dryrun`` 접미사 path
    # ------------------------------------------------------------------
    assert manifest_path.is_file(), (
        f"(d) manifest_email.json not created at {manifest_path}"
    )
    manifest_raw = json.loads(manifest_path.read_text(encoding="utf-8"))
    dispatch_log_path = manifest_raw["outputs"]["dispatch_log_path"]
    assert dispatch_log_path.endswith("메일_발송로그_dryrun.csv"), (
        f"(d) manifest outputs.dispatch_log_path must end with "
        f"``메일_발송로그_dryrun.csv`` (got {dispatch_log_path!r}) — "
        f"FR-C03d violated under dry-run + self-test"
    )
    assert "_dryrun" in dispatch_log_path, (
        f"(d) manifest dispatch_log_path missing ``_dryrun`` suffix "
        f"({dispatch_log_path!r})"
    )

    # ------------------------------------------------------------------
    # (e) Gmail API HTTPS 호출 0 건 (responses mock 검증)
    # ------------------------------------------------------------------
    assert len(responses.calls) == 0, (
        f"(e) dry-run + self-test must NOT call Gmail API; got "
        f"{len(responses.calls)} HTTPS call(s) — SC-003 violated"
    )
