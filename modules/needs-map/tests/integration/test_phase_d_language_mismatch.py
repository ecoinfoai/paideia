"""Phase D dictionary language mismatch warning (T116, FR-023, adversary P-7).

Synthesize a Silver fixture variant where every freetext response is in English.
Korean dictionary 'ko' will produce match_rate < 0.3, flipping
``manifest.dictionary_language_mismatch_warning`` to True.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

_FIXTURE_ROOT = Path("modules/needs-map/tests/fixtures/silver_minimal")
_FULL_MAPPING = Path("modules/needs-map/tests/fixtures/mappings/anatomy_full.diagnostic.yaml")


def _stage_with_english_freetext(tmp_path: Path) -> Path:
    silver_dir = tmp_path / "silver" / "immersio" / "2026-1-anatomy"
    silver_dir.mkdir(parents=True)
    shutil.copy(
        _FIXTURE_ROOT / "silver" / "immersio" / "2026-1-anatomy" / "student_master.parquet",
        silver_dir / "student_master.parquet",
    )

    # Load original diagnostic_response and rewrite freetext value_text → English
    src = pd.read_parquet(
        _FIXTURE_ROOT / "silver" / "immersio" / "2026-1-anatomy" / "diagnostic_response.parquet"
    )
    english_replacements = [
        "I am too busy with my part-time job",
        "Hard to memorize all anatomy terms",
        "Stress about exams is overwhelming",
        "I work nights so studying is hard",
        "Anxiety keeps me from concentrating",
        "Too many lectures in a single week",
        "I commute two hours every day",
        "Family responsibilities take priority",
        "English is not my first language",
    ]
    is_freetext = src["axis_kind"] == "freetext"
    freetext_idxs = src.index[is_freetext].tolist()
    for i, idx in enumerate(freetext_idxs):
        src.at[idx, "value_text"] = english_replacements[i % len(english_replacements)]

    pq.write_table(pa.Table.from_pandas(src), silver_dir / "diagnostic_response.parquet")

    mapping_dir = tmp_path / "bronze" / "매핑"
    mapping_dir.mkdir(parents=True)
    shutil.copy(_FULL_MAPPING, mapping_dir / "anatomy.diagnostic.yaml")
    return tmp_path


def test_english_freetext_flips_language_mismatch_warning(tmp_path: Path) -> None:
    from needs_map.pipeline import NeedsMapArgs, run_needs_map

    args = NeedsMapArgs(
        semester="2026-1",
        course_slug="anatomy",
        phases=frozenset({"A", "B", "C", "D"}),
        input_root=_stage_with_english_freetext(tmp_path / "in"),
        output_root=tmp_path / "out",
        seed=42,
        llm_enabled=False,
        llm_provider="anthropic",
        llm_model="claude-sonnet-4-6",
    )
    manifest = run_needs_map(args)
    assert manifest.dictionary_language_mismatch_warning is True
    assert manifest.free_text_dictionary_match_rate is not None
    assert manifest.free_text_dictionary_match_rate < 0.3
