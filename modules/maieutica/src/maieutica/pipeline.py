"""T034 — build pipeline (quiz + formative paths): ingest→silver→plan→generate→verify→output.

``build(...)`` orchestrates the full US1 quiz-path pipeline for one chapter
(= one week).  It mirrors ``examen.pipeline.build_exam`` but for maieutica's
simpler single-chapter quiz model.

Pipeline steps
--------------
1. Ingest (Bronze→Silver, fail-fast):
   - ``validate_week_in_map`` — the spec week must exist in the curriculum map.
   - ``resolve_chapter_txt`` — locate the chapter ``.txt`` (raises if missing).
   - ``load_chapter`` → ``clean_textbook`` (audit) and write ``ingest_report.json``.
2. Silver: ``chunk_chapter`` → ``EvidenceIndex.from_chapter``.
3. Plan: ``plan_slots`` → quiz + formative slots (both kinds are built here).
4. Generate + verify per quiz slot (each ``model_copy``-enriching the candidate):
   - ``build_bundle`` → ``generate_quiz_item`` (via ``InputHashCache``) →
     ``verify_groundedness`` → ``check_format`` → ``assign_difficulty``.
5. Cross-set verify: ``detect_duplicates`` over the full candidate set.
6. Output: ``write_quiz_xls`` + ``write_manifest`` under ``runs/{run_id}/``.

Atomicity (constitution V — 부분 산출 금지)
------------------------------------------
Input validation fails BEFORE any Gold write: the fail-fast ingest checks
(missing chapter ``.txt`` / absent curriculum mapping) raise before the run
directory is created, so a faulty input never produces a Gold file (CLI maps
those exceptions to exit 2).  Each of the two Gold files (``.xls`` + manifest)
is written atomically (temp→rename), and the deterministic ``run_id`` makes
re-runs idempotent — a re-run with the same inputs targets the same
``runs/{run_id}/`` and recovers/overwrites a partial pair rather than
accumulating duplicates.

Determinism scope
-----------------
The quiz ``.xls`` is byte-identical across identical-input re-runs (xlwt single
shared style; SC-009).  ``manifest_maieutica.json`` carries the only
non-deterministic field (``generated_at``).

Backend injection
-----------------
``build`` accepts an explicit ``backend: LLMBackend`` so tests pass a
``SubscriptionBackend`` fed by canned response files (no network).  The CLI
selects the real backend before calling ``build``.
"""

from __future__ import annotations

import datetime
import hashlib
from collections import Counter
from pathlib import Path

from paideia_shared.schemas import (
    CurriculumMap,
    FormativeItemCandidate,
    MaieuticaGenerationSpec,
    QuizItemCandidate,
)

from maieutica.assemble.difficulty import assign_difficulty
from maieutica.generate.backend import (
    ApiBackend,
    InputHashCache,
    LLMBackend,
    SubscriptionBackend,
)
from maieutica.generate.formative_gen import generate_formative_item
from maieutica.generate.quiz_gen import generate_quiz_item
from maieutica.ingest.report import write_ingest_report
from maieutica.ingest.spec_load import resolve_chapter_txt, validate_week_in_map
from maieutica.ingest.textbook import load_chapter
from maieutica.ingest.textbook_clean import clean_textbook
from maieutica.output.candidate_yaml import write_candidate_yaml
from maieutica.output.formative_xlsx import (
    formative_xlsx_filename,
    write_formative_xlsx,
)
from maieutica.output.manifest import build_manifest, write_manifest
from maieutica.output.paths import (
    compute_run_id,
    run_gold_dir,
    silver_dir,
)
from maieutica.output.quiz_xls import write_quiz_xls
from maieutica.plan.slots import plan_slots
from maieutica.silver.chunk import chunk_chapter
from maieutica.silver.evidence_index import EvidenceIndex
from maieutica.verify.format_checks import (
    answer_no_distribution,
    check_format,
    detect_duplicates,
)
from maieutica.verify.groundedness import ground_formative, verify_groundedness

# Frozen asset path (config_id provenance) — next to the quiz_xls writer's asset.
_GUIDE_ASSET_PATH = (
    Path(__file__).resolve().parent / "assets" / "lms_quiz_guide_sheet.yaml"
)


def _file_sha256(path: Path) -> str:
    """Return ``"sha256:<hex>"`` of a file's contents."""
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def _backend_label(backend: LLMBackend) -> str:
    """Map a backend instance to its manifest ``llm_backend`` label.

    Args:
        backend: The LLM backend used to generate the items.

    Returns:
        One of ``"subscription"``, ``"api"``, ``"none(dry-run)"``.
    """
    if isinstance(backend, SubscriptionBackend):
        return "subscription"
    if isinstance(backend, ApiBackend):
        return "api"
    return "none(dry-run)"


def build(
    *,
    spec: MaieuticaGenerationSpec,
    curriculum_map: CurriculumMap,
    bronze_dir: Path,
    data_root: Path,
    backend: LLMBackend,
    generation_spec_path: Path | None = None,
    curriculum_map_path: Path | None = None,
    answer_explanation_max: int | None = None,
) -> tuple[list[QuizItemCandidate], Path]:
    """Run the full quiz-path build pipeline for one chapter (one week).

    Args:
        spec: Validated generation specification (one chapter run).
        curriculum_map: Validated week→chapter mapping.
        bronze_dir: Directory containing the chapter ``.txt`` + config YAMLs.
        data_root: Root of the ``data/`` hierarchy (Silver cache + Gold paths).
        backend: LLM backend (``SubscriptionBackend`` / ``ApiBackend`` in
            production; a canned ``SubscriptionBackend`` in tests).  Wrapped in
            an ``InputHashCache`` for byte-identical re-runs.
        generation_spec_path: Optional path to ``generation_spec.yaml`` (manifest
            ``config_ids`` provenance).
        curriculum_map_path: Optional path to ``curriculum_map.yaml`` (manifest
            ``config_ids`` provenance).
        answer_explanation_max: Optional max length for the LMS 답안설명 cell.
            ``None`` (default, B1) writes the full basic fold — byte-identical to
            prior output.  When set, the leap portion is truncated first at write
            time; the candidate and ``출제후보_완전판.yaml`` always keep the full
            leap (V4 invariant holds on the candidate).

    Returns:
        ``(items, run_dir)`` — the generated+verified quiz candidates and the
        run-isolated Gold directory where artefacts were written.

    Raises:
        ValueError: If ``spec.week`` is absent from the curriculum map
            (input/config fault — CLI exit 2).
        FileNotFoundError: If the chapter ``.txt`` is missing (CLI exit 2).
        RuntimeError: If the backend cannot supply a response (CLI exit 3).
    """
    # ----------------------------------------------------------------
    # Step 1: ingest (Bronze→Silver) — fail-fast BEFORE any Gold write
    # ----------------------------------------------------------------
    validate_week_in_map(
        curriculum_map,
        spec.week,
        curriculum_map_path=curriculum_map_path or (bronze_dir / "curriculum_map.yaml"),
    )
    chapter_txt = resolve_chapter_txt(bronze_dir, spec.chapter_no)

    numbered_lines = load_chapter(chapter_txt)
    raw_lines = [text for _, text in numbered_lines]
    _kept, removed_spans = clean_textbook(raw_lines)

    silver_base = silver_dir(spec.semester, spec.course_slug, data_root=data_root)
    write_ingest_report(
        silver_base / "ingest_report.json",
        {
            "textbook": {
                "chapters_required": 1,
                "chapters_found": 1,
                "removed_span_counts": {str(spec.chapter_no): len(removed_spans)},
            },
            "anomalies": {
                "filename_violations": [],
                "unexpected_files": [],
            },
        },
    )

    # ----------------------------------------------------------------
    # Step 2: silver — chunk + evidence index (chapter-scoped)
    # ----------------------------------------------------------------
    chunks = chunk_chapter(
        raw_lines,
        chapter_no=spec.chapter_no,
        chapter=spec.chapter,
        semester=spec.semester,
        course_slug=spec.course_slug,
        source_file=chapter_txt.name,
    )
    evidence_index = EvidenceIndex.from_chapter(
        raw_lines,
        chunks=chunks,
        source_file=chapter_txt.name,
    )

    # ----------------------------------------------------------------
    # Step 3: plan — quiz + formative slots (both paths are built)
    # ----------------------------------------------------------------
    slots = plan_slots(spec)
    quiz_slots = [s for s in slots if s.kind == "quiz"]
    formative_slots = [s for s in slots if s.kind == "formative"]

    # ----------------------------------------------------------------
    # Step 4: generate + verify each quiz slot (staged model_copy enrichment)
    # ----------------------------------------------------------------
    cache_dir = silver_base / "cache"
    cache = InputHashCache(backend=backend, cache_dir=cache_dir)

    items: list[QuizItemCandidate] = []
    for slot in quiz_slots:
        item = generate_quiz_item(slot, spec, chunks, cache)
        item = verify_groundedness(item, evidence_index)
        item = check_format(item)
        item = assign_difficulty(item)
        items.append(item)

    # Cross-set duplicate detection (after the full set is collected).
    items = detect_duplicates(items)

    # Formative path (US3): generate + ground each formative slot.  Independent
    # of the quiz path — it does not perturb the quiz items or their .xls.
    formative_items: list[FormativeItemCandidate] = []
    for slot in formative_slots:
        formative = generate_formative_item(slot, spec, chunks, cache)
        formative = ground_formative(formative, evidence_index)
        formative_items.append(formative)

    # ----------------------------------------------------------------
    # Step 5: all-or-nothing Gold output under runs/{run_id}/
    # ----------------------------------------------------------------
    run_id = compute_run_id(
        generation_spec_bytes=(
            generation_spec_path.read_bytes()
            if generation_spec_path is not None
            else (bronze_dir / "generation_spec.yaml").read_bytes()
        ),
        curriculum_map_bytes=(
            curriculum_map_path.read_bytes()
            if curriculum_map_path is not None
            else (bronze_dir / "curriculum_map.yaml").read_bytes()
        ),
        chapter_txt_bytes=chapter_txt.read_bytes(),
    )
    run_dir = run_gold_dir(
        spec.semester, spec.course_slug, run_id=run_id, data_root=data_root
    )
    run_dir.mkdir(parents=True, exist_ok=True)

    # 5a: LMS quiz upload .xls (답안설명 may be leap-first truncated at write time)
    xls_path = run_dir / f"QuestionUploadExcel_{spec.week}주차.xls"
    write_quiz_xls(
        xls_path, items, week=spec.week, answer_explanation_max=answer_explanation_max
    )

    # 5b: LMS formative upload .xlsx (bhu_text_mining ExamPDFGenerator-compatible)
    formative_path = run_dir / formative_xlsx_filename(spec.chapter_no, spec.chapter)
    write_formative_xlsx(formative_path, formative_items)

    # 5c: full-fidelity candidate yaml (full leap + per-option/leap evidence)
    write_candidate_yaml(items, run_dir / "출제후보_완전판.yaml")

    # 5d: manifest
    generated_at = datetime.datetime.now(datetime.UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    input_hashes = {chapter_txt.name: _file_sha256(chapter_txt)}
    config_ids = _build_config_ids(generation_spec_path, curriculum_map_path)

    answer_dist = answer_no_distribution(items)
    stem_breakdown = dict(sorted(Counter(i.stem_polarity for i in items).items()))
    diff_breakdown = dict(sorted(Counter(i.difficulty for i in items).items()))
    groundedness = dict(
        sorted(
            Counter(
                (i.textbook_evidence.status if i.textbook_evidence else "미확인")
                for i in items
            ).items()
        )
    )
    option_length_violations = sum(1 for i in items if not i.option_length_ok)
    explanation_length_violations = sum(
        1 for i in items if not i.explanation_length_ok
    )

    manifest = build_manifest(
        semester=spec.semester,
        course_slug=spec.course_slug,
        week=spec.week,
        chapter_no=spec.chapter_no,
        chapter=spec.chapter,
        input_hashes=input_hashes,
        config_ids=config_ids,
        generated_at=generated_at,
        llm_backend=_backend_label(backend),
        llm_model=getattr(backend, "_model", None)
        if isinstance(backend, ApiBackend)
        else None,
        cache_hit_rate=cache.cache_hit_rate(),
        quiz_count=len(items),
        formative_count=len(formative_items),
        answer_no_distribution=answer_dist,
        stem_polarity_breakdown=stem_breakdown,
        difficulty_breakdown=diff_breakdown,
        groundedness=groundedness,
        option_length_violations=option_length_violations,
        explanation_length_violations=explanation_length_violations,
    )
    write_manifest(run_dir / "manifest_maieutica.json", manifest)

    return items, run_dir


def _build_config_ids(
    generation_spec_path: Path | None,
    curriculum_map_path: Path | None,
) -> dict[str, str]:
    """Build the manifest ``config_ids`` mapping (SHA-256 of config inputs).

    Args:
        generation_spec_path: Optional generation_spec.yaml path.
        curriculum_map_path: Optional curriculum_map.yaml path.

    Returns:
        Mapping of config identifier → ``"sha256:<hex>"``.  The frozen LMS guide
        asset is always included (immutable LMS contract provenance).
    """
    ids: dict[str, str] = {}
    if generation_spec_path is not None and generation_spec_path.exists():
        ids["generation_spec"] = _file_sha256(generation_spec_path)
    if curriculum_map_path is not None and curriculum_map_path.exists():
        ids["curriculum_map"] = _file_sha256(curriculum_map_path)
    if _GUIDE_ASSET_PATH.exists():
        ids["lms_quiz_guide_sheet"] = _file_sha256(_GUIDE_ASSET_PATH)
    return ids


__all__ = ["build"]
