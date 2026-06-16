"""T069 — 2026-1 anatomy 실데이터 e2e (Phase 9 인수 게이트, SC-003/SC-010).

Skipif-gated: only runs when the operator's silver 4종 (student_master,
exam_result, exam_item, diagnostic_response) are present at
``data/silver/immersio/2026-1-anatomy/``. Otherwise the test is skipped
so CI hosts without the restricted dataset still pass.

Verifies:
  * pipeline 단일 호출 끝까지 완주 (exit 0)
  * 9 산출 파일 모두 land
  * 60초 이내 (SC-003 budget)
  * legacy_diff.md 와 legacy xlsx 비교 결과 존재 (SC-010)
"""

from __future__ import annotations

import time
from pathlib import Path

import pytest
from immersio import fonts as _fonts
from immersio.analyze.pipeline import PipelineArgs, run_immersio_phase1

REPO_ROOT = Path(__file__).resolve().parents[4]
SILVER_ANATOMY = REPO_ROOT / "data" / "silver" / "immersio" / "2026-1-anatomy"
LEGACY_XLSX = REPO_ROOT / "data" / "silver" / "legacy" / "중간고사_분석결과.xlsx"

_REQUIRED_SILVER_FILES = (
    "student_master.parquet",
    "exam_result.parquet",
    "exam_item.parquet",
    "diagnostic_response.parquet",
)


def _silver_complete() -> bool:
    return all((SILVER_ANATOMY / f).is_file() for f in _REQUIRED_SILVER_FILES)


pytestmark = pytest.mark.skipif(
    not _silver_complete(),
    reason=(
        "real anatomy silver 4종 부재 → skip. "
        "Run `immersio ingest --bronze-dir data/bronze --output-key 2026-1-anatomy` "
        "first to populate the silver dir."
    ),
)


@pytest.fixture(autouse=True)
def _patch_fonts(monkeypatch: pytest.MonkeyPatch) -> None:
    import matplotlib

    matplotlib.use("Agg")
    from matplotlib import font_manager

    deja_vu = Path(font_manager.findfont("DejaVu Sans", fallback_to_default=True))
    monkeypatch.setattr(_fonts, "resolve_korean_font_paths", lambda: (deja_vu, deja_vu))


def _make_args(*, gold_root: Path, legacy: Path | None) -> PipelineArgs:
    return PipelineArgs(
        semester="2026-1",
        course_slug="anatomy",
        bronze_dir=REPO_ROOT / "data" / "bronze",
        silver_root=REPO_ROOT / "data" / "silver",
        gold_root=gold_root,
        legacy_xlsx=legacy,
        created_at_utc_override="2026-04-29T00:00:00Z",
        seed=42,
        no_needs_map=False,
    )


def test_anatomy_full_run_completes_under_60s(tmp_path: Path) -> None:
    """SC-003 + SC-010 — single command completes in < 60 s."""
    legacy = LEGACY_XLSX if LEGACY_XLSX.is_file() else None
    args = _make_args(gold_root=tmp_path / "gold", legacy=legacy)
    start = time.monotonic()
    rc = run_immersio_phase1(args)
    elapsed = time.monotonic() - start
    assert rc == 0, f"pipeline exit code {rc}"
    assert elapsed < 60.0, f"pipeline exceeded 60s budget: {elapsed:.1f}s (SC-003)"


def test_anatomy_full_run_lands_nine_artefacts(tmp_path: Path) -> None:
    """SC-010 — 9 산출 파일 모두 생성."""
    legacy = LEGACY_XLSX if LEGACY_XLSX.is_file() else None
    args = _make_args(gold_root=tmp_path / "gold", legacy=legacy)
    rc = run_immersio_phase1(args)
    assert rc == 0
    gold_dir = tmp_path / "gold" / "immersio" / "2026-1-anatomy"
    expected = [
        "시험분석결과.xlsx",
        "시험품질보고서.md",
        "시험품질보고서.pdf",
        "legacy_diff.md",
        "manifest.json",
        "figs/fig1_전체성적_히스토그램.png",
        "figs/fig2_메타데이터별_정답률.png",
    ]
    for rel in expected:
        path = gold_dir / rel
        assert path.is_file(), f"missing artefact: {rel}"


def test_anatomy_legacy_diff_renders_with_real_legacy(tmp_path: Path) -> None:
    """SC-010 — legacy_diff.md surfaces when both legacy + immersio xlsx exist."""
    if not LEGACY_XLSX.is_file():
        pytest.skip("legacy xlsx not present in this environment")
    args = _make_args(gold_root=tmp_path / "gold", legacy=LEGACY_XLSX)
    rc = run_immersio_phase1(args)
    assert rc == 0
    legacy_diff = tmp_path / "gold" / "immersio" / "2026-1-anatomy" / "legacy_diff.md"
    body = legacy_diff.read_text(encoding="utf-8")
    assert "총 비교 셀" in body
    assert "차이 발견" in body
    assert "immersio" in body
