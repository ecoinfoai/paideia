"""T006+T014 security test — per-student interview MD files must be owner-only.

Gold artifacts ``학생별/{sid}_{name_kr}.md`` and ``학생별면담시트_합본.md``
carry student PII (student_id + name_kr) and must never be world-readable.

Requirement: both per-student MD files and the consolidated MD file produced
by ``build_student_reports`` must have permissions ``mode & 0o077 == 0``
(0o600, owner-only).
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from types import ModuleType

import pyarrow.parquet as pq
import pytest


def _load_builder() -> ModuleType:
    here = Path(__file__).resolve()
    builder_path = here.parents[2] / "fixtures" / "build_silver_phase3.py"
    spec = importlib.util.spec_from_file_location("build_silver_phase3", builder_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"could not load builder from {builder_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def student_report_setup(
    tmp_path_factory: pytest.TempPathFactory,
) -> tuple[object, dict, Path]:
    """Build minimal silver fixture and return (df, manifest_dict, gold_dir)."""
    from immersio.combine.pipeline import run_us1_pipeline

    builder = _load_builder()
    tmp = tmp_path_factory.mktemp("student_report_perms")
    builder.build_silver_phase3_minimal(tmp)
    rc = run_us1_pipeline(
        semester="2026-1",
        course_slug="anatomy",
        silver_dir=tmp / "silver",
        gold_dir=tmp / "gold",
        include_cluster=True,
    )
    assert rc == 0
    silver_parquet = tmp / "silver" / "immersio" / "2026-1-anatomy" / "진단×시험결합.parquet"
    manifest_path = tmp / "silver" / "immersio" / "2026-1-anatomy" / "manifest_phase3.json"
    df = pq.read_table(silver_parquet).to_pandas()
    manifest_dict = json.loads(manifest_path.read_text(encoding="utf-8"))
    gold_dir = tmp / "gold" / "immersio" / "2026-1-anatomy"
    return df, manifest_dict, gold_dir


def test_per_student_md_is_owner_only(
    student_report_setup, tmp_path: Path, assert_owner_only
) -> None:
    """T006/T014: per-student MD files must be chmod 0o600 (no group/other bits)."""
    from immersio.combine.student_report import build_student_reports

    df, manifest, gold = student_report_setup
    gold_target = tmp_path / "gold_perms"
    paths = build_student_reports(df, manifest_dict=manifest, gold_dir=gold_target)

    student_mds = [p for p in paths if p.parent.name == "학생별"]
    assert len(student_mds) >= 1, "expected at least one per-student MD file"

    # Check at least the first per-student file — representative for all.
    assert_owner_only(student_mds[0])


def test_consolidated_md_is_owner_only(
    student_report_setup, tmp_path: Path, assert_owner_only
) -> None:
    """T006/T014: consolidated MD file must be chmod 0o600 (no group/other bits)."""
    from immersio.combine.student_report import build_student_reports

    df, manifest, gold = student_report_setup
    gold_target = tmp_path / "gold_consol"
    paths = build_student_reports(df, manifest_dict=manifest, gold_dir=gold_target)

    consolidated = gold_target / "학생별면담시트_합본.md"
    assert consolidated in paths
    assert_owner_only(consolidated)


def test_all_per_student_mds_are_owner_only(
    student_report_setup, tmp_path: Path, assert_owner_only
) -> None:
    """T006/T014: ALL per-student MD files must be owner-only, not just the first."""
    from immersio.combine.student_report import build_student_reports

    df, manifest, gold = student_report_setup
    gold_target = tmp_path / "gold_all_perms"
    paths = build_student_reports(df, manifest_dict=manifest, gold_dir=gold_target)

    student_mds = [p for p in paths if p.parent.name == "학생별"]
    assert len(student_mds) == 30, f"expected 30 per-student MDs, got {len(student_mds)}"
    for p in student_mds:
        assert_owner_only(p)
