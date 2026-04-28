"""factor_scores_long sentiment + dictionary hydrate verification [T067-hydrate].

Phase 8 carry-over absorbed into Phase 9 polish per team-lead dispatch.
The Phase D sentiment lookup + dictionary categories now flow into
``factor_scores_long.csv``'s ``freetext_q61_*`` / ``freetext_q62_*``
fields. Without this hydrate the columns are always empty and the long
export is the only v0.1.1 surface that would silently miss the sentiment
result that ``manifest.sentiment`` + ``freetext_audit.parquet`` already
carry — a silent-skip pattern (FR-014 / spec L182).

Even on the dictionary-only path (``--no-roberta``), the categories column
is still populated when the keyword dictionary matched.

Spec: 003-needs-map-v0-1-1/tasks.md T067 (carry-over absorbed).
"""

from __future__ import annotations

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


def test_factor_scores_long_dict_categories_hydrated_no_roberta(tmp_path: Path) -> None:
    """``--no-roberta`` path: categories column populated from Phase D dict."""
    from needs_map.pipeline import NeedsMapArgs, run_needs_map

    args = NeedsMapArgs(
        semester="2026-1",
        course_slug="anatomy",
        phases=frozenset({"A", "B", "C", "D", "E"}),
        input_root=_stage(tmp_path / "in"),
        output_root=tmp_path / "out",
        seed=42,
        llm_enabled=False,
        llm_provider="anthropic",
        llm_model="claude-sonnet-4-6",
        roberta_enabled=False,
    )
    run_needs_map(args)
    long_csv = (
        tmp_path / "out" / "gold" / "needs-map" / "2026-1-anatomy" / "factor_scores_long.csv"
    )
    assert long_csv.is_file()
    df = pd.read_csv(long_csv)

    # At least one of q61/q62 categories should be populated for the cohort
    # (silver_minimal carries Korean anxiety/experience freetext that the
    # dictionary matches for several students).
    q61_filled = df["freetext_q61_categories"].dropna().astype(str).str.len()
    q62_filled = df["freetext_q62_categories"].dropna().astype(str).str.len()
    total_chars = int(q61_filled.sum()) + int(q62_filled.sum())
    assert total_chars > 0, (
        "factor_scores_long must hydrate at least one freetext "
        "categories column under --no-roberta"
    )

    # Sentiment fields stay empty when RoBERTa is disabled (no model run).
    assert df["freetext_q61_negativity"].dropna().empty
    assert df["freetext_q61_top_emotion"].dropna().empty
    assert df["freetext_q62_negativity"].dropna().empty
    assert df["freetext_q62_top_emotion"].dropna().empty


def test_factor_scores_long_categories_sourced_from_dictionary(tmp_path: Path) -> None:
    """Categories in the long export must equal Phase D ``matched_categories``."""
    from needs_map.pipeline import NeedsMapArgs, run_needs_map

    args = NeedsMapArgs(
        semester="2026-1",
        course_slug="anatomy",
        phases=frozenset({"A", "B", "C", "D", "E"}),
        input_root=_stage(tmp_path / "in"),
        output_root=tmp_path / "out",
        seed=42,
        llm_enabled=False,
        llm_provider="anthropic",
        llm_model="claude-sonnet-4-6",
        roberta_enabled=False,
    )
    run_needs_map(args)

    silver = tmp_path / "out" / "silver" / "needs-map" / "2026-1-anatomy"
    gold = tmp_path / "out" / "gold" / "needs-map" / "2026-1-anatomy"
    ft = pd.read_parquet(silver / "free_text_categorization.parquet")
    long_df = pd.read_csv(gold / "factor_scores_long.csv")

    # Pick the first responder that has a non-empty matched_categories on
    # an anxiety_freetext or experience_freetext item; assert the long
    # export's categories field is the ';'-joined form.
    for _, row in ft.iterrows():
        cats = row["matched_categories"]
        if not isinstance(cats, list) or not cats:
            cats_list = list(cats) if cats is not None else []
        else:
            cats_list = list(cats)
        if not cats_list:
            continue
        item = str(row["item_id"]).lower()
        if "anxiety" in item or "q61" in item:
            field = "freetext_q61_categories"
        elif "experience" in item or "q62" in item:
            field = "freetext_q62_categories"
        else:
            continue
        long_row = long_df[long_df["student_id"].astype(str) == str(row["student_id"])].iloc[0]
        # Categories may aggregate from multiple items into the same area —
        # require ALL the matched_categories to appear in the joined string.
        joined = str(long_row[field])
        for cat in cats_list:
            assert cat in joined
        return  # one verified is enough; spot-check pattern

    raise AssertionError(
        "fixture had no dictionary-matched freetext rows — cannot exercise hydrate"
    )
