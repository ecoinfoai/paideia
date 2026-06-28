"""Email roster — Phase A of US1 (T040).

Parses the Bronze diagnostic CSV into ``EmailMappingEntry`` rows
(student_id → email + source row index + timestamp). Writes a
deterministic Silver parquet (``학번_이메일_매핑.parquet``) for
downstream phases.

Bronze CSV column order:
  col 0: 타임스탬프 (ISO8601 KST or "YYYY/MM/DD HH:MM:SS AM/PM GMT+9")
  col 1: 사용자 이름 (= email address)
  col 2: 학번 (student_id, may be 9-digit zero-pad target)
  col 3+: questionnaire fields (ignored)

Multiple responses for the same student_id retain only the *first*
(by row index) — operator may override via Phase 0 ingest.
"""

from __future__ import annotations

import csv
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq
from paideia_shared.io import atomic_write
from paideia_shared.schemas import EmailMappingEntry

from ..normalize.student_id import normalize_student_id

KST = timezone(timedelta(hours=9))

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
# Google Forms timestamp format: "2026/03/03 11:03:36 AM GMT+9"
_FORMS_TS_RE = re.compile(
    r"^(\d{4})/(\d{2})/(\d{2})\s+"
    r"(\d{1,2}):(\d{2}):(\d{2})\s+([AP]M)\s+GMT\+9$"
)


class RosterError(RuntimeError):
    """Raised when the Bronze CSV cannot be parsed into mapping entries."""


def _parse_forms_timestamp(raw: str) -> datetime:
    """Parse Google Forms timestamp ``YYYY/MM/DD HH:MM:SS AM/PM GMT+9``.

    Falls back to ISO 8601 ``fromisoformat`` for already-canonical inputs
    (post-Phase-0 silver). KST tzinfo is attached when missing.
    """
    raw = raw.strip()
    m = _FORMS_TS_RE.match(raw)
    if m is not None:
        y, mo, d, h, mi, s, ampm = m.groups()
        hour = int(h) % 12
        if ampm == "PM":
            hour += 12
        return datetime(int(y), int(mo), int(d), hour, int(mi), int(s), tzinfo=KST)
    try:
        dt = datetime.fromisoformat(raw)
    except ValueError as exc:
        raise RosterError(
            f"roster: cannot parse timestamp {raw!r} (expected Google Forms or ISO 8601 format)"
        ) from exc
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=KST)
    return dt


def load_email_mapping(bronze_csv: Path) -> list[EmailMappingEntry]:
    """Parse a Bronze diagnostic CSV into ``EmailMappingEntry`` rows.

    Args:
        bronze_csv: Absolute path to the Bronze CSV (``진단평가_1차_결과.csv``).

    Returns:
        List of ``EmailMappingEntry`` sorted by ``student_id``. Rows
        with invalid email or unparseable student_id are *skipped*
        (logged via WARN), not aborted — Phase E reports them as
        ``error_kind=invalid_email`` / ``email_not_found``. Duplicate
        student_id keeps the *first* response only.

    Raises:
        RosterError: When the CSV cannot be opened, has fewer than 3
            columns, or any timestamp is unparseable.
    """
    if not isinstance(bronze_csv, Path):
        raise RosterError(
            f"load_email_mapping: bronze_csv must be Path, got {type(bronze_csv).__name__}"
        )
    if not bronze_csv.is_file():
        raise RosterError(f"load_email_mapping: file not found at {bronze_csv}")

    seen_ids: set[str] = set()
    entries: list[EmailMappingEntry] = []
    with bronze_csv.open(encoding="utf-8", newline="") as handle:
        reader = csv.reader(handle)
        rows = list(reader)
    if len(rows) < 1:
        raise RosterError(f"load_email_mapping: empty CSV at {bronze_csv}")

    # First row = header; data starts at row index 1
    for row_index, row in enumerate(rows[1:], start=1):
        if len(row) < 3:
            # Sparse row — skip silently with warning would normally happen
            continue
        ts_raw, email_raw, sid_raw = row[0], row[1], row[2]
        email_clean = email_raw.strip().lower()
        if not _EMAIL_RE.fullmatch(email_clean):
            # invalid_email — record source for Phase E reporting via skip
            continue
        try:
            sid = normalize_student_id(sid_raw)
        except (TypeError, ValueError):
            # email_not_found — student_id unparseable
            continue
        if sid in seen_ids:
            continue  # First response wins (FR-A02)
        seen_ids.add(sid)
        try:
            ts = _parse_forms_timestamp(ts_raw)
        except RosterError:
            continue
        entries.append(
            EmailMappingEntry(
                student_id=sid,
                email=email_clean,
                source_row_index=row_index,
                original_timestamp=ts,
            )
        )
    entries.sort(key=lambda e: e.student_id)
    return entries


def write_mapping_silver(entries: list[EmailMappingEntry], silver_path: Path) -> None:
    """Write ``학번_이메일_매핑.parquet`` deterministically.

    Args:
        entries: Sorted ``EmailMappingEntry`` rows.
        silver_path: Output path. Parent directory created if missing.

    Determinism levers (ADR-008):
      - ``use_dictionary=False`` — no dictionary encoding (size-stable)
      - ``write_statistics=False`` — drop row-group min/max metadata
      - column order fixed via ``pa.schema`` (matches model)
    """
    if not isinstance(silver_path, Path):
        raise TypeError(
            f"write_mapping_silver: silver_path must be Path, got {type(silver_path).__name__}"
        )
    silver_path.parent.mkdir(parents=True, exist_ok=True)

    schema = pa.schema(
        [
            ("student_id", pa.string()),
            ("email", pa.string()),
            ("source_row_index", pa.int64()),
            ("original_timestamp", pa.timestamp("us", tz="Asia/Seoul")),
        ]
    )
    columns = {
        "student_id": [e.student_id for e in entries],
        "email": [str(e.email) for e in entries],
        "source_row_index": [e.source_row_index for e in entries],
        "original_timestamp": [e.original_timestamp for e in entries],
    }
    table = pa.table(columns, schema=schema)
    # Owner-only via atomic temp→rename (DAR-02) — keeps determinism levers.
    atomic_write(
        silver_path,
        lambda p: pq.write_table(
            table,
            p,
            use_dictionary=False,
            write_statistics=False,
            compression="snappy",
        ),
    )


__all__ = ["RosterError", "load_email_mapping", "write_mapping_silver"]
