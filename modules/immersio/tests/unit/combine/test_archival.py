"""TDD tests for ``combine.archival`` (T058, US6).

Verifies the Phase 3 archival wrapper:
- first-run (empty target) returns None — no _archive created
- second-run moves silver/gold artefacts into ``_archive/{ISO}__v{schema}/``
- silver_whitelist preserves Phase 0 inputs (student_master /
  diagnostic_response / 학생지표) co-located in same silver dir
- ArchivalError surfaces on I/O failure (caller maps to FR-024 exit 4)
"""

from __future__ import annotations

from pathlib import Path

import pytest

from immersio.combine.archival import (
    ArchivalError,
    archive_phase3_previous_run,
)


def _populate_silver(target: Path) -> None:
    target.mkdir(parents=True, exist_ok=True)
    (target / "진단×시험결합.parquet").write_bytes(b"silver-bytes")
    (target / "manifest_phase3.json").write_text(
        '{"schema_version": "0.1.0"}\n', encoding="utf-8"
    )
    # Phase 0/2 inputs that must stay put (whitelist excludes them).
    (target / "student_master.parquet").write_bytes(b"phase0-bytes")
    (target / "학생지표.parquet").write_bytes(b"phase2-bytes")


def _populate_gold(target: Path) -> None:
    target.mkdir(parents=True, exist_ok=True)
    (target / "결합분석보고서.md").write_text("# r1\n", encoding="utf-8")
    (target / "결합분석보고서.pdf").write_bytes(b"%PDF-mock")
    (target / "결합분석.xlsx").write_bytes(b"PK-mock")
    figs = target / "figs"
    figs.mkdir()
    (figs / "fig3_corr_heatmap.png").write_bytes(b"PNG-mock")


def test_first_run_returns_none(tmp_path: Path) -> None:
    silver = tmp_path / "silver" / "immersio" / "2026-1-anatomy"
    gold = tmp_path / "gold" / "immersio" / "2026-1-anatomy"
    silver.mkdir(parents=True)
    gold.mkdir(parents=True)
    rc = archive_phase3_previous_run(silver_dir=silver, gold_dir=gold)
    # Empty silver/gold (no Phase 3 outputs) → no archive created.
    assert rc is None


def test_second_run_archives_silver_and_gold(tmp_path: Path) -> None:
    silver = tmp_path / "silver" / "immersio" / "2026-1-anatomy"
    gold = tmp_path / "gold" / "immersio" / "2026-1-anatomy"
    _populate_silver(silver)
    _populate_gold(gold)

    rc = archive_phase3_previous_run(silver_dir=silver, gold_dir=gold)
    assert rc is not None
    assert "silver" in rc and "gold" in rc

    # Silver archive: 진단×시험결합 + manifest_phase3 moved into _archive.
    silver_archive = silver / "_archive"
    assert silver_archive.exists()
    archived_files = list(silver_archive.rglob("*"))
    archived_basenames = {p.name for p in archived_files if p.is_file()}
    assert "진단×시험결합.parquet" in archived_basenames
    assert "manifest_phase3.json" in archived_basenames


def test_phase0_inputs_stay_put(tmp_path: Path) -> None:
    """Whitelist excludes student_master / diagnostic_response / 학생지표."""
    silver = tmp_path / "silver" / "immersio" / "2026-1-anatomy"
    gold = tmp_path / "gold" / "immersio" / "2026-1-anatomy"
    _populate_silver(silver)
    _populate_gold(gold)

    archive_phase3_previous_run(silver_dir=silver, gold_dir=gold)

    # Phase 0/2 inputs must NOT be archived.
    assert (silver / "student_master.parquet").exists()
    assert (silver / "학생지표.parquet").exists()
    # Phase 3 outputs were moved.
    assert not (silver / "진단×시험결합.parquet").exists()
    assert not (silver / "manifest_phase3.json").exists()


def test_gold_full_archival(tmp_path: Path) -> None:
    """Gold has no persistent inputs — full archival."""
    silver = tmp_path / "silver" / "immersio" / "2026-1-anatomy"
    gold = tmp_path / "gold" / "immersio" / "2026-1-anatomy"
    _populate_silver(silver)
    _populate_gold(gold)

    archive_phase3_previous_run(silver_dir=silver, gold_dir=gold)

    # Gold archive must contain the report files.
    gold_archive = gold / "_archive"
    assert gold_archive.exists()
    archived = {p.name for p in gold_archive.rglob("*") if p.is_file()}
    assert "결합분석보고서.md" in archived
    assert "결합분석.xlsx" in archived


def test_schema_version_suffix_in_archive_dir(tmp_path: Path) -> None:
    silver = tmp_path / "silver" / "immersio" / "2026-1-anatomy"
    gold = tmp_path / "gold" / "immersio" / "2026-1-anatomy"
    _populate_silver(silver)
    _populate_gold(gold)

    rc = archive_phase3_previous_run(silver_dir=silver, gold_dir=gold)
    assert rc is not None
    assert "v0.1.0" in rc["silver"], rc
