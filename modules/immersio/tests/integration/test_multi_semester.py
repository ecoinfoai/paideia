"""T061 — Multi-semester / multi-course canonical key isolation (FR-026, R-09).

The orchestrator (Phase 8 / T064) keys silver+gold canonical directories by
``{semester}-{course_slug}`` so two semesters or two courses never commingle
their outputs. Until the orchestrator lands, this test exercises the same
guarantee at the archival layer — running ``archive_previous_run`` on one
key must NOT touch a sibling key's outputs.
"""

from __future__ import annotations

from pathlib import Path

from immersio.analyze.archival import archive_previous_run


def _seed(silver_dir: Path, gold_dir: Path, marker: str) -> None:
    silver_dir.mkdir(parents=True, exist_ok=True)
    gold_dir.mkdir(parents=True, exist_ok=True)
    (silver_dir / "문항통계.parquet").write_bytes(marker.encode())
    (gold_dir / "시험분석결과.xlsx").write_bytes(marker.encode())


def test_two_semesters_share_no_canonical_paths(tmp_path: Path) -> None:
    """2026-1 anatomy ↔ 2026-2 anatomy must keep their outputs separate."""
    s1 = tmp_path / "silver" / "immersio" / "2026-1-anatomy"
    g1 = tmp_path / "gold" / "immersio" / "2026-1-anatomy"
    s2 = tmp_path / "silver" / "immersio" / "2026-2-anatomy"
    g2 = tmp_path / "gold" / "immersio" / "2026-2-anatomy"

    _seed(s1, g1, "semester-1-marker")
    _seed(s2, g2, "semester-2-marker")

    # Archive 2026-1 only
    archive_previous_run(silver_dir=s1, gold_dir=g1)

    # 2026-2 canonical paths must remain untouched.
    assert (s2 / "문항통계.parquet").read_bytes() == b"semester-2-marker"
    assert (g2 / "시험분석결과.xlsx").read_bytes() == b"semester-2-marker"
    assert not (s2 / "_archive").exists()
    assert not (g2 / "_archive").exists()


def test_two_courses_share_no_canonical_paths(tmp_path: Path) -> None:
    """2026-1 anatomy ↔ 2026-1 microbio must keep their outputs separate."""
    s_anatomy = tmp_path / "silver" / "immersio" / "2026-1-anatomy"
    g_anatomy = tmp_path / "gold" / "immersio" / "2026-1-anatomy"
    s_micro = tmp_path / "silver" / "immersio" / "2026-1-microbio"
    g_micro = tmp_path / "gold" / "immersio" / "2026-1-microbio"

    _seed(s_anatomy, g_anatomy, "anatomy-marker")
    _seed(s_micro, g_micro, "microbio-marker")

    archive_previous_run(silver_dir=s_anatomy, gold_dir=g_anatomy)

    assert (s_micro / "문항통계.parquet").read_bytes() == b"microbio-marker"
    assert (g_micro / "시험분석결과.xlsx").read_bytes() == b"microbio-marker"
    assert not (s_micro / "_archive").exists()
    assert not (g_micro / "_archive").exists()


def test_repeated_archival_within_single_key_accumulates_archives(tmp_path: Path) -> None:
    """Two consecutive runs on the same key produce two _archive subdirs."""
    silver = tmp_path / "silver" / "immersio" / "2026-1-anatomy"
    gold = tmp_path / "gold" / "immersio" / "2026-1-anatomy"

    _seed(silver, gold, "v1")
    first = archive_previous_run(silver_dir=silver, gold_dir=gold)
    assert first is not None

    _seed(silver, gold, "v2")
    second = archive_previous_run(silver_dir=silver, gold_dir=gold)
    assert second is not None

    silver_archives = list((silver / "_archive").iterdir())
    gold_archives = list((gold / "_archive").iterdir())
    assert len(silver_archives) == 2
    assert len(gold_archives) == 2

    # The two archive subdirs must have distinct names (no collision).
    assert {p.name for p in silver_archives} == {
        first["silver"].split("/")[-1],
        second["silver"].split("/")[-1],
    }


def test_archival_only_silver_present(tmp_path: Path) -> None:
    """Gold absent + silver populated: only silver archived, gold returns no key."""
    silver = tmp_path / "silver"
    gold = tmp_path / "gold"
    _seed_dir = silver
    _seed_dir.mkdir()
    (silver / "문항통계.parquet").write_bytes(b"silver-only")
    # gold dir does NOT exist

    result = archive_previous_run(silver_dir=silver, gold_dir=gold)
    assert result is not None
    assert "silver" in result
    assert "gold" not in result
    assert not gold.exists()
