"""Append-only dispatch log + idempotent skip filter (T067).

The dispatch log is the *single source of truth* for "who has been sent
to" — read on every re-run, written one row per send attempt. To prevent
two parallel runs from interleaving rows or missing each other's
writes:

  - ``LOCK_EX | LOCK_NB`` flock on the log path → any concurrent run
    fails fast with ``DispatchLockError`` (caller maps to exit 7).
  - Each row is flushed + ``os.fsync`` so a crashing run leaves at most
    one row partially written; the next read still sees the durable
    prefix.

Secret masking: ``mask_secrets_in_error_detail`` strips App Password
quadruplets, RSA private key blobs, JSON ``"private_key"`` fields, and
the GCP Service Account ``.iam.gserviceaccount.com`` domain pattern  # ALLOW_HARDCODING: docstring meta-mention of masking pattern
from any error_detail string before it lands on disk (FR-G02 / ADR-014).
"""

from __future__ import annotations

import csv
import errno
import fcntl
import os
import re
from contextlib import contextmanager
from enum import StrEnum
from io import StringIO
from pathlib import Path
from typing import Iterator

from paideia_shared.schemas import DispatchLogRow, DispatchStatus


class DispatchLockError(RuntimeError):
    """Raised when the per-run flock cannot be acquired (FR-D02 / R6)."""


class RetryMode(StrEnum):
    """Retry semantics for ``idempotent_skip_filter`` (FR-D03 a/b/c)."""

    DEFAULT = "default"
    RETRY_FAILED = "retry_failed"
    RETRY_SKIPPED = "retry_skipped"


# ---------------------------------------------------------------------------
# Secret-masking patterns (ADR-014).
# ---------------------------------------------------------------------------

_APP_PASSWORD_RE = re.compile(r"\b([a-z]{4})\s+([a-z]{4})\s+([a-z]{4})\s+([a-z]{4})\b")
_RSA_PRIVATE_KEY_RE = re.compile(
    r"-----BEGIN (?:RSA )?PRIVATE KEY-----.*?-----END (?:RSA )?PRIVATE KEY-----",
    re.DOTALL,
)
_JSON_PRIVATE_KEY_RE = re.compile(r'"private_key"\s*:\s*"[^"]+"')
_JSON_PRIVATE_KEY_ID_RE = re.compile(
    r'"private_key_id"\s*:\s*"[a-f0-9]{40}"'
)
_SA_DOMAIN_RE = re.compile(
    r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.iam\.gserviceaccount\.com"
)
_RAW_PEM_BYTES_RE = re.compile(r"BEGIN (?:RSA )?PRIVATE KEY")


def mask_secrets_in_error_detail(text: str) -> str:
    """Strip secret-shaped substrings from an error detail before logging.

    Args:
        text: Free-form error detail string (e.g. from an exception
            ``str(...)``). Length is also truncated to 200 chars at the
            DispatchLogRow validator layer.

    Returns:
        ``text`` with each detected secret pattern replaced by
        ``<redacted>`` and any residual ``BEGIN PRIVATE KEY`` markers
        scrubbed. Empty input returns empty string.
    """
    if not text:
        return ""
    out = text
    out = _APP_PASSWORD_RE.sub("<redacted-app-password>", out)
    out = _RSA_PRIVATE_KEY_RE.sub("<redacted-rsa-private-key>", out)
    out = _JSON_PRIVATE_KEY_RE.sub('"private_key": "<redacted>"', out)
    out = _JSON_PRIVATE_KEY_ID_RE.sub(
        '"private_key_id": "<redacted>"', out
    )
    out = _SA_DOMAIN_RE.sub("<redacted-sa-email>", out)
    # Belt-and-braces: scrub any leftover PEM markers.
    out = _RAW_PEM_BYTES_RE.sub("<redacted-pem>", out)
    return out


# ---------------------------------------------------------------------------
# Append-only writer with flock + fsync.
# ---------------------------------------------------------------------------


@contextmanager
def _exclusive_lock(path: Path) -> Iterator[int]:
    """Acquire LOCK_EX|LOCK_NB on ``path`` (caller's responsibility to close).

    Yields the open fd. Releases the lock on context exit even if the
    caller raised. Raises ``DispatchLockError`` when the lock is held by
    another process (FR-D02 / R6 — concurrent run).
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    # O_RDWR|O_CREAT — file exists or is created with default mode
    fd = os.open(path, os.O_RDWR | os.O_CREAT, 0o644)
    locked = False
    try:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            locked = True
        except (BlockingIOError, OSError) as exc:
            # Close fd before raising — the contextmanager finally
            # block will skip unlock/close since ``locked`` is False
            # and ``fd`` already closed here.
            try:
                os.close(fd)
            except OSError:
                pass
            if isinstance(exc, OSError) and exc.errno not in (
                errno.EWOULDBLOCK,
                errno.EAGAIN,
            ):
                raise
            raise DispatchLockError(
                f"FR-D02: dispatch log {path} is locked by another run "
                f"(LOCK_EX|LOCK_NB). exit 7."
            ) from exc
        yield fd
    finally:
        if locked:
            try:
                fcntl.flock(fd, fcntl.LOCK_UN)
            except OSError:
                pass
            try:
                os.close(fd)
            except OSError:
                pass


def append_dispatch_log_row(log_path: Path, row: DispatchLogRow) -> None:
    """Append one ``DispatchLogRow`` to ``log_path`` durably.

    Args:
        log_path: Absolute or cwd-relative path to ``메일_발송로그.csv``.
            Created with header row on first write.
        row: Validated ``DispatchLogRow`` with masked ``error_detail``.

    Raises:
        DispatchLockError: When another process holds LOCK_EX on the
            same log file. Caller maps to exit 7.

    Side effects:
        Writes one CSV row, flushes Python buffer, and ``os.fsync`` so
        the row hits stable storage before the function returns.
    """
    with _exclusive_lock(log_path) as fd:
        # Determine if header is needed BEFORE opening Python's text
        # wrapper — st_size 0 on first write.
        st = os.fstat(fd)
        is_new = st.st_size == 0

        # Use a fresh fd for text-mode write (we already hold flock on
        # the underlying inode; the second open is fine on POSIX).
        with log_path.open("a", encoding="utf-8", newline="") as text_fh:
            writer = csv.DictWriter(
                text_fh, fieldnames=list(DispatchLogRow.COLUMN_ORDER)
            )
            if is_new:
                writer.writeheader()
            dump = row.model_dump(mode="json")
            writer.writerow({c: dump[c] for c in DispatchLogRow.COLUMN_ORDER})
            text_fh.flush()
            os.fsync(text_fh.fileno())


def append_dispatch_log_rows(
    log_path: Path, rows: list[DispatchLogRow]
) -> None:
    """Bulk-append variant — single flock acquisition for many rows."""
    if not rows:
        return
    with _exclusive_lock(log_path) as fd:
        st = os.fstat(fd)
        is_new = st.st_size == 0

        with log_path.open("a", encoding="utf-8", newline="") as text_fh:
            writer = csv.DictWriter(
                text_fh, fieldnames=list(DispatchLogRow.COLUMN_ORDER)
            )
            if is_new:
                writer.writeheader()
            for row in rows:
                dump = row.model_dump(mode="json")
                writer.writerow(
                    {c: dump[c] for c in DispatchLogRow.COLUMN_ORDER}
                )
            text_fh.flush()
            os.fsync(text_fh.fileno())


# ---------------------------------------------------------------------------
# Reader + idempotent skip filter.
# ---------------------------------------------------------------------------


def read_dispatch_log(log_path: Path) -> list[DispatchLogRow]:
    """Read all rows from ``log_path`` and validate each via Pydantic.

    Args:
        log_path: Path to the dispatch log CSV. Returns ``[]`` when the
            file does not exist (first-run path).

    Returns:
        List of ``DispatchLogRow`` in CSV order (chronological).
    """
    if not log_path.is_file():
        return []
    rows: list[DispatchLogRow] = []
    with log_path.open(encoding="utf-8", newline="") as fh:
        reader = csv.DictReader(fh)
        for raw in reader:
            rows.append(DispatchLogRow.model_validate(raw))
    return rows


def _latest_status_by_sid(
    log: list[DispatchLogRow],
) -> dict[str, DispatchStatus]:
    """Group ``log`` by ``student_id`` and pick the latest ``attempt_at_kst``."""
    latest: dict[str, DispatchLogRow] = {}
    for row in log:
        prev = latest.get(row.student_id)
        if prev is None or row.attempt_at_kst > prev.attempt_at_kst:
            latest[row.student_id] = row
    return {sid: r.status for sid, r in latest.items()}


def idempotent_skip_filter(
    targets: list[str],
    log: list[DispatchLogRow],
    mode: RetryMode = RetryMode.DEFAULT,
) -> list[str]:
    """Return only the student_ids that should be sent on this run.

    Args:
        targets: All student_ids the caller wants to consider.
        log: Already-read DispatchLogRow rows (chronological).
        mode: Retry semantics (FR-D03 a/b/c) — ``default`` skips
            ``success`` only, ``retry_failed`` only re-tries
            ``failed``/``temporary_failure``, ``retry_skipped`` only
            re-tries ``skipped``.

    Returns:
        Filtered ``targets`` in original order.
    """
    if not log:
        return list(targets)
    latest = _latest_status_by_sid(log)

    if mode == RetryMode.RETRY_FAILED:
        skip_statuses: frozenset[DispatchStatus] = frozenset({
            DispatchStatus.SUCCESS,
            DispatchStatus.SKIPPED,
            DispatchStatus.DRY_RUN,
            DispatchStatus.TEST_DUMMY,
        })
    elif mode == RetryMode.RETRY_SKIPPED:
        skip_statuses = frozenset({
            DispatchStatus.SUCCESS,
            DispatchStatus.FAILED,
            DispatchStatus.TEMPORARY_FAILURE,
            DispatchStatus.DRY_RUN,
            DispatchStatus.TEST_DUMMY,
        })
    else:
        skip_statuses = frozenset({DispatchStatus.SUCCESS})

    return [sid for sid in targets if latest.get(sid) not in skip_statuses]


# ---------------------------------------------------------------------------
# Korean status labels (FR-D04 / contracts/email_log_csv.md).
# Single source-of-truth — re-exported by report.py for the dispatch
# report markdown summary.
# ---------------------------------------------------------------------------

STATUS_KR: dict[DispatchStatus, str] = {
    DispatchStatus.SUCCESS: "성공",
    DispatchStatus.SKIPPED: "누락",
    DispatchStatus.FAILED: "실패",
    DispatchStatus.TEMPORARY_FAILURE: "일시실패",
    DispatchStatus.DRY_RUN: "미리보기",
    DispatchStatus.TEST_DUMMY: "테스트",
}


__all__ = [
    "DispatchLockError",
    "RetryMode",
    "STATUS_KR",
    "append_dispatch_log_row",
    "append_dispatch_log_rows",
    "idempotent_skip_filter",
    "mask_secrets_in_error_detail",
    "read_dispatch_log",
]
