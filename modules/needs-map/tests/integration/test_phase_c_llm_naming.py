"""Phase C with LLM naming: monkeypatched anthropic client → naming_source='llm' (T064)."""

from __future__ import annotations

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


def test_llm_naming_succeeds(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from needs_map.clustering import naming as naming_mod
    from needs_map.pipeline import NeedsMapArgs, run_needs_map

    class _FakeOk:
        class _Chat:
            class _Completions:
                def create(self, **_: object) -> naming_mod.ClusterNameOut:
                    return naming_mod.ClusterNameOut(label="LLM_test")

            completions = _Completions()

        chat = _Chat()

    # Replace make_client in the pipeline import path so llm_enabled triggers
    # the fake client without any real network.
    from needs_map import pipeline as pipeline_mod

    monkeypatch.setattr(
        pipeline_mod, "make_client", lambda **_kw: _FakeOk(), raising=False
    )

    args = NeedsMapArgs(
        semester="2026-1",
        course_slug="anatomy",
        phases=frozenset({"A", "B", "C"}),
        input_root=_stage(tmp_path / "in"),
        output_root=tmp_path / "out",
        seed=42,
        llm_enabled=True,
        llm_provider="anthropic",
        llm_model="claude-sonnet-4-6",
    )
    manifest = run_needs_map(args)
    # LLM enabled and every cluster call succeeded → llm_calls accounting present
    assert manifest.llm_provider == "anthropic"
    assert manifest.llm_model == "claude-sonnet-4-6"
    assert any(stat.site == "cluster_naming" and stat.succeeded > 0 for stat in manifest.llm_calls)
