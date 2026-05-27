"""cleanup-log e2e 4 시나리오 — T026 (RED).

본 모듈은 v0.1.1 신규 명령 ``immersio email-cleanup-log`` 의 end-to-end 동작을
검증한다. 단위 검증 (T025) 과 달리 본 파일은 *부수 효과 invariant* 와 *CLI 표면*
을 단언한다:

- (a) 실 모드 정상 완료 — 백업 파일 sha256 == 원본 sha256 (FR-C05b),
  새 csv 에 ``--keep`` status 행만 남음 (atomic replace),
  stdout 분포 보고가 한글 라벨 (``성공(success)``, ``본인-테스트(test_dummy)``,
  ``제거(removed)``) 을 포함 (FR-C04f · 계약 §4.1),
  임시 파일 (``*.tmp-*``) 잔존 없음.

- (b) 실 모드 도중 lock 충돌 — 별도 process 가 ``.dispatch.lock`` 을
  ``LOCK_EX`` 로 보유 중일 때 cleanup_log 호출 → ``DispatchLockError`` raise
  (CLI 핸들러는 exit 7 으로 매핑). 백업 미생성, csv 무변경 (FR-C05d).

- (c) dry-run 모드는 lock 미시도 — 위 (b) 와 동일하게 lock 을 외부에서
  보유 중이어도 ``--dry-run`` 은 정상 완료 (FR-C05e). csv 무변경.

- (d) nested subcommand ``immersio email cleanup-log ...`` → argparse 가
  unknown subcommand 로 거부 (FR-C05a). T029 가 ``email-cleanup-log`` 를
  *top-level* helper 로 등록 (``email-init-test-fixtures`` 와 동일 패턴) 하므로
  ``email`` 서브파서 아래에 ``cleanup-log`` 는 존재하지 않아야 함.

테스트 인터페이스 가정 (T028 implementer 가 align 해야 할 사항)
-----------------------------------------------------------------
``immersio.email.cleanup.cleanup_log`` 시그너처는 T025 와 동일하게 가정::

    def cleanup_log(
        log_csv_path: Path,
        keep_statuses: list[str],
        *,
        dry_run: bool = False,
        stdout: IO[str] | None = None,
        stderr: IO[str] | None = None,
    ) -> int:

lock 파일은 ``log_csv_path.parent / ".dispatch.lock"`` 로 가정 (계약 §6 ·
research.md R4 · spec data-model.md §10). T028 이 다른 경로를 택하면 본
테스트의 ``lock_path`` 계산만 조정한다.

RED 상태
--------
T026 작성 시점 ``immersio.email.cleanup`` 모듈은 존재하지 않으며,
``email-cleanup-log`` 서브파서도 등록 전이다. 시나리오 (a)·(b)·(c) 는
fixture 안의 deferred import 에서 ``ModuleNotFoundError`` 로 FAIL, 시나리오
(d) 는 subprocess invocation 자체는 가능하나 *현재 정상 사양 위반* (즉
nested ``email cleanup-log`` 가 argparse 에 의해 거부되어야 하는데 v0.1.0 의
``email`` 서브파서는 nested ``cleanup-log`` 인자를 받을 수 없으므로 이미 비-0
exit 가 발생) → 시나리오 (d) 는 GREEN 일 가능성도 있음. 본 테스트는 *현재
상태의 행위* 와 *T029 이후의 행위* 를 모두 한 단언으로 검증 (argparse 거부).
"""

from __future__ import annotations

import contextlib
import csv
import fcntl
import hashlib
import io
import os
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from immersio.email.log import append_dispatch_log_rows
from paideia_shared.schemas import (
    CohortLabel,
    DispatchLogRow,
    DispatchMode,
    DispatchStatus,
)

KST = timezone(timedelta(hours=9))


# ---------------------------------------------------------------------------
# Deferred import — module exists only after T028.
# ---------------------------------------------------------------------------


@pytest.fixture
def cleanup_log_fn():
    """Return the ``cleanup_log`` callable; fail at fixture-resolution time."""
    from immersio.email.cleanup import cleanup_log  # noqa: F401

    return cleanup_log


@pytest.fixture
def dispatch_lock_error_cls():
    """Return the ``DispatchLockError`` exception class.

    Imported lazily because the cleanup module's lock-handling code path
    only exists post-T028. ``DispatchLockError`` itself lives in
    ``immersio.email.log`` (v0.1.0) and is *re-used* by cleanup-log per
    research.md R4. Importing it eagerly is fine here, but we keep the
    pattern consistent with the other fixture.
    """
    from immersio.email.log import DispatchLockError

    return DispatchLockError


# ---------------------------------------------------------------------------
# Helpers — DispatchLogRow factory + csv state snapshot.
# ---------------------------------------------------------------------------


def _row(
    sid: str,
    *,
    status: DispatchStatus = DispatchStatus.SUCCESS,
    minute: int = 0,
    exam_name: str = "중간고사_진단",
) -> DispatchLogRow:
    return DispatchLogRow(
        student_id=sid,
        name_kr="홍길동",
        email="ok@example.com",
        pdf_filename=f"{sid}_홍길동.pdf",
        pdf_sha256="a" * 64,
        attempt_at_kst=datetime(2026, 5, 1, 12, minute, 0, tzinfo=KST),
        mode=DispatchMode.PRODUCTION,
        status=status,
        smtp_message_id="<deterministic@example.ac.kr>",
        error_kind="",
        error_detail="",
        exam_name=exam_name,
        cohort=CohortLabel.ALL,
    )


def _sha256_of(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _read_statuses(csv_path: Path) -> list[str]:
    """Return the status column values of every data row in the csv."""
    with csv_path.open(encoding="utf-8", newline="") as fh:
        reader = csv.DictReader(fh)
        return [row["status"] for row in reader]


def _no_lock_or_backup_artifacts(csv_path: Path) -> None:
    """Assert that no lock or .bak-* / .tmp-* sibling files exist next to csv."""
    parent = csv_path.parent
    # No backup files
    bak_files = list(parent.glob(f"{csv_path.name}.bak-*"))
    assert not bak_files, (
        f"FR-C05d violation: backup file(s) created during lock-conflict: "
        f"{bak_files}"
    )
    # No temp files
    tmp_files = list(parent.glob(f"{csv_path.name}.tmp-*"))
    assert not tmp_files, (
        f"atomic-replace violation: temp file(s) leaked: {tmp_files}"
    )


# ---------------------------------------------------------------------------
# (a) Real-mode normal completion.
# ---------------------------------------------------------------------------


def test_real_mode_normal_completion(
    tmp_path: Path, cleanup_log_fn
) -> None:
    """실 모드 정상 — 백업 sha256 == 원본 sha256, atomic replace, 한글 분포 보고."""
    log = tmp_path / "메일_발송로그.csv"
    # 4 rows: 2 success, 1 test_dummy, 1 dry_run, 1 skipped  → keep {success, test_dummy}
    append_dispatch_log_rows(
        log,
        [
            _row("1234567001", status=DispatchStatus.SUCCESS),
            _row("1234567002", status=DispatchStatus.SUCCESS, minute=1),
            _row("1234567003", status=DispatchStatus.TEST_DUMMY, minute=2),
            _row("1234567004", status=DispatchStatus.DRY_RUN, minute=3),
            _row("1234567005", status=DispatchStatus.SKIPPED, minute=4),
        ],
    )
    sha_before = _sha256_of(log)
    rows_before = _read_statuses(log)
    assert len(rows_before) == 5, "fixture must have 5 rows pre-cleanup"

    stdout = io.StringIO()
    stderr = io.StringIO()
    result = cleanup_log_fn(
        log,
        ["success", "test_dummy"],
        dry_run=False,
        stdout=stdout,
        stderr=stderr,
    )

    # Normal exit
    assert result in (0, None), (
        f"실 모드 정상 완료 시 return 0 (또는 None) 기대, got {result!r}"
    )

    # Exactly one backup file with the `*.bak-<unix_ts>` pattern.
    bak_files = list(log.parent.glob(f"{log.name}.bak-*"))
    assert len(bak_files) == 1, (
        f"백업 파일 1개 기대 (*.bak-<unix_ts>), got: {bak_files}"
    )
    bak = bak_files[0]
    # The suffix after `.bak-` must look like a unix timestamp (int).
    suffix = bak.name.rsplit(".bak-", 1)[-1]
    assert suffix.isdigit(), (
        f"백업 suffix 가 unix_ts (정수) 가 아님: {bak.name!r}"
    )

    # FR-C05b — backup sha256 == pre-cleanup csv sha256.
    assert _sha256_of(bak) == sha_before, (
        "FR-C05b: 백업 파일 sha256 가 정리 직전 csv sha256 과 일치해야 함"
    )

    # Atomic replace — original csv now contains ONLY {success, test_dummy} rows.
    statuses_after = _read_statuses(log)
    assert set(statuses_after) <= {"success", "test_dummy"}, (
        f"정리 후 csv 에 보존 status 외 행이 남음: {statuses_after}"
    )
    assert statuses_after.count("success") == 2, (
        f"success 행 2개 보존 기대, got {statuses_after}"
    )
    assert statuses_after.count("test_dummy") == 1, (
        f"test_dummy 행 1개 보존 기대, got {statuses_after}"
    )

    # sha256 changed (atomic replace performed).
    assert _sha256_of(log) != sha_before, (
        "원본 csv 가 atomic replace 로 새 내용으로 교체되어야 함"
    )

    # No `*.tmp-*` leftover (atomic replace cleaned up).
    tmp_files = list(log.parent.glob(f"{log.name}.tmp-*"))
    assert not tmp_files, (
        f"atomic replace 후 임시 파일 (*.tmp-*) 잔존 — 정리 누락: {tmp_files}"
    )

    # stdout 분포 보고 (§4.1) 한글 라벨 검증.
    out = stdout.getvalue()
    # 보존된 status 라벨
    assert "성공(success)" in out, (
        f"stdout 에 '성공(success)' 라벨 없음 (§4.1 / FR-C04f): {out!r}"
    )
    assert "본인-테스트(test_dummy)" in out, (
        f"stdout 에 '본인-테스트(test_dummy)' 라벨 없음: {out!r}"
    )
    # 제거 라벨 (status 가 아니라 작업 결과 — 분리 라벨)
    assert "제거(removed)" in out, (
        f"stdout 에 '제거(removed)' 분리 라벨 없음: {out!r}"
    )
    # 건수 — 정확한 카운트 (2 success, 1 test_dummy, 2 removed)
    assert "성공(success): 2건" in out, (
        f"stdout '성공(success): 2건' 카운트 없음: {out!r}"
    )
    assert "본인-테스트(test_dummy): 1건" in out, (
        f"stdout '본인-테스트(test_dummy): 1건' 카운트 없음: {out!r}"
    )
    assert "제거(removed): 2건" in out, (
        f"stdout '제거(removed): 2건' 카운트 없음: {out!r}"
    )


# ---------------------------------------------------------------------------
# (b) Lock conflict — external holder on `.dispatch.lock` blocks real mode.
# ---------------------------------------------------------------------------


def test_real_mode_lock_conflict_raises(
    tmp_path: Path, cleanup_log_fn, dispatch_lock_error_cls
) -> None:
    """실 모드 도중 다른 process 가 lock 보유 → ``DispatchLockError`` (exit 7).

    Test mechanism: 본 process 안에서 lock 파일 fd 를 직접 ``LOCK_EX | LOCK_NB``
    로 잡고 cleanup_log 를 호출. cleanup_log 의 동일 ``LOCK_EX | LOCK_NB`` 시도가
    ``EWOULDBLOCK`` 로 실패 → ``DispatchLockError`` raise. 백업/임시 파일 미생성,
    csv 무변경 단언.

    참고: POSIX flock 은 *process 단위* 가 아니라 *fd 단위* 잠금이지만, 같은
    process 안에서도 별도 fd 가 ``LOCK_EX`` 를 시도하면 첫 fd 의 잠금이 우선이며
    ``EWOULDBLOCK`` 가 발생한다. 따라서 별도 process 가 필요 없으며 테스트가
    더 결정적이다.
    """
    log = tmp_path / "메일_발송로그.csv"
    append_dispatch_log_rows(
        log,
        [
            _row("1234567001", status=DispatchStatus.SUCCESS),
            _row("1234567002", status=DispatchStatus.TEST_DUMMY, minute=1),
        ],
    )
    sha_before = _sha256_of(log)
    lock_path = log.parent / ".dispatch.lock"

    # Pre-acquire the lock from an external fd (simulates another process).
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(lock_path, os.O_RDWR | os.O_CREAT, 0o644)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)

        stderr = io.StringIO()
        with pytest.raises(dispatch_lock_error_cls):
            cleanup_log_fn(
                log,
                ["success", "test_dummy"],
                dry_run=False,
                stderr=stderr,
            )

        # No side effects: no backup, no temp file, csv untouched.
        _no_lock_or_backup_artifacts(log)
        assert _sha256_of(log) == sha_before, (
            "lock 실패 시 csv 가 변경됨 (atomic replace 도달 안 해야)"
        )
    finally:
        with contextlib.suppress(OSError):
            fcntl.flock(fd, fcntl.LOCK_UN)
        os.close(fd)


# ---------------------------------------------------------------------------
# (c) Dry-run does NOT attempt the lock — concurrent holder is OK.
# ---------------------------------------------------------------------------


def test_dry_run_does_not_attempt_lock(
    tmp_path: Path, cleanup_log_fn
) -> None:
    """``--dry-run`` 은 lock 미시도 → 다른 명령이 lock 을 보유 중이어도 정상 실행.

    (FR-C05e · 계약 §6/§7) dry-run 은 csv 미터치이므로 lock 을 잡지 않아야 한다.
    외부에서 ``.dispatch.lock`` 을 ``LOCK_EX`` 로 보유 중일 때도 dry-run 은 정상
    완료해야 함.
    """
    log = tmp_path / "메일_발송로그.csv"
    append_dispatch_log_rows(
        log,
        [
            _row("1234567001", status=DispatchStatus.SUCCESS),
            _row("1234567002", status=DispatchStatus.DRY_RUN, minute=1),
        ],
    )
    sha_before = _sha256_of(log)
    lock_path = log.parent / ".dispatch.lock"

    lock_path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(lock_path, os.O_RDWR | os.O_CREAT, 0o644)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)

        stdout = io.StringIO()
        stderr = io.StringIO()
        result = cleanup_log_fn(
            log,
            ["success"],
            dry_run=True,
            stdout=stdout,
            stderr=stderr,
        )

        # Dry-run normal exit even with lock held externally.
        assert result in (0, None), (
            f"dry-run 정상 종료 시 return 0 (또는 None) 기대, got {result!r}"
        )

        # csv unchanged (dry-run never writes).
        assert _sha256_of(log) == sha_before, (
            "dry-run 인데 csv 가 변경됨"
        )

        # No backup or temp artifacts (dry-run does not create them).
        _no_lock_or_backup_artifacts(log)

        # stdout sanity — at minimum mentions dry-run/미리보기 mode.
        out = stdout.getvalue()
        assert "dry-run" in out or "미리보기" in out, (
            f"dry-run stdout 에 mode 안내 없음: {out!r}"
        )
    finally:
        with contextlib.suppress(OSError):
            fcntl.flock(fd, fcntl.LOCK_UN)
        os.close(fd)


# ---------------------------------------------------------------------------
# (d) Nested subcommand `immersio email cleanup-log ...` → unknown subcommand.
# ---------------------------------------------------------------------------


def test_nested_subcommand_rejected(tmp_path: Path) -> None:
    """``immersio email cleanup-log ...`` 는 argparse 가 거부해야 함 (FR-C05a).

    T029 가 ``email-cleanup-log`` 를 *top-level* helper (sibling of
    ``email``) 로 등록하므로, ``email`` 서브파서 아래에 ``cleanup-log`` 가
    *존재하지 않아야* 한다. 본 테스트는 ``python -m immersio.cli.main email
    cleanup-log ...`` 를 subprocess 로 실행하여 비-0 exit 와 argparse 의 거부
    메시지 (stderr) 를 단언한다.

    참고: v0.1.0 의 ``email`` 서브파서는 ``--profile`` 등의 인자만 받으므로
    위치 인자 ``cleanup-log`` 는 argparse 에 의해 unknown argument 로 거부된다.
    T029 이후에도 동일 거부가 유지되어야 함 (top-level 패턴 유지).
    """
    # Invoke as a module so we use the in-tree code (avoids requiring the
    # ``immersio`` console script to be installed in test envs).
    completed = subprocess.run(  # noqa: S603
        [  # noqa: S607
            sys.executable,
            "-m",
            "immersio.cli.main",
            "email",
            "cleanup-log",
            "--semester",
            "2026-1",
            "--course",
            "anatomy",
            "--keep",
            "success",
        ],
        check=False,
        capture_output=True,
        text=True,
        timeout=60,
    )

    # argparse usage error → exit 2 by convention; we accept any non-zero
    # exit since some error paths may map to 1.
    assert completed.returncode != 0, (
        f"nested subcommand 가 거부되지 않음 (exit 0). FR-C05a 위반.\n"
        f"stdout:\n{completed.stdout}\nstderr:\n{completed.stderr}"
    )
    # argparse error message lives on stderr. Common phrasings:
    # "unrecognized arguments", "invalid choice", "unknown".
    err = completed.stderr.lower()
    assert any(
        kw in err
        for kw in (
            "unrecognized",
            "unknown",
            "invalid choice",
            "usage:",
            "error:",
        )
    ), (
        f"nested subcommand 거부 시 stderr 에 argparse 거부 메시지 기대, "
        f"got stderr={completed.stderr!r}"
    )
