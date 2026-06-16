"""Phase C — student master cross-check (T042).

Verifies the (학번, 이름) extracted from each PDF filename matches the
canonical student master (``data/silver/immersio/학생마스터.parquet``).
A name mismatch is a *hard abort* (FR-A05) — possible PII leak risk if
the wrong PDF would attach to the wrong student.

Missing master file → caller exits 3 (file_missing). Master that lacks
a particular student's row → that student is *skipped* per FR-A02
(reported as ``error_kind=email_not_found``).
"""

from __future__ import annotations

from pathlib import Path

import pyarrow.parquet as pq
from paideia_shared.schemas import StudentPDFBundle


class MasterMismatchError(RuntimeError):
    """Raised when PDF filename name_kr ≠ master name_kr (FR-A05)."""


class MasterMissingError(RuntimeError):
    """Raised when the master parquet file is unreadable / missing."""


def _load_master_names(silver_master_parquet: Path) -> dict[str, str | None]:
    """Read the student master and return ``{student_id: name_kr or None}``."""
    if not isinstance(silver_master_parquet, Path):
        raise MasterMissingError(
            f"silver_master must be Path, got {type(silver_master_parquet).__name__}"
        )
    if not silver_master_parquet.is_file():
        raise MasterMissingError(f"student master parquet not found at {silver_master_parquet}")
    table = pq.read_table(silver_master_parquet)
    df = table.to_pydict()
    ids = df.get("student_id", [])
    names = df.get("name_kr", [])
    return dict(zip(ids, names, strict=True))


def cross_check_with_master(
    bundles: list[StudentPDFBundle],
    silver_master_parquet: Path,
) -> tuple[list[StudentPDFBundle], list[StudentPDFBundle]]:
    """Cross-check bundles against the canonical student master.

    Args:
        bundles: ``StudentPDFBundle`` rows from ``scan_pdf_directory``.
        silver_master_parquet: Path to ``학생마스터.parquet``.

    Returns:
        ``(matched, missing)`` — bundles whose ``student_id`` is in the
        master with matching ``name_kr`` are returned in ``matched``.
        Bundles whose ``student_id`` is *absent* from the master land in
        ``missing`` (caller logs per-student skip with
        ``error_kind=email_not_found``).

    Raises:
        MasterMismatchError: When any bundle's ``name_kr`` differs from
            the master's row for that ``student_id`` (FR-A05 hard abort).
        MasterMissingError: When the master file cannot be read.
    """
    master = _load_master_names(silver_master_parquet)

    matched: list[StudentPDFBundle] = []
    missing: list[StudentPDFBundle] = []
    for bundle in bundles:
        if bundle.student_id not in master:
            missing.append(bundle)
            continue
        master_name = master[bundle.student_id]
        if master_name is None or master_name.strip() == "":
            # Master name unknown — accept the PDF filename name_kr as truth
            matched.append(bundle)
            continue
        if master_name.strip() != bundle.name_kr.strip():
            raise MasterMismatchError(
                f"FR-A05: student_id {bundle.student_id!r} name mismatch — "
                f"PDF filename says {bundle.name_kr!r}, master says "
                f"{master_name!r}. Resolve the source-of-truth before re-running."
            )
        matched.append(bundle)
    return matched, missing


__all__ = [
    "MasterMismatchError",
    "MasterMissingError",
    "cross_check_with_master",
]
