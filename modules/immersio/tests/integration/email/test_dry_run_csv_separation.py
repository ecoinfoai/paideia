"""Integration test — dry-run csv 분리 mtime·sha256 invariant (T009, v0.1.1 RED).

Covers FR-C03a / FR-C03c · contracts/dry_run_outputs.md §2 / §7.

Invariants under test (v0.1.1):

1. ``메일_발송로그.csv`` (send-mode log) — dry-run is *strictly read-only* on
   this path. Pre-seed an arbitrary baseline csv before any dry-run; assert
   its ``mtime_ns`` and ``sha256`` are UNCHANGED across N=3 consecutive
   dry-run invocations.

2. ``메일_발송로그_dryrun.csv`` (dry-run log) — truncate-write. After
   dry-run #1 capture ``sha256``; after dry-run #2 and #3 assert sha256
   unchanged (same fixture + same ``--sent-date`` → byte-identical
   truncate-write).

3. md report mode separation — ``메일_발송보고서.md`` must NOT be created
   by dry-run; ``메일_발송보고서_dryrun.md`` must be created and contain
   dispatch report content.

Note on fixture size: contract calls for "더미 픽스처 184 학생". The shared
``email_fixture`` provisions 5 students (see
``test_send_184_e2e.py`` comment "scales to 30 … same code paths are
equivalent" — the 184 figure is the operational cohort target). 5 students
fully exercise the truncate-write / mtime invariant logic; the per-row
append/truncate code paths under test are identical across N students.

Expected state on v0.1.0 code: ALL THREE assertions FAIL (RED).
- v0.1.0 writes dry-run rows into ``메일_발송로그.csv`` → assertion #1 fails
- v0.1.0 never creates ``메일_발송로그_dryrun.csv`` → assertion #2 fails
- v0.1.0 writes dry-run report into ``메일_발송보고서.md`` → assertion #3 fails

T014/T015 implement the v0.1.1 path branching to make this GREEN.
"""

from __future__ import annotations

import argparse
import hashlib
import os
import time
from pathlib import Path

import pytest
import responses
from immersio.email.pipeline import run_email_dispatch

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _args() -> argparse.Namespace:
    """Standard dry-run args (matches sibling test_dry_run_184_preview.py)."""
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


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _stat_pair(path: Path) -> tuple[int, str]:
    """Return (mtime_ns, sha256) for ``path``."""
    return path.stat().st_mtime_ns, _sha256(path)


# ---------------------------------------------------------------------------
# Test 1 — send-mode log csv mtime + sha256 invariant across N=3 dry-runs
# ---------------------------------------------------------------------------


@responses.activate
def test_dry_run_does_not_touch_send_mode_log_csv(email_fixture) -> None:
    """FR-C03c: dry-run leaves ``메일_발송로그.csv`` mtime·sha256 unchanged.

    Seed a baseline csv (simulating a prior --send run's artefact); run
    dry-run 3 times; assert mtime_ns + sha256 unchanged at each checkpoint.
    """
    gold_dir = email_fixture["gold_email_dir"]
    gold_dir.mkdir(parents=True, exist_ok=True)
    send_log = gold_dir / "메일_발송로그.csv"

    # Pre-condition: seed a baseline csv (mimics a prior --send run).
    # Values are schema-valid per DispatchLogRow: pdf_sha256=hex64,
    # smtp_message_id=RFC 5322 Message-ID, so that pipeline read_dispatch_log
    # does not reject the baseline during the idempotent-skip read.
    baseline_sha256 = "a" * 64
    baseline = (
        "student_id,name_kr,email,pdf_filename,pdf_sha256,attempt_at_kst,"
        "mode,status,smtp_message_id,error_kind,error_detail,exam_name,cohort\n"
        f"9999999999,베이스라인,baseline@example.com,baseline.pdf,"  # ALLOW_HARDCODING: RFC 2606 example domain in csv baseline fixture
        f"{baseline_sha256},2026-04-01T10:00:00+09:00,production,success,"
        "<base-id@example.com>,,,중간고사,all\n"  # ALLOW_HARDCODING: RFC 2606 example domain in message-id fixture
    )
    send_log.write_bytes(baseline.encode("utf-8"))
    pre_mtime, pre_sha = _stat_pair(send_log)

    # Run dry-run N=3 times, capturing (mtime_ns, sha256) after each.
    # The small sleep before each run guarantees that IF the pipeline did
    # touch the file, mtime_ns would advance — making the invariant
    # falsification observable.
    for run_idx in (1, 2, 3):
        time.sleep(0.01)
        rc = run_email_dispatch(_args())
        assert rc == 0, f"dry-run #{run_idx} returned non-zero rc"

        assert send_log.exists(), (
            f"after dry-run #{run_idx}: ``메일_발송로그.csv`` was deleted (should be untouched)"
        )
        post_mtime, post_sha = _stat_pair(send_log)
        assert post_sha == pre_sha, (
            f"after dry-run #{run_idx}: ``메일_발송로그.csv`` sha256 changed "
            f"(pre={pre_sha[:12]}.. post={post_sha[:12]}..) — FR-C03c "
            "violated, dry-run modified the send-mode log"
        )
        assert post_mtime == pre_mtime, (
            f"after dry-run #{run_idx}: ``메일_발송로그.csv`` mtime_ns "
            f"changed (pre={pre_mtime} post={post_mtime}) — FR-C03c "
            "violated, dry-run touched the send-mode log"
        )

    # SC-003 echo: dry-run made no Gmail HTTPS calls.
    assert len(responses.calls) == 0


# ---------------------------------------------------------------------------
# Test 2 — dry-run csv truncate-write is byte-identical across runs
# ---------------------------------------------------------------------------


@responses.activate
def test_dry_run_dryrun_csv_truncate_write_byte_identical(email_fixture) -> None:
    """FR-C03a: dry-run writes ``메일_발송로그_dryrun.csv`` truncate-style.

    Same fixture + same ``--sent-date`` across 3 runs → byte-identical
    csv after each run (truncate, not append).
    """
    gold_dir = email_fixture["gold_email_dir"]
    dryrun_log = gold_dir / "메일_발송로그_dryrun.csv"

    # Run #1 establishes the canonical contents.
    rc = run_email_dispatch(_args())
    assert rc == 0
    assert dryrun_log.is_file(), (
        "after dry-run #1: ``메일_발송로그_dryrun.csv`` not created "
        "(FR-C03a violated — dry-run log should land at *_dryrun.csv path)"
    )
    first_sha = _sha256(dryrun_log)
    first_bytes = dryrun_log.read_bytes()

    # Sanity: header + ≥1 dry_run row.
    text = first_bytes.decode("utf-8")
    lines = text.splitlines()
    assert len(lines) >= 2, (
        f"dryrun csv has only {len(lines)} line(s); expected header + ≥1 dry_run row"
    )
    # Exactly N=5 student rows for the 5-student fixture (cohort=all).
    students = email_fixture["students"]
    assert len(lines) == 1 + len(students), (
        f"dryrun csv has {len(lines)} lines; expected "
        f"{1 + len(students)} (header + {len(students)} students)"
    )
    assert text.count(",dry_run,") == len(students), (
        f"expected {len(students)} ``dry_run`` rows; got {text.count(',dry_run,')}"
    )

    # Runs #2 and #3 must produce byte-identical truncate-write output.
    for run_idx in (2, 3):
        time.sleep(0.01)
        rc = run_email_dispatch(_args())
        assert rc == 0, f"dry-run #{run_idx} returned non-zero rc"
        assert dryrun_log.is_file(), (
            f"after dry-run #{run_idx}: ``메일_발송로그_dryrun.csv`` missing"
        )
        post_sha = _sha256(dryrun_log)
        assert post_sha == first_sha, (
            f"after dry-run #{run_idx}: ``메일_발송로그_dryrun.csv`` sha256 "
            f"changed (first={first_sha[:12]}.. post={post_sha[:12]}..) — "
            "FR-C03a violated: truncate-write should be byte-identical for "
            "identical input"
        )


# ---------------------------------------------------------------------------
# Test 2b — dry-run dispatch log csv is owner-only (DAR-01 / FR-004)
# ---------------------------------------------------------------------------


@pytest.mark.skipif(os.geteuid() == 0, reason="root bypasses chmod 0o600 protection")
@responses.activate
def test_dry_run_dryrun_csv_is_owner_only(email_fixture) -> None:
    """FR-004/SC-002: the dry-run dispatch log carries full DispatchLogRow
    PII (student_id, name_kr, email) and must be owner-only regardless of
    send/dry-run mode or umask. Pre-seed a group/world-readable file so the
    fix must actively tighten it, not merely rely on a fresh create.
    """
    gold_dir = email_fixture["gold_email_dir"]
    gold_dir.mkdir(parents=True, exist_ok=True)
    dryrun_log = gold_dir / "메일_발송로그_dryrun.csv"
    # Pre-seed 0644 so the assert fails unless _write_log_csv fchmods.
    dryrun_log.write_bytes(b"stale\n")
    os.chmod(dryrun_log, 0o644)

    rc = run_email_dispatch(_args())
    assert rc == 0
    assert dryrun_log.is_file()
    mode = dryrun_log.stat().st_mode & 0o777
    assert mode & 0o077 == 0, f"expected owner-only, got {oct(mode)}"
    assert mode == 0o600, oct(mode)


# ---------------------------------------------------------------------------
# Test 3 — md report file mode separation
# ---------------------------------------------------------------------------


@responses.activate
def test_dry_run_md_report_separation(email_fixture) -> None:
    """FR-C03b/c: dry-run writes ``메일_발송보고서_dryrun.md`` only.

    ``메일_발송보고서.md`` (send-mode) must NOT be created.
    ``메일_발송보고서_dryrun.md`` (dry-run) must be created with content.
    """
    gold_dir = email_fixture["gold_email_dir"]
    gold_dir.mkdir(parents=True, exist_ok=True)

    send_report = gold_dir / "메일_발송보고서.md"
    dryrun_report = gold_dir / "메일_발송보고서_dryrun.md"

    # Pre-condition: neither file exists.
    assert not send_report.exists()
    assert not dryrun_report.exists()

    rc = run_email_dispatch(_args())
    assert rc == 0

    # FR-C03c: send-mode md untouched (must not exist).
    assert not send_report.exists(), (
        "after dry-run: ``메일_발송보고서.md`` was created by dry-run — "
        "FR-C03c violated; dry-run must only write to the *_dryrun.md path"
    )

    # FR-C03b: dry-run md created.
    assert dryrun_report.is_file(), (
        "after dry-run: ``메일_발송보고서_dryrun.md`` not created — "
        "FR-C03b violated; dry-run must write the report to the "
        "*_dryrun.md path"
    )
    body = dryrun_report.read_text(encoding="utf-8")
    assert body.strip(), "dryrun report md is empty"
