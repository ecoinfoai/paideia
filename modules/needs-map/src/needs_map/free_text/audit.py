"""Per-token freetext audit parquet writer [T056].

US6 spec FR-031 + research §R-12 — write one row per (student,
freetext_source, token) for the silver tier ``freetext_audit.parquet``.
Operators / auditors can replay the exact tokenization the RoBERTa
classifier saw.

The writer accepts validated ``FreetextAuditRow`` instances (T015) so
schema invariants (sha256 hex, char_start ≤ char_end ≤ length) are
guaranteed before the parquet is built. Output is sorted by
(student_id, freetext_source, token_index) for deterministic byte-equal
runs (FR-035).
"""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path

import pandas as pd
from paideia_shared.schemas import FreetextAuditRow


def write_freetext_audit(
    rows: Iterable[FreetextAuditRow], silver_dir: Path
) -> Path:
    """Write per-token audit rows to ``silver_dir/freetext_audit.parquet``.

    Args:
        rows: Validated FreetextAuditRow instances. Caller is responsible
            for the redaction + tokenization that produced them.
        silver_dir: Destination directory; created if absent.

    Returns:
        Absolute path to the written parquet file.
    """
    if not isinstance(silver_dir, Path):
        raise TypeError(
            f"write_freetext_audit: expected Path, got {type(silver_dir).__name__}."
        )
    silver_dir.mkdir(parents=True, exist_ok=True)
    materialised = sorted(
        rows, key=lambda r: (r.student_id, r.freetext_source, r.token_index)
    )
    df = pd.DataFrame([r.model_dump() for r in materialised])
    target = silver_dir / "freetext_audit.parquet"
    if df.empty:
        # Even an empty audit must land so the manifest path resolves.
        # Build an empty DataFrame with the canonical column order so
        # downstream parquet readers have a stable schema.
        canonical_columns = list(FreetextAuditRow.model_fields.keys())
        df = pd.DataFrame(columns=canonical_columns)
    df.to_parquet(target, index=False, compression="snappy")
    return target


__all__ = ["write_freetext_audit"]
