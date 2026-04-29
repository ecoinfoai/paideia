"""TDD tests for ``combine.student_report`` (T067, post-closure).

Verifies the per-student counseling-sheet emitter:
- per-student md (gold/학생별/{sid}_{name_kr}.md)
- consolidated md (gold/학생별면담시트_합본.md)
- 결정성 byte-identical re-run
- Korean axis vocabulary + Top-3 인용
- 결시 학생 / 진단 미응답 학생 graceful fallback
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from types import ModuleType

import pandas as pd
import pyarrow.parquet as pq
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


@pytest.fixture(scope="module")
def silver_setup(
    tmp_path_factory: pytest.TempPathFactory,
) -> tuple[pd.DataFrame, dict, Path]:
    """Build minimal fixture, run pipeline (US1+US2 wired), return df/manifest/gold."""
    from immersio.combine.pipeline import run_us1_pipeline

    builder = _load_builder()
    tmp = tmp_path_factory.mktemp("student_report_setup")
    builder.build_silver_phase3_minimal(tmp)
    rc = run_us1_pipeline(
        semester="2026-1",
        course_slug="anatomy",
        silver_dir=tmp / "silver",
        gold_dir=tmp / "gold",
        include_cluster=True,
    )
    assert rc == 0
    silver_parquet = (
        tmp / "silver" / "immersio" / "2026-1-anatomy" / "진단×시험결합.parquet"
    )
    manifest_path = (
        tmp / "silver" / "immersio" / "2026-1-anatomy" / "manifest_phase3.json"
    )
    df = pq.read_table(silver_parquet).to_pandas()
    manifest_dict = json.loads(manifest_path.read_text(encoding="utf-8"))
    gold_target = tmp / "gold" / "immersio" / "2026-1-anatomy"
    return df, manifest_dict, gold_target


def test_build_returns_paths(silver_setup) -> None:
    from immersio.combine.student_report import build_student_reports

    df, manifest, gold = silver_setup
    paths = build_student_reports(df, manifest_dict=manifest, gold_dir=gold)
    assert isinstance(paths, list)
    # 30 학생 + 1 합본 = 31 paths.
    assert len(paths) == 31


def test_per_student_md_lands(silver_setup) -> None:
    from immersio.combine.student_report import build_student_reports

    df, manifest, gold = silver_setup
    build_student_reports(df, manifest_dict=manifest, gold_dir=gold)
    student_dir = gold / "학생별"
    assert student_dir.is_dir()
    student_files = list(student_dir.glob("*.md"))
    assert len(student_files) == 30


def test_consolidated_md_lands(silver_setup) -> None:
    from immersio.combine.student_report import build_student_reports

    df, manifest, gold = silver_setup
    build_student_reports(df, manifest_dict=manifest, gold_dir=gold)
    consolidated = gold / "학생별면담시트_합본.md"
    assert consolidated.exists()
    assert consolidated.stat().st_size > 0


def test_consolidated_md_contains_all_students(silver_setup) -> None:
    from immersio.combine.student_report import build_student_reports

    df, manifest, gold = silver_setup
    build_student_reports(df, manifest_dict=manifest, gold_dir=gold)
    consolidated = (gold / "학생별면담시트_합본.md").read_text(encoding="utf-8")
    # Every student_id must appear in the consolidated file.
    for sid in df["student_id"]:
        assert sid in consolidated, f"student_id {sid} missing from consolidated"


def test_byte_identical_re_run(
    tmp_path_factory: pytest.TempPathFactory,
) -> None:
    """Two runs on identical input → byte-equal consolidated md."""
    from immersio.combine.pipeline import run_us1_pipeline
    from immersio.combine.student_report import build_student_reports

    builder = _load_builder()
    a = tmp_path_factory.mktemp("sr_run_a")
    b = tmp_path_factory.mktemp("sr_run_b")
    builder.build_silver_phase3_minimal(a)
    builder.build_silver_phase3_minimal(b)

    for root in (a, b):
        run_us1_pipeline(
            semester="2026-1",
            course_slug="anatomy",
            silver_dir=root / "silver",
            gold_dir=root / "gold",
            include_cluster=True,
        )
        silver_parquet = (
            root / "silver" / "immersio" / "2026-1-anatomy" / "진단×시험결합.parquet"
        )
        manifest_path = (
            root / "silver" / "immersio" / "2026-1-anatomy" / "manifest_phase3.json"
        )
        df = pq.read_table(silver_parquet).to_pandas()
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        gold = root / "gold" / "immersio" / "2026-1-anatomy"
        build_student_reports(df, manifest_dict=manifest, gold_dir=gold)

    md_a = (a / "gold" / "immersio" / "2026-1-anatomy" / "학생별면담시트_합본.md").read_bytes()
    md_b = (b / "gold" / "immersio" / "2026-1-anatomy" / "학생별면담시트_합본.md").read_bytes()
    assert md_a == md_b


def test_korean_axis_vocabulary_present(silver_setup) -> None:
    from immersio.combine.student_report import build_student_reports

    df, manifest, gold = silver_setup
    build_student_reports(df, manifest_dict=manifest, gold_dir=gold)
    consolidated = (gold / "학생별면담시트_합본.md").read_text(encoding="utf-8")
    # 8 axis Korean labels must surface.
    for kr_label in (
        "디지털 효능감",
        "학습 동기",
        "학습 시간 가용성",
        "교재 선호도",
        "학습 전략",
        "학습 환경",
        "사회적 학습",
        "피드백 추구",
    ):
        assert kr_label in consolidated


def test_absent_student_marked_as_결시(silver_setup) -> None:
    from immersio.combine.student_report import build_student_reports

    df, manifest, gold = silver_setup
    build_student_reports(df, manifest_dict=manifest, gold_dir=gold)
    consolidated = (gold / "학생별면담시트_합본.md").read_text(encoding="utf-8")
    # Minimal fixture has 3 응답-only students (시험 결시).
    assert "시험 미응시 — 결시" in consolidated


def test_student_id_ascending_order(silver_setup) -> None:
    """Determinism: 학생 sections sorted by student_id ascending."""
    from immersio.combine.student_report import build_student_reports

    df, manifest, gold = silver_setup
    build_student_reports(df, manifest_dict=manifest, gold_dir=gold)
    consolidated = (gold / "학생별면담시트_합본.md").read_text(encoding="utf-8")
    sids_sorted = sorted(df["student_id"].tolist())
    last_pos = -1
    for sid in sids_sorted:
        pos = consolidated.find(sid)
        assert pos > last_pos, f"student_id {sid} appears out of ascending order"
        last_pos = pos


def test_empty_df_rejected(tmp_path: Path) -> None:
    from immersio.combine.student_report import build_student_reports

    with pytest.raises(ValueError, match="empty"):
        build_student_reports(
            pd.DataFrame(),
            manifest_dict={"top3_predictor_axes": []},
            gold_dir=tmp_path,
        )


def test_creates_parent_directory(silver_setup, tmp_path: Path) -> None:
    from immersio.combine.student_report import build_student_reports

    df, manifest, _ = silver_setup
    nested = tmp_path / "deep" / "nest"
    build_student_reports(df, manifest_dict=manifest, gold_dir=nested)
    assert (nested / "학생별").is_dir()
    assert (nested / "학생별면담시트_합본.md").exists()
