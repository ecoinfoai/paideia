"""Phase C with LLM failing: fallback to rule labels (T065)."""

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


def test_llm_failure_falls_back_with_manifest_record(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """All LLM calls timeout → naming_source='llm_fallback' + manifest llm_calls
    failure_kinds.timeout == k_used.
    """
    from needs_map import pipeline as pipeline_mod
    from needs_map.pipeline import NeedsMapArgs, run_needs_map

    class _FakeTimeout:
        class _Chat:
            class _Completions:
                def create(self, **_: object) -> object:
                    import httpx

                    raise httpx.TimeoutException("simulated")

            completions = _Completions()

        chat = _Chat()

    monkeypatch.setattr(pipeline_mod, "make_client", lambda **_kw: _FakeTimeout(), raising=False)

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
    naming_stats = [s for s in manifest.llm_calls if s.site == "cluster_naming"]
    assert len(naming_stats) == 1
    assert naming_stats[0].succeeded == 0
    assert naming_stats[0].fallback >= 1
    assert naming_stats[0].failure_kinds.get("timeout", 0) >= 1
