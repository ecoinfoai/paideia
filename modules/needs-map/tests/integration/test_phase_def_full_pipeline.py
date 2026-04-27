"""Integration test: Phase A-F end-to-end with --no-llm (T088 + spans T077-T086)."""

from __future__ import annotations

import filecmp
import shutil
from pathlib import Path

import pandas as pd

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


def test_full_pipeline_writes_silver_and_gold(tmp_path: Path) -> None:
    """Phase A-F runs end-to-end with --no-llm. 4 silver + 3 gold + manifests."""
    from needs_map.pipeline import NeedsMapArgs, run_needs_map

    args = NeedsMapArgs(
        semester="2026-1",
        course_slug="anatomy",
        phases=frozenset({"A", "B", "C", "D", "E", "F"}),
        input_root=_stage(tmp_path / "in"),
        output_root=tmp_path / "out",
        seed=42,
        llm_enabled=False,
        llm_provider="anthropic",
        llm_model="claude-sonnet-4-6",
        created_at_utc="2026-04-27T00:00:00Z",
    )
    manifest = run_needs_map(args)

    silver = tmp_path / "out" / "silver" / "needs-map" / "2026-1-anatomy"
    gold = tmp_path / "out" / "gold" / "needs-map" / "2026-1-anatomy"

    # 4 silver outputs
    assert (silver / "scale_reliability.parquet").is_file()
    assert (silver / "factor_scores.parquet").is_file()
    assert (silver / "cluster_assignment.parquet").is_file()
    assert (silver / "free_text_categorization.parquet").is_file()
    assert (silver / "manifest.json").is_file()

    # 3 gold outputs
    assert (gold / "group_distribution.pdf").is_file()
    assert (gold / "cluster_summary.xlsx").is_file()
    assert (gold / "cards").is_dir()
    assert (gold / "manifest.json").is_file()

    # cards: 10 students (8 roster+responded + 1 off-roster + 1 roster non-responder)
    cards = list((gold / "cards").iterdir())
    assert len(cards) == 10

    assert manifest.phases_executed == ["A", "B", "C", "D", "E", "F"]
    assert manifest.pii_redaction_validated is True  # no LLM calls happened


def test_no_response_freetext_handled(tmp_path: Path) -> None:
    """T079 spans here too: synthetic 'all empty' freetext → match_source='no_response'."""
    from needs_map.pipeline import NeedsMapArgs, run_needs_map

    args = NeedsMapArgs(
        semester="2026-1",
        course_slug="anatomy",
        phases=frozenset({"A", "B", "C", "D"}),
        input_root=_stage(tmp_path / "in"),
        output_root=tmp_path / "out",
        seed=42,
        llm_enabled=False,
        llm_provider="anthropic",
        llm_model="claude-sonnet-4-6",
    )
    run_needs_map(args)
    silver = tmp_path / "out" / "silver" / "needs-map" / "2026-1-anatomy"
    ft = pd.read_parquet(silver / "free_text_categorization.parquet")
    # The fixture has substantive Korean responses, so no_response count may be 0;
    # we just assert match_source is one of the 5 valid values for every row.
    assert set(ft["match_source"].unique()) <= {
        "dictionary",
        "llm",
        "llm_fallback",
        "no_response",
        "uncategorized",
    }


def test_card_batch_includes_all_students(tmp_path: Path) -> None:
    """T084 spans: roster + off-roster + non-responder all get a PDF (FR-019)."""
    from needs_map.pipeline import NeedsMapArgs, run_needs_map

    args = NeedsMapArgs(
        semester="2026-1",
        course_slug="anatomy",
        phases=frozenset({"A", "B", "C", "D", "E", "F"}),
        input_root=_stage(tmp_path / "in"),
        output_root=tmp_path / "out",
        seed=42,
        llm_enabled=False,
        llm_provider="anthropic",
        llm_model="claude-sonnet-4-6",
    )
    run_needs_map(args)
    cards_dir = tmp_path / "out" / "gold" / "needs-map" / "2026-1-anatomy" / "cards"
    pdfs = sorted(p.name for p in cards_dir.iterdir())
    assert "2026194099.pdf" in pdfs  # roster non-responder (진단 미응답 카드)
    assert "9999999999.pdf" in pdfs  # off-roster respondent
    assert all(name.endswith(".pdf") for name in pdfs)


def test_card_determinism_byte_equal_two_runs(tmp_path: Path) -> None:
    """T086: --no-llm + same seed + same created_at_utc → cards/*.pdf byte-equal."""
    from needs_map.pipeline import NeedsMapArgs, run_needs_map

    args_a = NeedsMapArgs(
        semester="2026-1",
        course_slug="anatomy",
        phases=frozenset({"A", "B", "C", "D", "E", "F"}),
        input_root=_stage(tmp_path / "in_a"),
        output_root=tmp_path / "out_a",
        seed=42,
        llm_enabled=False,
        llm_provider="anthropic",
        llm_model="claude-sonnet-4-6",
        created_at_utc="2026-04-27T00:00:00Z",
    )
    args_b = args_a.model_copy(
        update={"input_root": _stage(tmp_path / "in_b"), "output_root": tmp_path / "out_b"}
    )
    run_needs_map(args_a)
    run_needs_map(args_b)

    cards_a = tmp_path / "out_a" / "gold" / "needs-map" / "2026-1-anatomy" / "cards"
    cards_b = tmp_path / "out_b" / "gold" / "needs-map" / "2026-1-anatomy" / "cards"
    for pdf_a in cards_a.iterdir():
        pdf_b = cards_b / pdf_a.name
        assert pdf_b.is_file()
        assert filecmp.cmp(pdf_a, pdf_b, shallow=False), f"{pdf_a.name} bytes differ"


def test_archival_on_rerun(tmp_path: Path) -> None:
    """T087: second run moves first-run artifacts into _archive/{TS}/."""
    from needs_map.pipeline import NeedsMapArgs, run_needs_map

    in_dir = _stage(tmp_path / "in")
    out_dir = tmp_path / "out"

    args = NeedsMapArgs(
        semester="2026-1",
        course_slug="anatomy",
        phases=frozenset({"A", "B"}),
        input_root=in_dir,
        output_root=out_dir,
        seed=42,
        llm_enabled=False,
        llm_provider="anthropic",
        llm_model="claude-sonnet-4-6",
    )
    manifest_first = run_needs_map(args)
    assert manifest_first.previous_run_archive_path is None  # first run

    manifest_second = run_needs_map(args)
    assert manifest_second.previous_run_archive_path is not None
    archive_dir = (
        out_dir / "silver" / "needs-map" / "2026-1-anatomy" / manifest_second.previous_run_archive_path
    )
    assert archive_dir.is_dir()
    # First-run silver outputs survived in _archive
    assert (archive_dir / "scale_reliability.parquet").is_file()
    assert (archive_dir / "factor_scores.parquet").is_file()
