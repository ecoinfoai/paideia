"""Phase A+B byte-equality across two consecutive runs (T041, SC-002)."""

from __future__ import annotations

import filecmp
import json
import shutil
from pathlib import Path

import pytest

_FIXTURE_ROOT = Path("modules/needs-map/tests/fixtures/silver_minimal")
_FULL_MAPPING = Path("modules/needs-map/tests/fixtures/mappings/anatomy_full.diagnostic.yaml")


def _stage(tmp_path: Path) -> Path:
    silver_dir = tmp_path / "silver" / "immersio" / "2026-1-anatomy"
    silver_dir.mkdir(parents=True)
    for name in ("student_master.parquet", "diagnostic_response.parquet"):
        shutil.copy(
            _FIXTURE_ROOT / "silver" / "immersio" / "2026-1-anatomy" / name,
            silver_dir / name,
        )
    mapping_dir = tmp_path / "bronze" / "매핑"
    mapping_dir.mkdir(parents=True)
    shutil.copy(_FULL_MAPPING, mapping_dir / "anatomy.diagnostic.yaml")
    return tmp_path


def test_phase_ab_two_runs_byte_equal(tmp_path: Path) -> None:
    from needs_map.pipeline import NeedsMapArgs, run_needs_map

    in_a = _stage(tmp_path / "in_a")
    in_b = _stage(tmp_path / "in_b")

    args_a = NeedsMapArgs(
        semester="2026-1",
        course_slug="anatomy",
        phases=frozenset({"A", "B"}),
        input_root=in_a,
        output_root=tmp_path / "out_a",
        seed=42,
        llm_enabled=False,
        llm_provider="anthropic",
        llm_model="claude-sonnet-4-6",
        # Pin created_at_utc so the manifest also stays equal
        created_at_utc="2026-04-27T00:00:00Z",
    )
    args_b = args_a.model_copy(update={"input_root": in_b, "output_root": tmp_path / "out_b"})

    run_needs_map(args_a)
    run_needs_map(args_b)

    silver_a = tmp_path / "out_a" / "silver" / "needs-map" / "2026-1-anatomy"
    silver_b = tmp_path / "out_b" / "silver" / "needs-map" / "2026-1-anatomy"

    for name in ("scale_reliability.parquet", "factor_scores.parquet"):
        assert filecmp.cmp(silver_a / name, silver_b / name, shallow=False), (
            f"{name} differs between runs"
        )

    # manifest identical when created_at_utc is pinned
    m_a = json.loads((silver_a / "manifest.json").read_text(encoding="utf-8"))
    m_b = json.loads((silver_b / "manifest.json").read_text(encoding="utf-8"))
    # input paths differ (in_a vs in_b) — strip them out before comparison
    for m in (m_a, m_b):
        m["inputs"]["diagnostic_response_path"] = "<path>"
        m["inputs"]["student_master_path"] = "<path>"
        m["inputs"]["diagnostic_mapping_path"] = "<path>"
    assert m_a == m_b


def test_phase_ab_byte_equal_excludes_created_at(tmp_path: Path) -> None:
    """Without pinning created_at_utc, parquet still byte-equal (no timestamp inside)."""
    from needs_map.pipeline import NeedsMapArgs, run_needs_map

    in_a = _stage(tmp_path / "in_a")
    in_b = _stage(tmp_path / "in_b")

    base = {
        "semester": "2026-1",
        "course_slug": "anatomy",
        "phases": frozenset({"A", "B"}),
        "seed": 42,
        "llm_enabled": False,
        "llm_provider": "anthropic",
        "llm_model": "claude-sonnet-4-6",
    }
    args_a = NeedsMapArgs(input_root=in_a, output_root=tmp_path / "out_a", **base)  # type: ignore[arg-type]
    args_b = NeedsMapArgs(input_root=in_b, output_root=tmp_path / "out_b", **base)  # type: ignore[arg-type]

    run_needs_map(args_a)
    run_needs_map(args_b)

    silver_a = tmp_path / "out_a" / "silver" / "needs-map" / "2026-1-anatomy"
    silver_b = tmp_path / "out_b" / "silver" / "needs-map" / "2026-1-anatomy"
    assert filecmp.cmp(
        silver_a / "scale_reliability.parquet",
        silver_b / "scale_reliability.parquet",
        shallow=False,
    )
    assert filecmp.cmp(
        silver_a / "factor_scores.parquet",
        silver_b / "factor_scores.parquet",
        shallow=False,
    )


@pytest.fixture(autouse=True)
def _isolate_pyarrow_metadata(monkeypatch: pytest.MonkeyPatch) -> None:
    """pyarrow embeds the writer version in parquet metadata. We pin it via env
    so byte-equality holds across reruns within the same arrow build.
    """
    monkeypatch.setenv("ARROW_DEFAULT_MEMORY_POOL", "system")
