"""Phase 3 re-run archival policy (T060, US6).

FR-022 + research §R6 #6 — reuses
``immersio.analyze.archival.archive_previous_run`` with Phase 3 specific
silver/gold whitelists so prior runs land in ``_archive/{ISO}__v{schema}/``
without disturbing persistent inputs (Phase 0 student_master, needs-map
silver) co-located with Phase 3 silver outputs.

Public:
- :func:`archive_phase3_previous_run(silver_dir, gold_dir, schema_version)`
  — wrapper that pins the Phase 3 file set:
    silver whitelist = {진단×시험결합.parquet, manifest_phase3.json}
    gold whitelist   = None (full archival of gold tree)
"""

from __future__ import annotations

from pathlib import Path

from immersio.analyze.archival import (
    ArchivalError,
    archive_previous_run,
)

# Phase 3 silver outputs that must move into _archive when re-running.
# Phase 0 student_master / diagnostic_response / 학생지표 stay put — they
# are *inputs* to combine, not outputs.
_SILVER_WHITELIST: frozenset[str] = frozenset(
    {
        "진단×시험결합.parquet",
        "manifest_phase3.json",
    }
)

# Gold has no persistent inputs — full archival.
_GOLD_WHITELIST = None


def archive_phase3_previous_run(
    *,
    silver_dir: Path,
    gold_dir: Path,
    schema_version: str | None = None,
) -> dict[str, str] | None:
    """Archive prior-run Phase 3 outputs (FR-022, SC-010).

    Args:
        silver_dir: Canonical silver output directory
            (``{silver}/immersio/{semester}-{course}``).
        gold_dir: Canonical gold output directory
            (``{gold}/immersio/{semester}-{course}``).
        schema_version: Optional explicit schema_version for the
            ``_archive/{ISO}__v{schema}/`` suffix; falls back to the
            manifest_phase3.json schema_version when None.

    Returns:
        ``{"silver": "_archive/{name}", "gold": "_archive/{name}"}`` on
        archival; ``None`` when both targets are first-run (empty or
        absent) — caller may proceed without archival.

    Raises:
        ArchivalError: I/O / permission failure during the move
            (mapped to FR-024 exit 4 by combine.cli).
    """
    # If caller didn't pin schema_version, probe manifest_phase3.json
    # directly — Phase 1+2 archival_helper only looks for manifest.json.
    if schema_version is None:
        manifest_phase3 = silver_dir / "manifest_phase3.json"
        if manifest_phase3.exists():
            try:
                import json

                payload = json.loads(manifest_phase3.read_text(encoding="utf-8"))
                schema_version = payload.get("schema_version")
            except (OSError, ValueError):
                schema_version = None

    return archive_previous_run(
        silver_dir=silver_dir,
        gold_dir=gold_dir,
        schema_version=schema_version,
        silver_whitelist=_SILVER_WHITELIST,
        gold_whitelist=_GOLD_WHITELIST,
    )


__all__ = ["ArchivalError", "archive_phase3_previous_run"]
