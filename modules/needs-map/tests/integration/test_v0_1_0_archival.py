"""v0.1.0 → v0.1.1 archival migration test [T063].

SC-008 + FR-034: a v0.1.1 pipeline run on a directory whose previous
output carries a v0.1.0-shape ``manifest.json`` (``schema_version:
"1.0.0"``) MUST move every prior artifact into
``_archive/{ISO8601_UTC}__v1.0.0/`` (suffix per research.md §R-09) so
the v0.1.0 outputs are sortable / classifiable after the fact and v0.1.1
outputs do not commingle with the older shape.

The suffix is the operator's *only* signal that the archived directory
holds non-current schema artifacts; without it, an operator inspecting
``_archive/`` cannot tell which subdir holds v0.1.0 vs v0.1.1 vs future
shapes (research §R-09 — "사후 분류 가능").

Spec: 003-needs-map-v0-1-1/tasks.md T063; FR-034; SC-008; research §R-09.
"""

from __future__ import annotations

import json
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


def _seed_v0_1_0_outputs(silver_target: Path) -> None:
    """Plant a v0.1.0-shape manifest + stub silver shards.

    The bytes / fields don't matter for archival — the mover only inspects
    schema_version on the existing manifest.json. We write minimal
    placeholders for the four v0.1.0 silver shards plus the manifest.
    """
    silver_target.mkdir(parents=True, exist_ok=True)
    (silver_target / "scale_reliability.parquet").write_bytes(b"v0.1.0-stub-A")
    (silver_target / "factor_scores.parquet").write_bytes(b"v0.1.0-stub-B")
    (silver_target / "cluster_assignment.parquet").write_bytes(b"v0.1.0-stub-C")
    (silver_target / "free_text_categorization.parquet").write_bytes(b"v0.1.0-stub-D")
    (silver_target / "manifest.json").write_text(
        json.dumps({"schema_version": "1.0.0", "semester": "2026-1"}),
        encoding="utf-8",
    )


def test_v0_1_0_archival_suffix_marks_schema_version(tmp_path: Path) -> None:
    """Pre-existing v0.1.0 outputs are archived under ``__v1.0.0`` suffix."""
    from needs_map.pipeline import NeedsMapArgs, run_needs_map

    out_root = tmp_path / "out"
    silver_target = out_root / "silver" / "needs-map" / "2026-1-anatomy"
    _seed_v0_1_0_outputs(silver_target)

    # Sanity: the seed wrote into the canonical silver path.
    assert (silver_target / "manifest.json").is_file()

    args = NeedsMapArgs(
        semester="2026-1",
        course_slug="anatomy",
        phases=frozenset({"A", "B"}),  # cheapest path that still archives
        input_root=_stage(tmp_path / "in"),
        output_root=out_root,
        seed=42,
        llm_enabled=False,
        llm_provider="anthropic",
        llm_model="claude-sonnet-4-6",
        roberta_enabled=False,
    )
    manifest = run_needs_map(args)

    # (a) prior outputs were moved under _archive/{TS}__v1.0.0/
    assert manifest.previous_run_archive_path is not None
    archive_rel = manifest.previous_run_archive_path
    assert archive_rel.endswith("__v1.0.0"), (
        f"archive subdir missing __v1.0.0 suffix: {archive_rel}"
    )
    archive_dir = silver_target / archive_rel
    assert archive_dir.is_dir(), f"missing archive subdir: {archive_dir}"
    # The original v0.1.0 stubs landed inside it.
    for name in (
        "scale_reliability.parquet",
        "factor_scores.parquet",
        "cluster_assignment.parquet",
        "free_text_categorization.parquet",
        "manifest.json",
    ):
        assert (archive_dir / name).is_file(), f"{name} not archived"
    # Confirm the archived manifest.json still holds the v0.1.0 schema_version.
    archived_manifest = json.loads((archive_dir / "manifest.json").read_text(encoding="utf-8"))
    assert archived_manifest["schema_version"] == "1.0.0"

    # (b) canonical paths now hold v0.1.1 outputs (manifest schema_version 1.1.0)
    new_manifest = json.loads((silver_target / "manifest.json").read_text(encoding="utf-8"))
    assert new_manifest["schema_version"] == "1.1.0"
    # Phase A+B silver shards landed.
    assert (silver_target / "scale_reliability.parquet").is_file()
    assert (silver_target / "factor_scores.parquet").is_file()

    # (c) original directory is *not* commingled — v0.1.0 stubs are gone
    # from the canonical path (the only file with that name now is the
    # v0.1.1 shard, byte-different from the seed).
    assert (silver_target / "scale_reliability.parquet").read_bytes() != b"v0.1.0-stub-A"


def test_v0_1_1_archival_suffix_marks_schema_version(tmp_path: Path) -> None:
    """Pre-existing v0.1.1 outputs are archived under ``__v1.1.0`` suffix.

    Verifies the suffix is parametric on schema_version, not hard-coded
    for the v1.0.0 case. A second v0.1.1 run after a successful first
    v0.1.1 run should produce ``__v1.1.0`` so an operator inspecting
    ``_archive/`` after multiple iterations can still classify.
    """
    from needs_map.pipeline import NeedsMapArgs, run_needs_map

    args = NeedsMapArgs(
        semester="2026-1",
        course_slug="anatomy",
        phases=frozenset({"A", "B"}),
        input_root=_stage(tmp_path / "in"),
        output_root=tmp_path / "out",
        seed=42,
        llm_enabled=False,
        llm_provider="anthropic",
        llm_model="claude-sonnet-4-6",
        roberta_enabled=False,
    )
    run_needs_map(args)  # first run lays down v0.1.1 outputs
    manifest_second = run_needs_map(args)

    assert manifest_second.previous_run_archive_path is not None
    assert manifest_second.previous_run_archive_path.endswith("__v1.1.0"), (
        f"v0.1.1 → v0.1.1 archive subdir missing __v1.1.0 suffix: "
        f"{manifest_second.previous_run_archive_path}"
    )
