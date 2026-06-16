"""Integration test — manifest ``outputs.*`` path dry-run/send 분기 (T010, v0.1.1 RED).

Covers FR-C03d · X-3 · contracts/dry_run_outputs.md §3.

Invariants under test (v0.1.1):

1. dry-run 모드의 manifest:
   - ``outputs.dispatch_log_path`` 는 ``메일_발송로그_dryrun.csv`` (절대경로)
   - ``outputs.report_md_path``    는 ``메일_발송보고서_dryrun.md`` (절대경로)

2. ``--send`` 모드의 manifest:
   - ``outputs.dispatch_log_path`` 는 ``메일_발송로그.csv`` (접미사 없음, 절대경로)
   - ``outputs.report_md_path``    는 ``메일_발송보고서.md`` (접미사 없음, 절대경로)

3. (FR-C06b 보강) 두 manifest 모두 동일한 ``EmailManifest`` pydantic 스키마로
   파싱 — ``outputs`` 객체 구조 자체는 v0.1.0 과 무변경, *값* 만 mode 별로 분기.

Expected state on v0.1.0 code: SEND 시나리오는 PASS (v0.1.0 가 이미 접미사
없는 path 를 쓰고 있음). DRY-RUN 시나리오는 FAIL — v0.1.0 의 dry-run 도
manifest 의 ``dispatch_log_path``/``report_md_path`` 를 접미사 없는 send-mode
path 로 기록하기 때문 (실제 dry-run csv/md 파일 위치와 manifest 가 가리키는
path 가 불일치).

T015 가 manifest path branching 을 구현하여 GREEN 으로 전환.
"""

from __future__ import annotations

import argparse
import io
import json
from pathlib import Path

import responses
from immersio.email.pipeline import run_email_dispatch
from paideia_shared.schemas import DispatchStatus
from paideia_shared.schemas.email_dispatch_manifest import EmailManifest

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _dry_run_args() -> argparse.Namespace:
    """Standard dry-run args (matches sibling test_dry_run_csv_separation.py)."""
    return argparse.Namespace(
        profile="alpha-prof",
        semester="2026-1",
        course="anatomy",
        exam_name="중간고사",
        sent_date="2026-05-01",
        send=False,  # dry-run
        self_test=None,
        retry_failed=False,
        retry_skipped=False,
        rate_per_min=None,
        cohort="all",
        confirm_sample=None,
        bronze_csv=None,
        gold_pdf_dir=None,
        silver_master=None,
        silver_student_metrics=None,
        quiet=False,
        verbose=False,
    )


def _send_args() -> argparse.Namespace:
    """Standard send args (matches sibling test_send_184_e2e.py)."""
    args = argparse.Namespace(
        profile="alpha-prof",
        semester="2026-1",
        course="anatomy",
        exam_name="중간고사",
        sent_date="2026-05-01",
        send=True,
        self_test=None,
        retry_failed=False,
        retry_skipped=False,
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


class _AlwaysSucceeds:
    """Stub Gmail dispatcher — always returns SUCCESS, no HTTPS calls."""

    captured: list = []

    def __init__(self, profile, **kwargs):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return None

    def send_one(self, draft, *, pdf_bytes):
        from immersio.email.sender import SendResult

        type(self).captured.append(draft)
        return SendResult(
            status=DispatchStatus.SUCCESS,
            error_kind="",
            error_detail="",
            gmail_server_message_id=f"id-{draft.student_id}",
        )


def _load_manifest(gold_dir: Path) -> EmailManifest:
    """Load + schema-validate the manifest JSON.

    FR-C06b: schema (``EmailManifest``) is unchanged between dry-run and send;
    only the *values* under ``outputs.*`` differ. Re-validating via
    ``model_validate_json`` proves the schema invariant.
    """
    manifest_path = gold_dir / "manifest_email.json"
    assert manifest_path.is_file(), f"manifest_email.json missing at {manifest_path}"
    return EmailManifest.model_validate_json(manifest_path.read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# Scenario A — dry-run manifest 의 outputs.* 는 ``_dryrun`` 접미사 path
# ---------------------------------------------------------------------------


@responses.activate
def test_dry_run_manifest_outputs_have_dryrun_suffix(email_fixture) -> None:
    """FR-C03d (dry-run): manifest outputs.* paths end with ``_dryrun`` suffix.

    실 산출 파일 (``메일_발송로그_dryrun.csv`` / ``메일_발송보고서_dryrun.md``)
    의 path 를 manifest 에 기록해야 — manifest 가 실제 파일을 가리켜야 audit
    도구가 일관성 있게 따라갈 수 있음.
    """
    rc = run_email_dispatch(_dry_run_args())
    assert rc == 0

    manifest = _load_manifest(email_fixture["gold_email_dir"])

    # NB: manifest.mode is the DispatchMode (production/test, FR-D09), NOT a
    # dry-run flag. The dry-run-ness lives in the outputs.* path suffix and in
    # the per-row dry_run rows. We assert dry-run via the counts (>=1 dry_run
    # row) and via the path suffix below.
    assert manifest.counts.dry_run >= 1, (
        f"expected ≥1 dry_run row in manifest counts after dry-run "
        f"invocation; got counts.dry_run={manifest.counts.dry_run}"
    )

    dispatch_log_path = manifest.outputs.dispatch_log_path
    report_md_path = manifest.outputs.report_md_path

    # Absolute path 단언.
    assert Path(dispatch_log_path).is_absolute(), (
        f"manifest outputs.dispatch_log_path is not absolute: {dispatch_log_path!r}"
    )
    assert Path(report_md_path).is_absolute(), (
        f"manifest outputs.report_md_path is not absolute: {report_md_path!r}"
    )

    # FR-C03d: dry-run → ``_dryrun`` 접미사.
    assert dispatch_log_path.endswith("메일_발송로그_dryrun.csv"), (
        f"FR-C03d violated: dry-run manifest outputs.dispatch_log_path "
        f"must end with ``메일_발송로그_dryrun.csv`` (got {dispatch_log_path!r})"
    )
    assert report_md_path.endswith("메일_발송보고서_dryrun.md"), (
        f"FR-C03d violated: dry-run manifest outputs.report_md_path "
        f"must end with ``메일_발송보고서_dryrun.md`` (got {report_md_path!r})"
    )

    # Reinforce: dry-run manifest must NOT point at the send-mode paths.
    assert not dispatch_log_path.endswith("/메일_발송로그.csv"), (
        f"dry-run manifest outputs.dispatch_log_path points at the send-mode "
        f"csv ({dispatch_log_path!r}) — FR-C03d violated"
    )
    assert not report_md_path.endswith("/메일_발송보고서.md"), (
        f"dry-run manifest outputs.report_md_path points at the send-mode "
        f"md ({report_md_path!r}) — FR-C03d violated"
    )

    # SC-003 echo: dry-run made no Gmail HTTPS calls.
    assert len(responses.calls) == 0


# ---------------------------------------------------------------------------
# Scenario B — send manifest 의 outputs.* 는 접미사 없는 path
# ---------------------------------------------------------------------------


def test_send_manifest_outputs_have_no_suffix(email_fixture, monkeypatch) -> None:
    """FR-C03d (send): manifest outputs.* paths have NO ``_dryrun`` suffix.

    Send 모드는 v0.1.0 그대로 — manifest 가 접미사 없는 production path 를
    가리켜야 함.
    """
    _AlwaysSucceeds.captured = []
    monkeypatch.setattr("immersio.email.sender.GmailAPIDispatcher", _AlwaysSucceeds)

    rc = run_email_dispatch(_send_args())
    assert rc == 0

    manifest = _load_manifest(email_fixture["gold_email_dir"])

    dispatch_log_path = manifest.outputs.dispatch_log_path
    report_md_path = manifest.outputs.report_md_path

    # Absolute path 단언.
    assert Path(dispatch_log_path).is_absolute(), (
        f"manifest outputs.dispatch_log_path is not absolute: {dispatch_log_path!r}"
    )
    assert Path(report_md_path).is_absolute(), (
        f"manifest outputs.report_md_path is not absolute: {report_md_path!r}"
    )

    # FR-C03d: send → 접미사 없음.
    assert dispatch_log_path.endswith("메일_발송로그.csv"), (
        f"FR-C03d violated: send-mode manifest outputs.dispatch_log_path "
        f"must end with ``메일_발송로그.csv`` (got {dispatch_log_path!r})"
    )
    assert report_md_path.endswith("메일_발송보고서.md"), (
        f"FR-C03d violated: send-mode manifest outputs.report_md_path "
        f"must end with ``메일_발송보고서.md`` (got {report_md_path!r})"
    )

    # Reinforce: send-mode manifest must NOT carry the ``_dryrun`` suffix.
    assert "_dryrun" not in dispatch_log_path, (
        f"send-mode manifest outputs.dispatch_log_path carries ``_dryrun`` "
        f"suffix ({dispatch_log_path!r}) — FR-C03d violated"
    )
    assert "_dryrun" not in report_md_path, (
        f"send-mode manifest outputs.report_md_path carries ``_dryrun`` "
        f"suffix ({report_md_path!r}) — FR-C03d violated"
    )


# ---------------------------------------------------------------------------
# Scenario C — schema invariant (FR-C06b)
# ---------------------------------------------------------------------------


def test_dry_run_and_send_manifests_share_same_schema(email_fixture, monkeypatch) -> None:
    """FR-C06b: dry-run + send manifests parse via the *same* EmailManifest schema.

    `_load_manifest` already calls ``EmailManifest.model_validate_json`` which
    rejects extra/missing fields (``extra='forbid'``). Both runs must validate
    cleanly under the unchanged v0.1.0 schema — only the *values* differ.
    """
    # --- dry-run leg ---
    rc = run_email_dispatch(_dry_run_args())
    assert rc == 0
    dry_manifest = _load_manifest(email_fixture["gold_email_dir"])

    # Snapshot the raw JSON for set-of-keys comparison (extra='forbid' would
    # already block schema drift, but we also compare top-level + nested keys
    # explicitly so a drift is reported clearly).
    dry_raw = json.loads(
        (email_fixture["gold_email_dir"] / "manifest_email.json").read_text(encoding="utf-8")
    )

    # --- send leg (overwrites manifest_email.json) ---
    _AlwaysSucceeds.captured = []
    monkeypatch.setattr("immersio.email.sender.GmailAPIDispatcher", _AlwaysSucceeds)
    rc = run_email_dispatch(_send_args())
    assert rc == 0
    send_manifest = _load_manifest(email_fixture["gold_email_dir"])

    send_raw = json.loads(
        (email_fixture["gold_email_dir"] / "manifest_email.json").read_text(encoding="utf-8")
    )

    # Top-level key sets are identical (FR-C06b — schema unchanged).
    assert set(dry_raw.keys()) == set(send_raw.keys()), (
        f"FR-C06b violated: dry-run vs send manifest top-level key drift "
        f"(dry only: {set(dry_raw.keys()) - set(send_raw.keys())}; "
        f"send only: {set(send_raw.keys()) - set(dry_raw.keys())})"
    )

    # outputs sub-object key sets identical.
    assert set(dry_raw["outputs"].keys()) == set(send_raw["outputs"].keys()), (
        f"FR-C06b violated: outputs sub-object key drift "
        f"(dry only: "
        f"{set(dry_raw['outputs'].keys()) - set(send_raw['outputs'].keys())}; "
        f"send only: "
        f"{set(send_raw['outputs'].keys()) - set(dry_raw['outputs'].keys())})"
    )

    # Both must parse via the EmailManifest schema (sanity — already
    # validated inside _load_manifest, but a second explicit assert keeps the
    # contract intent loud).
    assert isinstance(dry_manifest, EmailManifest)
    assert isinstance(send_manifest, EmailManifest)
