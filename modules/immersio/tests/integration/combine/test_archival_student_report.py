"""Integration test — archival 의 학생별/ 서브디렉터리 보존 (qa GAP-11 verify).

qa-engineer 가 GAP-11 (archival silver_whitelist 학생별 디렉터리 미land)
권고했으나, 실제로는 archival_phase3 의 ``_GOLD_WHITELIST = None`` 가
full archival 을 trigger 하고 Phase 1+2 archival 의 ``_archive_one`` 이
``Path.rename`` 으로 디렉터리 sub-tree 도 정상 archive — 본 test 가
실재 동작을 검증하여 GAP-11 을 *resolved-by-design* 으로 closure.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType

import pytest


def _load_builder() -> ModuleType:
    here = Path(__file__).resolve()
    builder_path = here.parents[2] / "fixtures" / "build_silver_phase3.py"
    spec = importlib.util.spec_from_file_location(
        "build_silver_phase3", builder_path
    )
    if spec is None or spec.loader is None:
        raise RuntimeError(f"could not load builder from {builder_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_re_run_archives_student_report_consolidated(
    tmp_path_factory: pytest.TempPathFactory,
) -> None:
    """qa GAP-11: 2nd run 시 1st run 학생별면담시트_합본.md 가 _archive 로 이동."""
    from immersio.combine.pipeline import run_us1_pipeline

    builder = _load_builder()
    tmp = tmp_path_factory.mktemp("gap11_consolidated")
    builder.build_silver_phase3_minimal(tmp)

    # 1st run
    run_us1_pipeline(
        semester="2026-1",
        course_slug="anatomy",
        silver_dir=tmp / "silver",
        gold_dir=tmp / "gold",
    )
    # 2nd run (archival hook moves prior outputs)
    run_us1_pipeline(
        semester="2026-1",
        course_slug="anatomy",
        silver_dir=tmp / "silver",
        gold_dir=tmp / "gold",
    )

    gold_archive = (
        tmp / "gold" / "immersio" / "2026-1-anatomy" / "_archive"
    )
    archived_top = {p.name for p in gold_archive.rglob("*") if p.is_file()}
    assert "학생별면담시트_합본.md" in archived_top, (
        f"qa GAP-11: 1st run 학생별면담시트_합본.md 가 _archive 에 미land. "
        f"archive contents: {sorted(archived_top)}"
    )


def test_re_run_archives_student_report_per_student_dir(
    tmp_path_factory: pytest.TempPathFactory,
) -> None:
    """qa GAP-11: 학생별/ 서브디렉터리 + 30 학생별 .md 가 모두 archive."""
    from immersio.combine.pipeline import run_us1_pipeline

    builder = _load_builder()
    tmp = tmp_path_factory.mktemp("gap11_per_student")
    builder.build_silver_phase3_minimal(tmp)

    run_us1_pipeline(
        semester="2026-1",
        course_slug="anatomy",
        silver_dir=tmp / "silver",
        gold_dir=tmp / "gold",
    )
    run_us1_pipeline(
        semester="2026-1",
        course_slug="anatomy",
        silver_dir=tmp / "silver",
        gold_dir=tmp / "gold",
    )

    gold_archive = (
        tmp / "gold" / "immersio" / "2026-1-anatomy" / "_archive"
    )
    # 학생별 디렉터리가 archive 안에 sub-directory 로 보존.
    student_dirs = list(gold_archive.rglob("학생별"))
    assert student_dirs, (
        f"qa GAP-11: 학생별/ 서브디렉터리 archive 미land. "
        f"contents: {sorted(p.name for p in gold_archive.rglob('*'))}"
    )
    # 학생별 .md 30 파일 모두 보존.
    student_mds = list(student_dirs[0].glob("*.md"))
    assert len(student_mds) == 30, (
        f"qa GAP-11: 30 학생별 .md 중 {len(student_mds)} 개만 archive 됨"
    )
