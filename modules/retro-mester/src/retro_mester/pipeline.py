"""T029 / T035–T036 — retro-mester pipeline: load → detect → escalate → rank → output.

Entry point: ``run_retro(...) -> int`` (exit code).

Steps:
1. Resolve input paths under ``data_root``.
2. Load combined + items + exam_spec + config; call ``reconcile_config``.
3. ``detect_gaps`` → ``escalate_structural`` (US2 T032) → ``rank_changes``.
4. Compute per-(chapter,segment) prescriptions (US2 T033) and cluster vocab (US2 T034).
5. Write Silver (빈틈표.parquet, 변경권고.parquet) and Gold
   (CQI회고보고서.md/.pdf, 회고분석.xlsx with 집단대비 sheet, manifest_retro.json).

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

from retro_mester.align.alignment import build_alignment
from retro_mester.align.cliff import chapter_item_type_rates, detect_cliff, dominant_failing_level
from retro_mester.align.interest_gap import interest_aversion_findings
from retro_mester.cause.prescription import prescription_for, refine_cause
from retro_mester.forward.audit import audit_prior
from retro_mester.forward.baseline import build_baseline
from retro_mester.forward.ledger import build_ledger
from retro_mester.forward.next_items import propose_next_items, write_next_items_md
from retro_mester.forward.write import next_year, write_forward
from retro_mester.gaps.detect import detect_gaps
from retro_mester.gaps.escalate import escalate_structural
from retro_mester.llm.cache import InputHashCache
from retro_mester.llm.insight import LLMRequiredError, build_insight
from retro_mester.load import (
    InputError,
    load_combined,
    load_config,
    load_exam_spec,
    load_items,
    reconcile_config,
)
from retro_mester.output.figures import render_all_figures
from retro_mester.output.manager import archive_existing, atomic_write_text
from retro_mester.output.manifest import build_manifest, write_manifest
from retro_mester.output.paths import bronze_dir, gold_dir, output_key, silver_dir
from retro_mester.output.report_md import build_report_md
from retro_mester.output.report_pdf import write_report_pdf
from retro_mester.output.silver import write_silver
from retro_mester.output.xlsx import write_xlsx
from retro_mester.prioritize.rank import rank_changes
from retro_mester.segment.assign import assign_segments
from retro_mester.segment.vocab import segment_cluster_vocab
from retro_mester.validity.gate import chapter_validity, validity_signals

# Repair prescription used when a chapter's validity is "문항수선" (T050 / SC-006).
# This constant is the ONLY prescription emitted for such chapters; re-teaching
# prescriptions are suppressed because the instrument cannot be trusted.
_REPAIR_PRESCRIPTION = "문항 재검토·교체 — 학습 처방 보류"

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
    2026, 1, 1, 0, 0, 0, tzinfo=datetime.UTC
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
    prior_yaml_path: str | None = None,
    llm_mode: str = "off",
    require_llm: bool = False,
) -> int:
    """Run the full retrospective analytics pipeline (US1–US4).

    Steps:
    1. Resolve all input paths under ``data_root``.
    2. Load combined + items + exam_spec + config; reconcile config.
    3. detect_gaps → escalate_structural → prescriptions → cluster vocab
       → rank_changes (US1 + US2).
    3c. Cognitive-cliff + alignment enrichment: enrich UnitGap.cohort_failing_item_types
        and ChangeRecommendation.target_cognitive_level; build AlignmentFinding list (US4).
    4. Build forward baseline + ledger + next-item proposals (US3).
    5. If ``prior_yaml_path`` provided, run audit against prior ledger.
    6. Archive existing outputs (gold + silver retro dirs).
    7. Write Silver parquet + Gold figs/md/pdf/xlsx/yaml/md + manifest.

    Args:
        semester: Semester code, e.g. ``"2026-1"``.
        course: Course slug, e.g. ``"anatomy"``.
        data_root: Root of the data hierarchy (default ``"data"``).
        config_path: Optional explicit path to ``retro_config.yaml``.
        prior_yaml_path: Optional path to a prior ``차년도방향.yaml`` for
            forward-contract audit.  When ``None``, cold-start (no audit section).
        llm_mode: LLM mode — ``"off"`` (default), ``"subscription"``,
            or ``"api"``.
        require_llm: If True, exit 5 when LLM is unavailable (unused in
            US1–US3).

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
            prior_yaml_path=prior_yaml_path,
            llm_mode=llm_mode,
            require_llm=require_llm,
        )
    except InputError:
        return 2
    except LLMRequiredError:
        return 5
    except Exception:
        return 3


def _run(
    *,
    semester: str,
    course: str,
    data_root: Path,
    config_path: str | None,
    prior_yaml_path: str | None,
    llm_mode: str,
    require_llm: bool = False,
) -> int:
    """Inner pipeline implementation — exceptions propagate to ``run_retro``'s handler.

    Args:
        semester: Semester code.
        course: Course slug.
        data_root: Resolved data root Path.
        config_path: Optional explicit config path override.
        prior_yaml_path: Optional path to prior 차년도방향.yaml for audit.
        llm_mode: LLM mode string — ``"off"``, ``"subscription"``, ``"api"``.
        require_llm: If True, raise ``LLMRequiredError`` (exit 5) when LLM
            is unavailable instead of degrading gracefully.

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
    # Step 3: Detect gaps → escalate structural → compute prescriptions
    #         → cluster vocab → rank changes (US1/US2 T032-T036)
    # ------------------------------------------------------------------
    # Assign segments to capture unclassified count for manifest (T060).
    _segment_buckets, _unclassified = assign_segments(rows, config)
    gaps = detect_gaps(rows, items, config)

    # US2 T032: escalate chapters where baseline is also below threshold.
    gaps = escalate_structural(gaps, rows, config)

    # US2 T033: refine cause per gap and compute per-(chapter,segment) prescriptions.
    refined_gaps = []
    prescriptions: dict[tuple[str, str], str] = {}
    for gap in gaps:
        refined_cause, extra_signals = refine_cause(gap, rows, items, config)
        # Rebuild gap with refined cause (UnitGap is frozen).
        if refined_cause != gap.cause:
            merged_signals = {**gap.cause_signals, **extra_signals}
            gap = gap.model_copy(update={"cause": refined_cause, "cause_signals": merged_signals})
        else:
            # Still merge extra_signals for traceability.
            merged_signals = {**gap.cause_signals, **extra_signals}
            gap = gap.model_copy(update={"cause_signals": merged_signals})
        refined_gaps.append(gap)
        prescriptions[(gap.chapter, gap.segment)] = prescription_for(gap.cause, gap.segment)
    gaps = refined_gaps

    # US2 T034: cluster vocabulary per segment.
    vocab = segment_cluster_vocab(rows, config)

    recs, uncovered_ratio = rank_changes(gaps, config)

    # US2 T035: patch prescription_key and cluster_vocab onto recommendations.
    patched_recs = []
    for rec in recs:
        presc = prescriptions.get((rec.chapter, rec.segment), rec.prescription_key)
        cv = vocab.get(rec.segment)
        patched_recs.append(
            rec.model_copy(update={"prescription_key": presc, "cluster_vocab": cv})
        )
    recs = patched_recs

    # ------------------------------------------------------------------
    # Step 3c: US4 T044/T045/T048 — cognitive-cliff + alignment enrichment
    # ------------------------------------------------------------------
    # Compute cliff: {chapter: [failing_item_types]} at cohort level.
    cliff = detect_cliff(items, config)
    item_type_rates = chapter_item_type_rates(items)

    # Enrich UnitGap.cohort_failing_item_types from the cliff dict.
    # UnitGap is frozen → rebuild via model_copy.
    enriched_gaps: list = []
    for gap in gaps:
        failing_types = cliff.get(gap.chapter, [])
        if failing_types != gap.cohort_failing_item_types:
            gap = gap.model_copy(update={"cohort_failing_item_types": list(failing_types)})
        enriched_gaps.append(gap)
    gaps = enriched_gaps

    # Enrich ChangeRecommendation.target_cognitive_level from dominant_failing_level.
    enriched_recs: list = []
    for rec in recs:
        dominant = dominant_failing_level(rec.chapter, cliff, item_type_rates)
        if dominant != rec.target_cognitive_level:
            rec = rec.model_copy(update={"target_cognitive_level": dominant})
        enriched_recs.append(rec)
    recs = enriched_recs

    # Build AlignmentFinding list for output.
    alignment_findings = build_alignment(items, curriculum, blueprint, rows, config)

    # Compute interest/aversion gap (FR-022) — attached to findings where applicable.
    _interest_gap_data = interest_aversion_findings(rows)

    # ------------------------------------------------------------------
    # Step 3d: US5 T049/T050 — psychometric validity gate
    # ------------------------------------------------------------------
    # Compute per-chapter ValidityVerdict from item-level CTT statistics.
    validity_verdicts = chapter_validity(items, config)

    # Build per-chapter signals for the 타당도 xlsx sheet (T051).
    _items_by_chapter: dict[str, list] = {}
    for it in items:
        _items_by_chapter.setdefault(it.chapter, []).append(it)
    validity_table: list[dict] = []
    for ch in sorted(validity_verdicts.keys()):
        sigs = validity_signals(_items_by_chapter.get(ch, []), config)
        validity_table.append({
            "chapter": ch,
            "verdict": validity_verdicts[ch],
            **sigs,
        })

    # Enrich UnitGap.validity (replaces provisional "판정불가").
    validity_enriched_gaps: list = []
    for gap in gaps:
        verdict = validity_verdicts.get(gap.chapter, "판정불가")
        if verdict != gap.validity:
            gap = gap.model_copy(update={"validity": verdict})
        validity_enriched_gaps.append(gap)
    gaps = validity_enriched_gaps

    # Enrich ChangeRecommendation: mirror validity from gap; for "문항수선"
    # chapters, override prescription_key with the repair string (SC-006).
    # Re-teaching prescriptions are suppressed — the instrument must be fixed
    # before instructional re-design is meaningful.
    chapter_validity_map: dict[str, str] = {
        gap.chapter: gap.validity for gap in gaps
    }
    validity_enriched_recs: list = []
    for rec in recs:
        rec_validity = chapter_validity_map.get(rec.chapter, "판정불가")
        updates: dict = {"validity": rec_validity}
        if rec_validity == "문항수선":
            updates["prescription_key"] = _REPAIR_PRESCRIPTION
        rec = rec.model_copy(update=updates)
        validity_enriched_recs.append(rec)
    recs = validity_enriched_recs

    # ------------------------------------------------------------------
    # Step 3b: US3 T037-T041 — forward-contract planning
    # ------------------------------------------------------------------
    # NOTE: forward planning runs before the LLM step so the forward
    # summary is available as part of the insight facts (Step 3e).
    # Derive the year this forward plan is created for.
    created_for_year = next_year(semester)

    # T037: build per-(segment × chapter) baseline snapshot.
    baseline = build_baseline(rows, config)

    # T038: build improvement ledger from covered recommendations.
    covered_recs = [r for r in recs if r.is_covered]
    ledger = build_ledger(covered_recs, gaps, config, created_for_year=created_for_year)

    # T041: propose next-year diagnostic items.
    proposals = propose_next_items(gaps, rows, config)

    # T040: optional audit against prior-year yaml.
    forward_audit: dict | None = None
    if prior_yaml_path is not None:
        forward_audit = audit_prior(Path(prior_yaml_path), baseline)

    # ------------------------------------------------------------------
    # Step 3e: US6 T054/T055 — optional LLM insight layer
    #
    # SC-009 compliance: the LLM step runs AFTER all deterministic
    # computation (Silver parquet content, xlsx, yaml, non-LLM report
    # sections) is finalised.  The only output that varies between
    # llm_mode="off" and llm_mode="subscription"/"api" is the
    # ``llm_block`` string injected into the MD/PDF report.
    #
    # The Silver parquet write and all other Gold artefacts (xlsx, yaml,
    # 차년도진단문항제안.md) are written *after* this step and are
    # byte-identical regardless of llm_mode.
    # ------------------------------------------------------------------
    # Build structured facts from already-computed results.
    _top_changes = [
        {
            "chapter": r.chapter,
            "segment": r.segment,
            "cause_hypothesis": r.cause_hypothesis,
            "prescription_key": r.prescription_key,
        }
        for r in recs
        if r.is_covered
    ]
    _alignment_flag_strs = list({f.flag for f in alignment_findings if f.flag})
    _forward_summary = (
        f"개선 서약 {len(ledger)}건"
        if ledger
        else "개선 서약 없음"
    )
    insight_facts: dict = {
        "top_changes": _top_changes,
        "alignment_flags": _alignment_flag_strs,
        "uncovered_ratio": uncovered_ratio,
        "forward_summary": _forward_summary,
    }

    # Cache lives under silver/.llm_cache/retro-mester/<key>/ — a sibling of
    # the archived retro-mester dir so it SURVIVES archival across runs
    # (FR-025 reproducibility: same input → same cached response).
    _key = output_key(semester, course)
    _cache_dir = data_root / "silver" / ".llm_cache" / "retro-mester" / _key
    _llm_cache = InputHashCache(_cache_dir) if llm_mode != "off" else None

    # build_insight raises LLMRequiredError if require_llm=True and
    # backend fails — propagates to run_retro which returns exit 5.
    llm_block_text, llm_used = build_insight(
        insight_facts,
        llm_mode=llm_mode,
        require_llm=require_llm,
        cache=_llm_cache,
    )

    # ------------------------------------------------------------------
    # Step 4: Compute timestamps
    # ------------------------------------------------------------------
    # Real now() — used ONLY for archival dir names and manifest.generated_at_utc
    now_utc: datetime.datetime = datetime.datetime.now(datetime.UTC)

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

    # Gold — figures (US4 T047: alignment PNGs, deterministic)
    figs_dir = gold_out / "figs"
    render_all_figures(alignment_findings, figs_dir)

    # Gold — Markdown (US2 T035 + US3 T042: forward section + US4 T047: alignment
    #         + US6 T055: LLM insight block)
    md_text = build_report_md(
        recs,
        uncovered_ratio,
        gaps,
        semester,
        course,
        llm_block=llm_block_text,
        prescriptions=prescriptions,
        forward_ledger=ledger,
        forward_audit=forward_audit,
        alignment_findings=alignment_findings,
    )
    atomic_write_text(gold_out / "CQI회고보고서.md", md_text, encoding="utf-8")

    # Gold — PDF (uses DETERMINISTIC_EPOCH for SOURCE_DATE_EPOCH)
    write_report_pdf(md_text, gold_out / "CQI회고보고서.pdf", when)

    # Gold — xlsx (US2 T035 + US4 T047: 정렬 sheet + US5 T051: 타당도 sheet)
    write_xlsx(
        gaps,
        recs,
        gold_out / "회고분석.xlsx",
        when,
        prescriptions=prescriptions,
        alignment_findings=alignment_findings,
        validity_table=validity_table,
    )

    # Gold — 차년도방향.yaml (US3 T039)
    write_forward(
        gold_out / "차년도방향.yaml",
        ledger=ledger,
        baseline=baseline,
        semester=semester,
        course_slug=course,
        created_for_year=created_for_year,
        audit=forward_audit,
    )

    # Gold — 차년도진단문항제안.md (US3 T041)
    write_next_items_md(gold_out / "차년도진단문항제안.md", proposals)

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
        "segments": float(len(_segment_buckets)),
        "gaps": float(len(gaps)),
        "recommendations": float(len(recs)),
        "covered": float(sum(1 for r in recs if r.is_covered)),
        "uncovered_ratio": uncovered_ratio,
        "unclassified_students": float(len(_unclassified)),
    }

    degrade: dict[str, bool | str] = {
        "llm_used": llm_used,
        "prior_year_present": prior_yaml_path is not None,
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
