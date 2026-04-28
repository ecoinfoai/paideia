"""Full-pipeline byte-equal determinism test [T062].

SC-007 + FR-035: two consecutive runs of the full Phase A-F pipeline with
the same seed and pinned ``created_at_utc`` MUST produce byte-identical
artifacts across every output surface a downstream module/operator can
read:

- ``cards/*.pdf`` (one per student)
- ``manual.pdf`` (operator manual)
- ``group_distribution.pdf``
- ``factor_scores_long.csv`` + ``axis_summary.csv``
- ``factor_scores_long.yaml`` + ``axis_summary.yaml``
- silver parquet shards (scale_reliability, factor_scores,
  cluster_assignment, free_text_categorization)
- ``freetext_audit.parquet``
- (radar PNGs are embedded inside the per-student PDFs and so are
  covered transitively by ``cards/*.pdf`` byte-equality)

manifest.json is *excluded* from byte-equal comparison: although every
content field is deterministic, the run timestamp is allowed to differ
across two invocations. Determinism keys (font sha256, model sha256,
tokenizer hash, NEGATIVE_LABELS hash, mapping yaml hash, random_seed)
are checked separately on the manifest model objects.

Spec: 003-needs-map-v0-1-1/tasks.md T062; FR-035; SC-007.
"""

from __future__ import annotations

import filecmp
import shutil
from pathlib import Path

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


def _silver(out_root: Path) -> Path:
    return out_root / "silver" / "needs-map" / "2026-1-anatomy"


def _gold(out_root: Path) -> Path:
    return out_root / "gold" / "needs-map" / "2026-1-anatomy"


def _assert_byte_equal(path_a: Path, path_b: Path) -> None:
    assert path_a.is_file(), f"missing {path_a}"
    assert path_b.is_file(), f"missing {path_b}"
    assert filecmp.cmp(path_a, path_b, shallow=False), (
        f"bytes differ: {path_a.name}"
    )


def test_full_pipeline_byte_equal_two_runs(tmp_path: Path) -> None:
    """Two full Phase A-F runs produce byte-identical exports + parquets + PDFs."""
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
        roberta_enabled=False,  # dictionary-only path so no kote cache needed
        created_at_utc="2026-04-28T00:00:00Z",
    )
    args_b = args_a.model_copy(
        update={
            "input_root": _stage(tmp_path / "in_b"),
            "output_root": tmp_path / "out_b",
        }
    )
    run_needs_map(args_a)
    run_needs_map(args_b)

    silver_a, silver_b = _silver(tmp_path / "out_a"), _silver(tmp_path / "out_b")
    gold_a, gold_b = _gold(tmp_path / "out_a"), _gold(tmp_path / "out_b")

    # silver parquet shards (4) + freetext_audit (v0.1.1 new output)
    for name in (
        "scale_reliability.parquet",
        "factor_scores.parquet",
        "cluster_assignment.parquet",
        "free_text_categorization.parquet",
        "freetext_audit.parquet",
    ):
        _assert_byte_equal(silver_a / name, silver_b / name)

    # gold flat exports (v0.1.1 new outputs) + group_distribution + manual
    for name in (
        "factor_scores_long.csv",
        "factor_scores_long.yaml",
        "axis_summary.csv",
        "axis_summary.yaml",
        "group_distribution.pdf",
        "needs-map_manual.pdf",
    ):
        _assert_byte_equal(gold_a / name, gold_b / name)

    # cards/*.pdf — every per-student PDF (radar PNGs embedded inside)
    cards_a = sorted(p.name for p in (gold_a / "cards").iterdir())
    cards_b = sorted(p.name for p in (gold_b / "cards").iterdir())
    assert cards_a == cards_b, "card filenames differ"
    for name in cards_a:
        _assert_byte_equal(gold_a / "cards" / name, gold_b / "cards" / name)


def test_full_pipeline_determinism_keys_match(tmp_path: Path) -> None:
    """Determinism keys in manifest match across two runs (FR-035).

    Compares the hash fingerprints (font, mapping_yaml, model_sha256,
    tokenizer_vocab_sha256, negative_label_subset_sha256, random_seed)
    that operators use to verify byte-equality preconditions. The
    timestamp field ``created_at_utc`` is intentionally excluded.
    """
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
        roberta_enabled=False,
        created_at_utc="2026-04-28T00:00:00Z",
    )
    args_b = args_a.model_copy(
        update={
            "input_root": _stage(tmp_path / "in_b"),
            "output_root": tmp_path / "out_b",
        }
    )
    manifest_a = run_needs_map(args_a)
    manifest_b = run_needs_map(args_b)

    # Mapping yaml hash (input fingerprint)
    assert (
        manifest_a.inputs.diagnostic_mapping_sha256
        == manifest_b.inputs.diagnostic_mapping_sha256
    )
    # Font hashes (regular + bold)
    assert manifest_a.font_resolution is not None
    assert manifest_b.font_resolution is not None
    assert (
        manifest_a.font_resolution.regular_sha256
        == manifest_b.font_resolution.regular_sha256
    )
    assert (
        manifest_a.font_resolution.bold_sha256
        == manifest_b.font_resolution.bold_sha256
    )
    # Sentiment fallback path: model hashes are None on both sides.
    assert manifest_a.sentiment is not None
    assert manifest_b.sentiment is not None
    assert manifest_a.sentiment.model_sha256 == manifest_b.sentiment.model_sha256
    assert (
        manifest_a.sentiment.tokenizer_vocab_sha256
        == manifest_b.sentiment.tokenizer_vocab_sha256
    )
    assert (
        manifest_a.sentiment.negative_label_subset_sha256
        == manifest_b.sentiment.negative_label_subset_sha256
    )
