"""T060 — Tests for `analyze/archival.py::archive_previous_run` (FR-025, R-09).

Behaviours under test (per dispatch + tasks.md):

* (a) 빈 디렉터리 첫 실행 → archival 없음 (returns None)
* (b) 두 번째 실행 → ``_archive/{ISO8601}__v{schema}/`` 생성 + 이전 산출 이동
* (c) canonical 경로 commingling 없음 (archive 후 canonical 빈 상태)
* (d) silver + gold 양쪽 동시 archival
* (e) schema_version suffix 가 manifest.json 에서 읽힘 (또는 인자로 명시)
* (f) atomic rename failure → ArchivalError raise (silent skip 금지)
"""

from __future__ import annotations

from pathlib import Path

import pytest
from immersio.analyze.archival import (
    ArchivalError,
    archive_previous_run,
)


def _seed_silver(silver_dir: Path) -> None:
    silver_dir.mkdir(parents=True, exist_ok=True)
    (silver_dir / "문항통계.parquet").write_bytes(b"fake-parquet-1")
    (silver_dir / "학생지표.parquet").write_bytes(b"fake-parquet-2")
    (silver_dir / "manifest.json").write_text('{"schema_version": "1.0.0"}', encoding="utf-8")


def _seed_gold(gold_dir: Path) -> None:
    gold_dir.mkdir(parents=True, exist_ok=True)
    (gold_dir / "시험분석결과.xlsx").write_bytes(b"fake-xlsx")
    (gold_dir / "시험품질보고서.md").write_text("# fake report\n", encoding="utf-8")
    (gold_dir / "manifest.json").write_text('{"schema_version": "1.0.0"}', encoding="utf-8")


def test_first_run_returns_none(tmp_path: Path) -> None:
    silver = tmp_path / "silver"
    gold = tmp_path / "gold"
    result = archive_previous_run(silver_dir=silver, gold_dir=gold)
    assert result is None
    assert not silver.exists()
    assert not gold.exists()


def test_second_run_archives_silver_and_gold(tmp_path: Path) -> None:
    silver = tmp_path / "silver"
    gold = tmp_path / "gold"
    _seed_silver(silver)
    _seed_gold(gold)

    result = archive_previous_run(silver_dir=silver, gold_dir=gold)
    assert result is not None, "archival of populated dirs must return a dict"
    # Both silver and gold archives must surface in the return value
    assert "silver" in result
    assert "gold" in result
    # Each archive subpath uses the _archive/{ISO}__v{schema} pattern
    assert result["silver"].startswith("_archive/")
    assert "__v" in result["silver"]
    assert result["gold"].startswith("_archive/")
    assert "__v" in result["gold"]


def test_archived_files_moved_into_archive_subdir(tmp_path: Path) -> None:
    silver = tmp_path / "silver"
    gold = tmp_path / "gold"
    _seed_silver(silver)
    _seed_gold(gold)
    result = archive_previous_run(silver_dir=silver, gold_dir=gold)
    assert result is not None

    # Canonical paths must be empty (apart from _archive subtree).
    silver_remaining = [p.name for p in silver.iterdir() if p.name != "_archive"]
    gold_remaining = [p.name for p in gold.iterdir() if p.name != "_archive"]
    assert silver_remaining == []
    assert gold_remaining == []

    # Archive subdir must contain the previous outputs verbatim.
    archive_silver = silver / result["silver"]
    archive_gold = gold / result["gold"]
    assert (archive_silver / "문항통계.parquet").is_file()
    assert (archive_silver / "학생지표.parquet").is_file()
    assert (archive_silver / "manifest.json").is_file()
    assert (archive_gold / "시험분석결과.xlsx").is_file()
    assert (archive_gold / "시험품질보고서.md").is_file()


def test_schema_version_suffix_from_manifest(tmp_path: Path) -> None:
    silver = tmp_path / "silver"
    gold = tmp_path / "gold"
    silver.mkdir()
    (silver / "manifest.json").write_text('{"schema_version": "2.3.4"}', encoding="utf-8")
    (silver / "stub.bin").write_bytes(b"x")
    gold.mkdir()
    (gold / "stub.bin").write_bytes(b"y")
    result = archive_previous_run(silver_dir=silver, gold_dir=gold)
    assert result is not None
    assert "__v2.3.4" in result["silver"]
    # Gold falls back to silver's schema_version when its own manifest is
    # absent (operator-friendly default).
    assert "__v" in result["gold"]


def test_missing_manifest_falls_back_to_unknown_suffix(tmp_path: Path) -> None:
    silver = tmp_path / "silver"
    gold = tmp_path / "gold"
    silver.mkdir()
    (silver / "stub.bin").write_bytes(b"x")
    gold.mkdir()
    (gold / "stub.bin").write_bytes(b"y")
    result = archive_previous_run(silver_dir=silver, gold_dir=gold)
    assert result is not None
    assert "__vunknown" in result["silver"]


def test_explicit_schema_version_overrides_manifest(tmp_path: Path) -> None:
    silver = tmp_path / "silver"
    gold = tmp_path / "gold"
    silver.mkdir()
    (silver / "manifest.json").write_text('{"schema_version": "1.0.0"}', encoding="utf-8")
    (silver / "stub.bin").write_bytes(b"x")
    gold.mkdir()
    (gold / "stub.bin").write_bytes(b"y")
    result = archive_previous_run(silver_dir=silver, gold_dir=gold, schema_version="9.9.9")
    assert result is not None
    assert "__v9.9.9" in result["silver"]
    assert "__v9.9.9" in result["gold"]


def test_archive_subdir_excluded_from_archive_iteration(tmp_path: Path) -> None:
    """Re-running on a dir that already has _archive must not re-archive _archive."""
    silver = tmp_path / "silver"
    gold = tmp_path / "gold"
    _seed_silver(silver)
    _seed_gold(gold)
    # First run
    archive_previous_run(silver_dir=silver, gold_dir=gold)
    # Re-seed with new outputs (post-archival)
    (silver / "문항통계.parquet").write_bytes(b"v2-parquet")
    (gold / "시험분석결과.xlsx").write_bytes(b"v2-xlsx")
    # Second run — must archive the second seeding without descending into _archive
    result = archive_previous_run(silver_dir=silver, gold_dir=gold)
    assert result is not None
    # _archive must contain TWO subdirs now (one per run)
    silver_archives = list((silver / "_archive").iterdir())
    assert len(silver_archives) == 2


def test_existing_path_is_file_not_dir_raises(tmp_path: Path) -> None:
    silver = tmp_path / "silver"
    silver.write_bytes(b"this is a file, not a dir")
    gold = tmp_path / "gold"
    with pytest.raises(ArchivalError):
        archive_previous_run(silver_dir=silver, gold_dir=gold)


def test_path_argument_must_be_pathlib_path(tmp_path: Path) -> None:
    with pytest.raises(TypeError):
        archive_previous_run(silver_dir=str(tmp_path), gold_dir=tmp_path)
