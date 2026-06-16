"""Phase 8 adversary follow-ups (P5 needs-map partial + P7 created_at_utc).

P5: needs-map silver dir exists with PARTIAL files → fail-fast exit 3
    (silent degraded join forbidden).
P7: --created-at-utc with calendar fields out of range (regex passes
    but datetime.fromisoformat refuses) → fail-fast exit 1.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest
from immersio import fonts as _fonts
from immersio.analyze.pipeline import (
    PipelineArgs,
    SilverNotFoundError,
    run_immersio_phase1,
)
from immersio.cli.main import app as cli_app


@pytest.fixture(autouse=True)
def _patch_fonts(monkeypatch: pytest.MonkeyPatch) -> None:
    import matplotlib

    matplotlib.use("Agg")
    from matplotlib import font_manager

    deja_vu = Path(font_manager.findfont("DejaVu Sans", fallback_to_default=True))
    monkeypatch.setattr(_fonts, "resolve_korean_font_paths", lambda: (deja_vu, deja_vu))


def _seed_silver(silver_dir: Path) -> None:
    silver_dir.mkdir(parents=True, exist_ok=True)
    items = pd.DataFrame(
        [
            {
                "semester": "2026-1",
                "course_slug": "anatomy",
                "item_no": 1,
                "chapter": "1장. 서론",
                "week": 1,
                "item_type": "지식축적",
                "difficulty_level": 2,
                "expected_difficulty": "보통",
                "source": "교과서",
                "correct_answer": 1,
                "answer_key": "1",
                "points": 1.0,
                "bloom": "knowledge",
                "text": "문항 1",
            }
        ]
    )
    items.to_parquet(silver_dir / "exam_item.parquet")
    masters = [
        {
            "student_id": "2026100001",
            "semester": "2026-1",
            "course_slug": "anatomy",
            "on_roster": True,
            "section": "A",
            "name_kr": "테스트",
            "diagnostic_responded": True,
            "exam_taken": True,
            "exam_absent": False,
            "attendance_recorded": True,
            "exam_total_score": 1.0,
            "exam_max_score": 1.0,
            "attendance_present_count": None,
            "attendance_absent_count": None,
            "attendance_late_count": None,
            "attendance_excused_count": None,
            "axis_scores": {"placeholder": 0.0},
        }
    ]
    pd.DataFrame(masters).to_parquet(silver_dir / "student_master.parquet")
    pd.DataFrame(
        [
            {
                "student_id": "2026100001",
                "semester": "2026-1",
                "course_slug": "anatomy",
                "item_no": 1,
                "response": "1",
                "is_correct": True,
                "is_omit": False,
            }
        ]
    ).to_parquet(silver_dir / "exam_result.parquet")
    pd.DataFrame(
        [
            {
                "student_id": "2026100001",
                "semester": "2026-1",
                "course_slug": "anatomy",
                "axis": "interest_topics",
                "axis_kind": "multiselect_onehot",
                "option_key": "혈액과 면역",
                "value_int": None,
                "value_bool": True,
                "value_text": None,
                "source_column": "Q11",
            }
        ]
    ).to_parquet(silver_dir / "diagnostic_response.parquet")


def test_p5_partial_needs_map_silver_raises(tmp_path: Path) -> None:
    """needs-map silver with one file present + others missing → exit 3."""
    silver_root = tmp_path / "silver"
    silver_dir = silver_root / "immersio" / "2026-1-anatomy"
    _seed_silver(silver_dir)

    # Plant a partial needs-map silver dir: just diagnostic_response.parquet.
    needs_map_dir = silver_root / "needs-map" / "2026-1-anatomy"
    needs_map_dir.mkdir(parents=True)
    (needs_map_dir / "diagnostic_response.parquet").write_bytes(b"not really parquet")
    # factor_scores / cluster_assignment / scale_reliability all missing

    args = PipelineArgs(
        semester="2026-1",
        course_slug="anatomy",
        bronze_dir=tmp_path / "bronze",
        silver_root=silver_root,
        gold_root=tmp_path / "gold",
        legacy_xlsx=None,
        created_at_utc_override="2026-04-29T00:00:00Z",
        seed=42,
        no_needs_map=False,
    )
    with pytest.raises(SilverNotFoundError) as exc_info:
        run_immersio_phase1(args)
    msg = str(exc_info.value)
    assert "partial" in msg
    assert "diagnostic_response.parquet" in msg
    assert "factor_scores.parquet" in msg


def test_p5_full_needs_map_absence_falls_back_gracefully(tmp_path: Path) -> None:
    """No needs-map silver dir at all → graceful fallback (no raise, exit 0)."""
    silver_root = tmp_path / "silver"
    silver_dir = silver_root / "immersio" / "2026-1-anatomy"
    _seed_silver(silver_dir)

    args = PipelineArgs(
        semester="2026-1",
        course_slug="anatomy",
        bronze_dir=tmp_path / "bronze",
        silver_root=silver_root,
        gold_root=tmp_path / "gold",
        legacy_xlsx=None,
        created_at_utc_override="2026-04-29T00:00:00Z",
        seed=42,
        no_needs_map=False,
    )
    # No needs-map dir created — pipeline should fall back to immersio's
    # own diagnostic_response.parquet AND emit a manifest note.
    rc = run_immersio_phase1(args)
    assert rc == 0


def test_p7_calendar_out_of_range_rejected_by_cli(tmp_path: Path, capsys) -> None:
    """--created-at-utc='2026-13-99T...Z' passes regex but fromisoformat rejects it."""
    silver_root = tmp_path / "silver"
    silver_dir = silver_root / "immersio" / "2026-1-anatomy"
    _seed_silver(silver_dir)

    rc = cli_app(
        [
            "analyze",
            "--semester",
            "2026-1",
            "--course",
            "anatomy",
            "--silver-dir",
            str(silver_root),
            "--gold-dir",
            str(tmp_path / "gold"),
            "--legacy-xlsx",
            str(tmp_path / "no-such-legacy.xlsx"),
            "--created-at-utc",
            "2026-13-99T25:61:61Z",
            "--no-needs-map",
        ]
    )
    assert rc == 1
    captured = capsys.readouterr()
    assert "invalid_created_at_utc" in captured.err
    assert "calendar fields out of range" in captured.err


def test_p7_valid_iso8601_accepted_by_cli(tmp_path: Path) -> None:
    silver_root = tmp_path / "silver"
    silver_dir = silver_root / "immersio" / "2026-1-anatomy"
    _seed_silver(silver_dir)

    rc = cli_app(
        [
            "analyze",
            "--semester",
            "2026-1",
            "--course",
            "anatomy",
            "--silver-dir",
            str(silver_root),
            "--gold-dir",
            str(tmp_path / "gold"),
            "--legacy-xlsx",
            str(tmp_path / "no-such-legacy.xlsx"),
            "--created-at-utc",
            "2026-04-29T00:00:00Z",
            "--no-needs-map",
        ]
    )
    assert rc == 0


def test_p7_regex_fail_rejected_by_cli(tmp_path: Path, capsys) -> None:
    """--created-at-utc='not-a-date' fails the regex tier."""
    silver_root = tmp_path / "silver"
    silver_dir = silver_root / "immersio" / "2026-1-anatomy"
    _seed_silver(silver_dir)

    rc = cli_app(
        [
            "analyze",
            "--semester",
            "2026-1",
            "--course",
            "anatomy",
            "--silver-dir",
            str(silver_root),
            "--gold-dir",
            str(tmp_path / "gold"),
            "--legacy-xlsx",
            str(tmp_path / "no-such-legacy.xlsx"),
            "--created-at-utc",
            "not-a-date",
            "--no-needs-map",
        ]
    )
    assert rc == 1
    captured = capsys.readouterr()
    assert "invalid_created_at_utc" in captured.err
    assert "ISO 8601 UTC" in captured.err
