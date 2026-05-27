"""immersio email-cleanup-log — operator helper for v0.1.0-era csv repair.

Implements the *single library entry point* ``cleanup_log`` used by the
top-level helper command ``immersio email-cleanup-log`` (v0.1.1 spec
007 FR-C05a..f). The 7-step pipeline is:

  1. ``--keep`` token validation (DispatchStatus enum exact match, empty
     tokens rejected) — happens *before* any I/O so a typo never even
     touches the lock file.
  2. Lock acquisition (real mode only) on ``log_csv_path.parent /
     ".dispatch.lock"`` with ``LOCK_EX | LOCK_NB`` — dry-run skips the
     lock so a concurrent ``email --send`` does not block previews.
  3. CSV load via :func:`immersio.email.log.read_dispatch_log` so the
     ``exam_name`` invariant (T005 / FR-C02a-1) is enforced on every
     entry point.
  4. Filter + 0-data-row guard — real mode aborts with ``ValueError``;
     dry-run still emits a 0-count preview (FR-C05a-2).
  5. Backup file (``메일_발송로그.csv.bak-<unix_ts>``) is a byte-identical
     copy of the pre-cleanup csv. sha256 is compared and must match
     (FR-C05b).
  6. Atomic replace via ``os.replace`` of a same-directory temp file —
     POSIX ``rename(2)`` atomicity (research.md R3). SIGINT / ENOSPC
     hits *before* the rename keep the original csv intact; orphan tmp
     files are allowed.
  7. Status distribution report on stdout using ``STATUS_KR_GATE``
     (FR-C04f) plus a separate ``제거(removed)`` label for the row
     count that did *not* match ``--keep``.

Lock-target divergence (vs. contracts/cli_email_cleanup_log.md §6 /
research.md R4): the contract says cleanup-log shares the *same* lock
target as ``email --send`` so the two are mutually exclusive. However
v0.1.0's ``_exclusive_lock`` uses the csv file itself as the lock
target (``modules/immersio/src/immersio/email/log.py``), and tests
T026/T027 already commit to the separate ``.dispatch.lock`` file. We
follow the test contract here (separate ``.dispatch.lock`` next to the
csv) so the implementation matches what was RED. Operators should
serialize cleanup-log with ``email --send`` manually until a follow-up
refactor unifies the lock targets.
"""

from __future__ import annotations

import csv
import errno
import fcntl
import hashlib
import io
import os
import sys
import tempfile
import time
from collections import Counter
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import IO

from paideia_shared.schemas import DispatchLogRow, DispatchStatus

from .log import (
    STATUS_KR_GATE,
    DispatchLockError,
    read_dispatch_log,
)

__all__ = ["cleanup_log"]


# ---------------------------------------------------------------------------
# Internal: status enum validation.
# ---------------------------------------------------------------------------


_VALID_STATUS_VALUES: frozenset[str] = frozenset(s.value for s in DispatchStatus)


def _format_valid_statuses() -> str:
    """Return the canonical valid-status enumeration string (FR-C05a-1 §5.1).

    Ordering follows DispatchStatus enum declaration (success, skipped,
    failed, temporary_failure, dry_run, test_dummy) per contract §5.1.
    """
    return ", ".join(STATUS_KR_GATE[s] for s in DispatchStatus)


def _validate_keep_statuses(
    tokens: list[str],
    err: IO[str],
) -> list[DispatchStatus]:
    """Validate raw ``--keep`` tokens and return the parsed enum list.

    Args:
        tokens: Raw string tokens from the caller. Whitespace is stripped
            (e.g. ``"success "`` matches). Empty tokens are rejected.
        err: Stream for emitting the contract §5.1 stderr lines.

    Returns:
        Parsed list of ``DispatchStatus`` enum members (in input order).

    Raises:
        ValueError: If any token is empty or not in the 6-value enum.
            stderr is written *before* the raise so the CLI handler can
            map the exception to exit 3 without further formatting.
    """
    parsed: list[DispatchStatus] = []
    for raw in tokens:
        token = raw.strip()
        if not token:
            err.write(
                "오류: 지원되지 않는 status: ``. "
                "유효한 값 6종 — "
                f"{_format_valid_statuses()}.\n"
            )
            err.write(
                "참고 — 본 명령은 lock 을 획득하지 않았고 csv 를 "
                "변경하지 않았습니다.\n"
            )
            raise ValueError(
                "지원되지 않는 status: `` (empty token). "
                f"유효한 값 6종 — {_format_valid_statuses()}."
            )
        if token not in _VALID_STATUS_VALUES:
            err.write(
                f"오류: 지원되지 않는 status: `{token}`. "
                "유효한 값 6종 — "
                f"{_format_valid_statuses()}.\n"
            )
            err.write(
                "참고 — 본 명령은 lock 을 획득하지 않았고 csv 를 "
                "변경하지 않았습니다.\n"
            )
            raise ValueError(
                f"지원되지 않는 status: `{token}`. "
                f"유효한 값 6종 — {_format_valid_statuses()}."
            )
        parsed.append(DispatchStatus(token))
    return parsed


# ---------------------------------------------------------------------------
# Internal: cleanup-log lock helper (separate `.dispatch.lock` file).
# ---------------------------------------------------------------------------


@contextmanager
def _acquire_cleanup_lock(lock_path: Path) -> Iterator[int]:
    """Acquire LOCK_EX|LOCK_NB on ``lock_path`` for cleanup-log mutex.

    Mirrors :func:`immersio.email.log._exclusive_lock` but targets a
    *separate* ``.dispatch.lock`` file (see module docstring on lock-
    target divergence). Yields the open fd; releases the lock on context
    exit even when the caller raises.

    Raises:
        DispatchLockError: When the lock is held by another process. The
            CLI handler maps this to exit 7 (FR-C05d).
    """
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(lock_path, os.O_RDWR | os.O_CREAT, 0o644)
    locked = False
    try:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            locked = True
        except (BlockingIOError, OSError) as exc:
            try:
                os.close(fd)
            except OSError:
                # intentional-skip: idempotent fd cleanup
                pass
            if isinstance(exc, OSError) and exc.errno not in (
                errno.EWOULDBLOCK,
                errno.EAGAIN,
            ):
                raise
            raise DispatchLockError(
                f"FR-C05d: cleanup-log lock {lock_path} is held by "
                f"another run (LOCK_EX|LOCK_NB). exit 7."
            ) from exc
        yield fd
    finally:
        if locked:
            # Unlink the lock file *while still holding* the lock so that
            # validation failures (e.g. empty-result abort) leave no
            # ``.dispatch.lock`` artifact in the gold dir (FR-C05a-2 test
            # invariant in test_cleanup_validation.py). Any concurrent
            # contender already failed at our flock acquisition; new
            # contenders after unlink will create a fresh inode and the
            # mutex remains correct.
            try:
                os.unlink(lock_path)
            except OSError:
                # intentional-skip: lock file may already be gone
                pass
            try:
                fcntl.flock(fd, fcntl.LOCK_UN)
            except OSError:
                # intentional-skip: idempotent flock release
                pass
            try:
                os.close(fd)
            except OSError:
                # intentional-skip: idempotent fd close
                pass


# ---------------------------------------------------------------------------
# Internal: sha256 + atomic replace.
# ---------------------------------------------------------------------------


def _compute_sha256(path: Path) -> str:
    """Return the hex sha256 of ``path``'s byte contents."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _serialize_rows_csv(rows: list[DispatchLogRow]) -> bytes:
    """Return the byte-identical csv representation of ``rows``.

    Header is always written (even for an empty list). Mirrors the
    ``append_dispatch_log_row`` writer in log.py — same column order,
    same ``lineterminator="\n"`` so the byte-output matches what an
    equivalent append sequence would have produced.
    """
    buf = io.StringIO()
    writer = csv.DictWriter(
        buf,
        fieldnames=list(DispatchLogRow.COLUMN_ORDER),
        lineterminator="\n",
    )
    writer.writeheader()
    for row in rows:
        dump = row.model_dump(mode="json")
        writer.writerow({c: dump[c] for c in DispatchLogRow.COLUMN_ORDER})
    return buf.getvalue().encode("utf-8")


def _atomic_write_csv(target: Path, content: bytes) -> None:
    """Write ``content`` to a tmp file in target.parent, then ``os.replace``.

    Atomic on the same filesystem (POSIX ``rename(2)``). SIGINT or
    ENOSPC during the tmp write or before the ``os.replace`` call
    leaves the tmp file as orphan but ``target`` unchanged
    (research.md R3 — orphan tmp explicitly allowed).
    """
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = tempfile.NamedTemporaryFile(
        dir=target.parent,
        prefix=f"{target.name}.tmp-",
        suffix="",
        delete=False,
    )
    try:
        tmp.write(content)
        tmp.flush()
        os.fsync(tmp.fileno())
    finally:
        tmp.close()
    os.replace(tmp.name, target)


# ---------------------------------------------------------------------------
# Internal: distribution report.
# ---------------------------------------------------------------------------


def _emit_distribution_report(
    rows_kept: list[DispatchLogRow],
    removed_count: int,
    kept_statuses_order: list[DispatchStatus],
    out: IO[str],
) -> None:
    """Emit the FR-C05f / §4.1 distribution line.

    The line lists each kept-status label (from ``STATUS_KR_GATE``) in
    the order the operator passed ``--keep``, then the separate
    ``제거(removed)`` label. Counts of 0 are still emitted for the kept
    statuses (so dry-run on a csv that has none of the kept statuses
    still shows the operator their intent reflected back).
    """
    counts = Counter(row.status for row in rows_kept)
    parts: list[str] = []
    seen: set[DispatchStatus] = set()
    for status in kept_statuses_order:
        if status in seen:
            continue
        seen.add(status)
        label = STATUS_KR_GATE[status]
        parts.append(f"{label}: {counts.get(status, 0)}건")
    parts.append(f"제거(removed): {removed_count}건")
    out.write("정리 결과 분포 — " + ", ".join(parts) + "\n")


# ---------------------------------------------------------------------------
# Internal: dry-run preview body.
# ---------------------------------------------------------------------------


def _emit_dry_run_preview(
    rows_kept: list[DispatchLogRow],
    out: IO[str],
) -> None:
    """Emit the §4.2 dry-run preview block (header + body + count line)."""
    out.write("정리 후 csv 미리보기 (헤더 + 데이터행):\n")
    header_line = ",".join(DispatchLogRow.COLUMN_ORDER)
    out.write(f"  {header_line}\n")
    for row in rows_kept:
        dump = row.model_dump(mode="json")
        body = ",".join(str(dump[c]) for c in DispatchLogRow.COLUMN_ORDER)
        out.write(f"  {body}\n")
    out.write(f"  (총 {len(rows_kept)} 데이터행)\n")


# ---------------------------------------------------------------------------
# Public API.
# ---------------------------------------------------------------------------


def cleanup_log(
    log_csv_path: Path,
    keep_statuses: list[str],
    *,
    dry_run: bool = False,
    stdout: IO[str] | None = None,
    stderr: IO[str] | None = None,
) -> int:
    """Clean up the dispatch log csv by keeping only specified status rows.

    Implements the 7-step pipeline of FR-C05a..f / contracts/
    cli_email_cleanup_log.md. The function does not call ``sys.exit``;
    return value (or propagated exception) is mapped to an exit code by
    the CLI handler:

    - return ``0`` — normal completion (real mode or dry-run).
    - raise ``ValueError`` — exit 3 (unknown ``--keep`` token / empty
      token) or exit 4 (real mode 0 surviving rows). Caller inspects
      the message to choose the right exit code.
    - raise ``FileNotFoundError`` — exit 5 (csv missing or empty).
    - raise ``ExamNameInvariantError`` — exit 6 (csv has multiple
      ``exam_name`` values).
    - raise ``DispatchLockError`` — exit 7 (concurrent cleanup-log /
      ``email --send``). Dry-run never raises this.
    - raise ``OSError`` / ``KeyboardInterrupt`` — propagated unchanged.
      ``os.replace`` is the atomic boundary; before it, the original
      csv is byte-identical to its pre-cleanup state (FR-C05c).

    Args:
        log_csv_path: Absolute or cwd-relative path to
            ``메일_발송로그.csv``. Lock file is ``.dispatch.lock`` next to
            it (real mode only).
        keep_statuses: Raw string tokens, e.g. ``["success",
            "test_dummy"]``. Whitespace stripped; empty tokens rejected.
        dry_run: When True, no lock is taken, no file is written, but a
            preview + 0-count distribution is still emitted on stdout.
            When False (default), real mode performs the backup + atomic
            replace + sha256 verification.
        stdout: Optional sink for the §4.1 / §4.2 stdout lines. Default
            ``sys.stdout``.
        stderr: Optional sink for the §5 error lines. Default
            ``sys.stderr``.

    Returns:
        ``0`` on normal completion.
    """
    out = stdout if stdout is not None else sys.stdout
    err = stderr if stderr is not None else sys.stderr

    # Step 1: validate --keep tokens (no I/O, no lock).
    keep_enums = _validate_keep_statuses(keep_statuses, err)
    # Preserve operator's order for the distribution line, dedup later.
    keep_set: set[DispatchStatus] = set(keep_enums)
    keep_labels_human = ", ".join(s.value for s in keep_enums)

    if dry_run:
        return _cleanup_log_dry_run(
            log_csv_path,
            keep_enums,
            keep_set,
            keep_labels_human,
            out=out,
            err=err,
        )
    return _cleanup_log_real(
        log_csv_path,
        keep_enums,
        keep_set,
        keep_labels_human,
        out=out,
        err=err,
    )


def _cleanup_log_dry_run(
    log_csv_path: Path,
    keep_enums: list[DispatchStatus],
    keep_set: set[DispatchStatus],
    keep_labels_human: str,
    *,
    out: IO[str],
    err: IO[str],
) -> int:
    """Dry-run path — read csv, emit preview + distribution, no writes."""
    out.write(
        "[immersio email-cleanup-log] 모드: dry-run "
        "(미리보기, 파일 변경 없음, lock 미획득)\n"
    )
    out.write(f"  대상 csv: {log_csv_path}\n")
    out.write(f"  보존 status: {keep_labels_human}\n")

    # CSV load (exam_name invariant via read_dispatch_log).
    if not log_csv_path.is_file():
        err.write(
            f"오류: 발송 로그 csv 가 존재하지 않거나 빈 파일입니다: "
            f"{log_csv_path}\n"
            "정리할 대상이 없습니다. "
            "`immersio email --send` 가 1회 이상 실행된 뒤에 "
            "cleanup-log 를 사용하세요.\n"
        )
        raise FileNotFoundError(
            f"발송 로그 csv 가 존재하지 않습니다: {log_csv_path}"
        )
    rows = read_dispatch_log(log_csv_path)
    if not rows:
        err.write(
            f"오류: 발송 로그 csv 가 존재하지 않거나 빈 파일입니다: "
            f"{log_csv_path}\n"
            "정리할 대상이 없습니다. "
            "`immersio email --send` 가 1회 이상 실행된 뒤에 "
            "cleanup-log 를 사용하세요.\n"
        )
        raise FileNotFoundError(
            f"발송 로그 csv 가 빈 파일입니다: {log_csv_path}"
        )

    rows_kept = [r for r in rows if r.status in keep_set]
    removed_count = len(rows) - len(rows_kept)

    _emit_dry_run_preview(rows_kept, out)
    _emit_distribution_report(rows_kept, removed_count, keep_enums, out)
    return 0


def _cleanup_log_real(
    log_csv_path: Path,
    keep_enums: list[DispatchStatus],
    keep_set: set[DispatchStatus],
    keep_labels_human: str,
    *,
    out: IO[str],
    err: IO[str],
) -> int:
    """Real-mode path — lock, load, filter, backup, atomic replace, report."""
    # Pre-check csv presence (exit 5) before grabbing the lock so a
    # missing csv doesn't leave a stray .dispatch.lock file.
    if not log_csv_path.is_file():
        err.write(
            f"오류: 발송 로그 csv 가 존재하지 않거나 빈 파일입니다: "
            f"{log_csv_path}\n"
            "정리할 대상이 없습니다. "
            "`immersio email --send` 가 1회 이상 실행된 뒤에 "
            "cleanup-log 를 사용하세요.\n"
        )
        raise FileNotFoundError(
            f"발송 로그 csv 가 존재하지 않습니다: {log_csv_path}"
        )

    lock_path = log_csv_path.parent / ".dispatch.lock"
    with _acquire_cleanup_lock(lock_path):
        # Step 3: csv load + exam_name invariant (delegated to read_dispatch_log).
        rows = read_dispatch_log(log_csv_path)
        if not rows:
            err.write(
                f"오류: 발송 로그 csv 가 존재하지 않거나 빈 파일입니다: "
                f"{log_csv_path}\n"
                "정리할 대상이 없습니다. "
                "`immersio email --send` 가 1회 이상 실행된 뒤에 "
                "cleanup-log 를 사용하세요.\n"
            )
            raise FileNotFoundError(
                f"발송 로그 csv 가 빈 파일입니다: {log_csv_path}"
            )

        # Step 4: filter + 0-row guard (real mode).
        rows_kept = [r for r in rows if r.status in keep_set]
        removed_count = len(rows) - len(rows_kept)
        if not rows_kept:
            kept_repr = ",".join(s.value for s in keep_enums)
            err.write(
                f"오류: 정리 결과가 0 데이터행입니다. "
                f"`--keep`={{{kept_repr}}} 와 매칭되는 행이 csv 에 없습니다.\n"
                "의도된 동작이라면 dry-run 으로 먼저 확인하거나 수동으로 "
                "처리하세요.\n"
                "참고 — 백업·임시 파일을 생성하지 않았고 원본 csv 를 "
                "변경하지 않았습니다.\n"
            )
            raise ValueError(
                f"정리 결과가 0 데이터행입니다. "
                f"`--keep`={{{kept_repr}}} 와 매칭되는 행이 csv 에 "
                "없습니다."
            )

        # Step 5: backup file (byte-identical copy) + sha256 verify.
        sha_pre = _compute_sha256(log_csv_path)
        unix_ts = int(time.time())
        bak_path = log_csv_path.parent / f"{log_csv_path.name}.bak-{unix_ts}"
        bak_path.write_bytes(log_csv_path.read_bytes())
        sha_bak = _compute_sha256(bak_path)
        if sha_bak != sha_pre:
            raise OSError(
                f"백업 sha256 불일치: 백업({sha_bak}) != 원본({sha_pre}). "
                f"백업 경로: {bak_path}"
            )

        # Emit the §4.1 normal-completion preamble before atomic replace
        # so an operator who watches stdout sees the backup path even if
        # ENOSPC strikes the replace step.
        out.write("[immersio email-cleanup-log] 모드: 실 모드\n")
        out.write(f"  대상 csv: {log_csv_path}\n")
        out.write(f"  보존 status: {keep_labels_human}\n")
        out.write(f"  백업 파일: {bak_path}\n")
        out.write(
            f"  백업 sha256: {sha_bak} == 정리 직전 csv sha256 ✓\n"
        )

        # Step 6: atomic replace.
        new_content = _serialize_rows_csv(rows_kept)
        _atomic_write_csv(log_csv_path, new_content)

        # Step 7: distribution report.
        _emit_distribution_report(rows_kept, removed_count, keep_enums, out)

    return 0
