"""T029 — US1 retro-mester pipeline: load → detect → rank → output.

Entry point: ``run_retro(...) -> int`` (exit code).

Steps:
1. Resolve input paths under ``data_root``.
2. Load combined + items + exam_spec + config; call ``reconcile_config``.
3. ``detect_gaps`` → ``rank_changes``.
4. Write Silver (빈틈표.parquet, 변경권고.parquet) and Gold
   (CQI회고보고서.md/.pdf, 회고분석.xlsx, manifest_retro.json).

Determinism
-----------
``DETERMINISTIC_EPOCH`` is the same fixed datetime used in
``examen/pipeline.py`` (``_PINNED_WHEN = datetime(2026, 1, 1, 0, 0, 0, UTC)``).
All Gold artefacts except ``manifest_retro.json`` use this constant so two
runs with identical inputs produce byte-identical files.
``manifest_retro.json`` uses real ``datetime.now(UTC)`` for
``generated_at_utc`` — it is the ONLY non-deterministic field (SC-009).

Exit codes
----------
0 — success
2 — ``InputError`` (missing file / bad config / key mismatch)
3 — unexpected integrity / runtime error
"""

from __future__ import annotations

import datetime
import hashlib
from pathlib import Path

from retro_mester.gaps.detect import detect_gaps
from retro_mester.load import (
    InputError,
    load_combined,
    load_config,
    load_exam_spec,
    load_items,
    reconcile_config,
)
from retro_mester.output.manager import archive_existing, atomic_write_text
from retro_mester.output.manifest import build_manifest, write_manifest
from retro_mester.output.paths import bronze_dir, gold_dir, output_key, silver_dir
from retro_mester.output.report_md import build_report_md
from retro_mester.output.report_pdf import write_report_pdf
from retro_mester.output.silver import write_silver
from retro_mester.output.xlsx import write_xlsx
from retro_mester.prioritize.rank import rank_changes

# ---------------------------------------------------------------------------
# Module / schema versions
# ---------------------------------------------------------------------------

_MODULE_VERSION = "0.1.0"
_SCHEMA_VERSION = "0.1.0"

# ---------------------------------------------------------------------------
# DETERMINISTIC_EPOCH — matches examen/pipeline.py ``_PINNED_WHEN``.
# All Gold artefacts (xlsx, pdf, md) use this constant so two runs on
# identical inputs produce byte-identical files regardless of wall-clock time.
# ``manifest_retro.json`` is the sole carrier of the real run timestamp.
# ---------------------------------------------------------------------------

DETERMINISTIC_EPOCH: datetime.datetime = datetime.datetime(
    2026, 1, 1, 0, 0, 0, tzinfo=datetime.timezone.utc
)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _file_sha256(path: Path) -> str:
    """Return ``sha256:<hex>`` digest for ``path``."""
    data = path.read_bytes()
    return "sha256:" + hashlib.sha256(data).hexdigest()


def _resolve_immersio_silver(
    semester: str, course: str, data_root: Path
) -> tuple[Path, Path]:
    """Return (combined_path, items_path) in the immersio Silver tier.

    Args:
        semester: Semester code, e.g. ``"2026-1"``.
        course: Course slug, e.g. ``"anatomy"``.
        data_root: Root of the data hierarchy.

    Returns:
        Tuple of (진단×시험결합.parquet path, 문항통계.parquet path).
    """
    key = output_key(semester, course)
    base = data_root / "silver" / "immersio" / key
    return (
        base / "진단×시험결합.parquet",
        base / "문항통계.parquet",
    )


def _resolve_retro_bronze(
    semester: str, course: str, data_root: Path, config_path: str | None
) -> tuple[Path, Path, Path]:
    """Return (config_path, blueprint_path, curriculum_map_path) in Bronze.

    Args:
        semester: Semester code.
        course: Course slug.
        data_root: Root of the data hierarchy.
        config_path: Optional explicit override for the config YAML path.

    Returns:
        Tuple of (config, blueprint, curriculum_map) Paths.
    """
    bronze = bronze_dir(semester, course, data_root=data_root)
    cfg = Path(config_path) if config_path else bronze / "retro_config.yaml"
    bp = bronze / "blueprint.yaml"
    cm = bronze / "curriculum_map.yaml"
    return cfg, bp, cm


# ---------------------------------------------------------------------------
# Public pipeline function
# ---------------------------------------------------------------------------


def run_retro(
    *,
    semester: str,
    course: str,
    data_root: str = "data",
    config_path: str | None = None,
    prior_year: str | None = None,
    llm_mode: str = "off",
    require_llm: bool = False,
) -> int:
    """Run the full US1 retrospective analytics pipeline.

    Steps:
    1. Resolve all input paths under ``data_root``.
    2. Load combined + items + exam_spec + config; reconcile config.
    3. detect_gaps → rank_changes.
    4. Archive existing outputs (gold + silver retro dirs).
    5. Write Silver parquet + Gold md/pdf/xlsx + manifest.

    Args:
        semester: Semester code, e.g. ``"2026-1"``.
        course: Course slug, e.g. ``"anatomy"``.
        data_root: Root of the data hierarchy (default ``"data"``).
        config_path: Optional explicit path to ``retro_config.yaml``.
        prior_year: Prior-year semester for YoY alignment (not used in US1).
        llm_mode: LLM mode — ``"off"`` (US1), ``"subscription"``, or ``"api"``.
        require_llm: If True, exit 5 when LLM is unavailable (not used in US1).

    Returns:
        Integer exit code:
        - ``0`` — success
        - ``2`` — InputError (missing file / bad config / key mismatch)
        - ``3`` — unexpected integrity / runtime error
    """
    data_root_path = Path(data_root)

    try:
        return _run(
            semester=semester,
            course=course,
            data_root=data_root_path,
            config_path=config_path,
            prior_year=prior_year,
            llm_mode=llm_mode,
        )
    except InputError:
        return 2
    except Exception:
        return 3


def _run(
    *,
    semester: str,
    course: str,
    data_root: Path,
    config_path: str | None,
    prior_year: str | None,
    llm_mode: str,
) -> int:
    """Inner implementation — exceptions propagate to ``run_retro``'s handler.

    Args:
        semester: Semester code.
        course: Course slug.
        data_root: Resolved data root Path.
        config_path: Optional explicit config path override.
        prior_year: Prior-year semester (unused in US1).
        llm_mode: LLM mode string (unused in US1).

    Returns:
        0 on success; raises on failure.
    """
    # ------------------------------------------------------------------
    # Step 1: Resolve input paths
    # ------------------------------------------------------------------
    combined_path, items_path = _resolve_immersio_silver(semester, course, data_root)
    cfg_path, bp_path, cm_path = _resolve_retro_bronze(
        semester, course, data_root, config_path
    )

    # ------------------------------------------------------------------
    # Step 2: Load + reconcile
    # ------------------------------------------------------------------
    rows = load_combined(combined_path)
    combined_chapters: set[str] = set()
    for row in rows:
        combined_chapters.update(row.chapter_correct_rates.keys())

    items, _mismatch = load_items(items_path, combined_chapters=combined_chapters)

    blueprint, curriculum = load_exam_spec(bp_path, cm_path, semester, course)
    config = load_config(cfg_path)

    # Build chapter universe and student ID set for reconcile
    item_chapters: set[str] = {it.chapter for it in items}
    chapters: set[str] = combined_chapters | item_chapters

    student_ids: set[str] = {row.student_id for row in rows}

    reconcile_config(config, chapters, student_ids)

    # ------------------------------------------------------------------
    # Step 3: Detect gaps and rank changes
    # ------------------------------------------------------------------
    gaps = detect_gaps(rows, items, config)
    recs, uncovered_ratio = rank_changes(gaps, config)

    # ------------------------------------------------------------------
    # Step 4: Compute timestamps
    # ------------------------------------------------------------------
    # Real now() — used ONLY for archival dir names and manifest.generated_at_utc
    now_utc: datetime.datetime = datetime.datetime.now(datetime.timezone.utc)

    # DETERMINISTIC_EPOCH — used for all byte-comparable Gold artefacts
    when = DETERMINISTIC_EPOCH

    # ------------------------------------------------------------------
    # Step 5: Archive existing outputs (before writing new ones)
    # ------------------------------------------------------------------
    silver_out = silver_dir(semester, course, data_root=data_root)
    gold_out = gold_dir(semester, course, data_root=data_root)

    if silver_out.exists():
        archive_existing(silver_out, now_utc)
    if gold_out.exists():
        archive_existing(gold_out, now_utc)

    # Create output directories
    silver_out.mkdir(parents=True, exist_ok=True)
    gold_out.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    # Step 6: Write outputs (all-or-nothing: dirs are created only after
    #          analysis succeeds; any exception here propagates up)
    # ------------------------------------------------------------------

    # Silver
    write_silver(gaps, recs, silver_out)

    # Gold — Markdown
    md_text = build_report_md(recs, uncovered_ratio, gaps, semester, course)
    atomic_write_text(gold_out / "CQI회고보고서.md", md_text, encoding="utf-8")

    # Gold — PDF (uses DETERMINISTIC_EPOCH for SOURCE_DATE_EPOCH)
    write_report_pdf(md_text, gold_out / "CQI회고보고서.pdf", when)

    # Gold — xlsx (uses DETERMINISTIC_EPOCH for finalize_xlsx pinning)
    write_xlsx(gaps, recs, gold_out / "회고분석.xlsx", when)

    # Gold — manifest (uses real now_utc for generated_at_utc)
    inputs: dict[str, str] = {
        "combined": str(combined_path),
        "items": str(items_path),
        "config": str(cfg_path),
        "blueprint": str(bp_path),
        "curriculum_map": str(cm_path),
    }
    # Add SHA-256 fingerprints for existing input files
    input_hashes: dict[str, str] = {}
    for role, path_str in inputs.items():
        p = Path(path_str)
        if p.exists():
            input_hashes[role] = _file_sha256(p)

    thresholds: dict[str, float] = {
        "gap_threshold": config.gap_threshold,
        "low_discrimination_threshold": config.low_discrimination_threshold,
        "cognitive_cliff_drop": config.cognitive_cliff_drop,
    }

    counts: dict[str, float] = {
        "students": float(len(rows)),
        "gaps": float(len(gaps)),
        "recommendations": float(len(recs)),
        "covered": float(sum(1 for r in recs if r.is_covered)),
        "uncovered_ratio": uncovered_ratio,
    }

    degrade: dict[str, bool | str] = {
        "llm_used": False,
        "prior_year_present": prior_year is not None,
        "granularity_note": (
            "group×chapter×item_type 3원 교차 미가용 — 인지수준 cohort 주석"
        ),
    }

    manifest = build_manifest(
        when=now_utc,
        module_version=_MODULE_VERSION,
        schema_version=_SCHEMA_VERSION,
        semester=semester,
        course_slug=course,
        inputs=input_hashes,
        thresholds=thresholds,
        counts=counts,
        degrade=degrade,
    )
    write_manifest(gold_out / "manifest_retro.json", manifest, now_utc)

    return 0


__all__ = ["run_retro", "DETERMINISTIC_EPOCH"]
