"""T030 — build_exam pipeline: ingest→plan→generate→verify→output.

``build_exam(...)`` orchestrates the full US1 textbook-path pipeline:

1. ``verify_chapter_files`` — fail-fast on missing chapter .txt (exit 2 territory).
2. Per chapter: ``load_chapter`` → ``chunk_chapter`` + build ``EvidenceIndex``.
3. ``solve(blueprint, curriculum_map)`` → slot list.
4. For each textbook slot:
   - ``generate_item(...)``
   - ``verify_groundedness(...)``
   - ``check_format(...)``
5. ALL-or-NOTHING Gold output: compute ``run_id`` → ``run_gold_dir`` → write
   xlsx + yaml + manifest + ingest_report atomically only after all items
   are verified.
6. Return ``(items, run_dir)`` for callers (tests, CLI).

Backend injection
-----------------
``build_exam`` accepts an explicit ``backend: LLMBackend`` parameter so
tests pass ``FakeBackend`` (no network).  The CLI selects the real backend
(``SubscriptionBackend`` / ``ApiBackend``) before calling ``build_exam``.

The ``pipeline.py`` module contains NO CLI-specific logic — it is a pure
function wired from I/O utilities and generation primitives.

Non-textbook slots (``source="formative"`` / ``"quiz"``) raise
``NotImplementedError`` from ``generate_item`` — that is expected for US1
(the integration test uses a textbook-only blueprint).

All-or-nothing guarantee
------------------------
Items are collected in memory.  Gold files are written ONLY after all
items pass the verify pass.  If any step raises, the Gold dir is either
not created or not populated (atomic writes ensure no partial files).

Determinism scope
-----------------
The PRIMARY Gold artefacts — ``기말출제초안.xlsx`` and ``기말출제초안.yaml`` —
are byte-identical across identical-input re-runs (xlsx via ``finalize_xlsx``
pinning ``<dcterms:modified>``; yaml via ``dump_yaml`` ``sort_keys`` +
``allow_unicode``).  The manifest deliberately carries the ONE
non-deterministic field ``generated_at`` (constitution V: 산출 결정론 — the
timestamp lives in the manifest only so the primary artefacts stay
reproducible).  "byte-identical" therefore applies to xlsx + yaml, NOT to
``manifest_examen.json``.
"""

from __future__ import annotations

import datetime
import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Any

from paideia_shared.schemas import (
    CurriculumMap,
    ExamenBlueprint,
    ExamItemDraft,
    SourceInventoryEntry,
)

from examen.generate.backend import (
    ApiBackend,
    InputHashCache,
    LLMBackend,
    SubscriptionBackend,
)
from examen.generate.convert_formative import convert_formative
from examen.generate.item_gen import generate_item
from examen.generate.vary_quiz import vary_quiz
from examen.ingest.report import write_ingest_report
from examen.ingest.textbook import load_chapter, verify_chapter_files
from examen.output.determinism import finalize_xlsx
from examen.output.exam_item_projection import write_exam_item_projection
from examen.output.manifest import build_manifest, write_manifest
from examen.output.quality_report import (
    build_quality_report,
    build_targets_vs_actual,
    write_quality_report,
)
from examen.output.xlsx import write_xlsx
from examen.output.yaml_out import write_yaml
from examen.plan.blueprint import solve
from examen.silver.chunk import chunk_chapter
from examen.silver.evidence_index import EvidenceIndex
from examen.verify.format_checks import (
    balance_answer_keys,
    check_explanation_lengths,
    check_format,
    check_formative,
    check_quiz_variation,
    detect_duplicates,
)
from examen.verify.groundedness import verify_groundedness

# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

_PINNED_WHEN = datetime.datetime(2026, 1, 1, 0, 0, 0, tzinfo=datetime.UTC)
"""Pinned timestamp for xlsx determinism (``finalize_xlsx``)."""


def _slot_position(slot_id: str) -> int:
    """Extract the global 1-based slot position from a slot_id.

    The solver emits slot_ids as ``"slot-NNN"`` in global order.  This position
    is used as ``item_no`` so that formative and textbook items never collide on
    번호 (textbook ``generate_item`` already derives item_no the same way).

    Args:
        slot_id: Slot identifier (e.g. ``"slot-007"``).

    Returns:
        Positive integer position (falls back to 1 for unknown formats).
    """
    parts = slot_id.rsplit("-", 1)
    if len(parts) == 2:
        try:
            return max(1, int(parts[1]))
        except ValueError:
            pass
    return 1


def _sha256_hex(text: str) -> str:
    """Return the SHA-256 hex digest of a UTF-8 encoded string."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _file_sha256(path: Path) -> str:
    """Return the SHA-256 hex digest of a file's contents."""
    data = path.read_bytes()
    return "sha256:" + hashlib.sha256(data).hexdigest()


def _find_chapter_file(bronze_dir_path: Path, chapter_no: int) -> Path | None:
    """Find the .txt file for chapter_no in bronze_dir (mirrors textbook.py logic)."""
    import re
    n = str(chapter_no)
    pattern = re.compile(rf"(?:^|(?<=\D)){re.escape(n)}장")
    for p in sorted(bronze_dir_path.glob("*.txt")):
        if pattern.search(p.stem):
            return p
    return None


def _compute_run_id(
    blueprint: ExamenBlueprint,
    curriculum_map: CurriculumMap,
    bronze_dir_path: Path,
) -> str:
    """Compute a deterministic run_id from the input bundle hash.

    The run_id is the first 16 hex chars of the SHA-256 of the canonical
    JSON-serialised combination of blueprint + curriculum_map + chapter
    file hashes.  Identical inputs → identical run_id → same Gold dir
    (idempotent re-run).

    Args:
        blueprint: Validated exam specification.
        curriculum_map: Week→chapter mapping.
        bronze_dir_path: Path to the Bronze directory.

    Returns:
        16-character lowercase hex string.
    """
    # Chapter file hashes — sorted for determinism
    chapter_hashes: dict[str, str] = {}
    seen: set[int] = set()
    for entry in curriculum_map.entries:
        ch_no = entry.chapter_no
        if ch_no in seen:
            continue
        seen.add(ch_no)
        ch_file = _find_chapter_file(bronze_dir_path, ch_no)
        if ch_file is not None:
            chapter_hashes[ch_file.name] = _file_sha256(ch_file)

    payload = {
        "blueprint": blueprint.model_dump(mode="json"),
        "chapter_hashes": chapter_hashes,
        "course_slug": blueprint.course_slug,
        "curriculum_entries": curriculum_map.model_dump(mode="json"),
        "semester": blueprint.semester,
    }
    canonical = json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    digest = _sha256_hex(canonical)
    return digest[:16]


def _build_input_hashes(
    bronze_dir_path: Path,
    curriculum_map: CurriculumMap,
) -> dict[str, str]:
    """Build input_hashes mapping filename → sha256 for the manifest."""
    hashes: dict[str, str] = {}
    seen: set[int] = set()
    for entry in curriculum_map.entries:
        ch_no = entry.chapter_no
        if ch_no in seen:
            continue
        seen.add(ch_no)
        ch_file = _find_chapter_file(bronze_dir_path, ch_no)
        if ch_file is not None:
            hashes[ch_file.name] = _file_sha256(ch_file)
    return hashes


def _build_config_ids(
    blueprint_path: Path | None,
    curriculum_map_path: Path | None,
) -> dict[str, str]:
    """Build config_ids mapping for the manifest."""
    ids: dict[str, str] = {}
    if blueprint_path is not None and blueprint_path.exists():
        ids["blueprint"] = _file_sha256(blueprint_path)
    if curriculum_map_path is not None and curriculum_map_path.exists():
        ids["curriculum_map"] = _file_sha256(curriculum_map_path)
    return ids


def _backend_label(backend: LLMBackend) -> str:
    """Infer the manifest ``llm_backend`` label from the backend instance.

    Maps the concrete backend type to one of the schema-permitted labels:
    - ``SubscriptionBackend`` → ``"subscription"``
    - ``ApiBackend`` → ``"api"``
    - anything else (e.g. a test FakeBackend / dry-run path) → ``"none(dry-run)"``

    Args:
        backend: The LLM backend instance used to generate the items.

    Returns:
        One of ``"subscription"``, ``"api"``, ``"none(dry-run)"``.
    """
    if isinstance(backend, SubscriptionBackend):
        return "subscription"
    if isinstance(backend, ApiBackend):
        return "api"
    return "none(dry-run)"


# ---------------------------------------------------------------------------
# Main pipeline
# ---------------------------------------------------------------------------

def build_exam(
    *,
    blueprint: ExamenBlueprint,
    curriculum_map: CurriculumMap,
    bronze_dir: Path,
    data_root: Path,
    backend: LLMBackend,
    blueprint_path: Path | None = None,
    curriculum_map_path: Path | None = None,
    formative_inventory: list[SourceInventoryEntry] | None = None,
    quiz_inventory: list[SourceInventoryEntry] | None = None,
) -> tuple[list[ExamItemDraft], Path]:
    """Run the full ingest→plan→generate→verify→output pipeline.

    This is the single entry point for building an exam draft.  It accepts
    an injectable ``backend`` so that tests use ``FakeBackend`` without
    network access.

    Pipeline steps
    --------------
    1. Verify all chapter .txt files exist (fail-fast on missing → raises).
    2. Load + chunk each chapter; build a **chapter-scoped** EvidenceIndex.
    3. Solve the blueprint → slot list (with formative cross-check if inventory provided).
    4. For each slot:
       - textbook: generate_item → verify_groundedness → check_format
       - formative: convert_formative → check_format → check_formative
       - quiz: vary_quiz → check_format → check_quiz_variation
    5. Write xlsx + yaml + manifest + ingest_report to the run Gold dir
       (all-or-nothing: writes only after all items are verified).
    6. Return ``(items, run_dir)``.

    Args:
        blueprint: Validated ExamenBlueprint.
        curriculum_map: Validated CurriculumMap.
        bronze_dir: Path to the Bronze directory containing .txt chapter files.
        data_root: Root of the data hierarchy (used to compute Gold paths).
        backend: LLM backend to use (``FakeBackend`` for tests,
            ``SubscriptionBackend`` / ``ApiBackend`` for production).
        blueprint_path: Optional path to the blueprint.yaml file (for
            manifest config_ids hashing).
        curriculum_map_path: Optional path to the curriculum_map.yaml (for
            manifest config_ids hashing).
        formative_inventory: Optional list of SourceInventoryEntry objects
            (source="formative").  When provided, the count is validated
            against ``blueprint.source_mix['formative']`` (T036 cross-check)
            and formative slots are dispatched to ``convert_formative``.
            When None, the formative slot count must be 0 or a ValueError is
            raised.
        quiz_inventory: Optional pool of quiz SourceInventoryEntry objects
            (source="quiz").  When provided, ``source_mix['quiz']`` items are
            selected chapter-evenly and dispatched to ``vary_quiz``.
            When None, quiz slot count must be 0 or a ValueError is raised.

    Returns:
        ``(items, run_dir)`` — the generated+verified items and the
        run-isolated Gold directory where artefacts were written.

    Raises:
        FileNotFoundError: If any required chapter .txt is missing.
        ValueError: If source_mix.formative != len(formative_inventory), or
            if quiz_inventory cannot supply enough chapter-even items, or
            if generation or verification fails critically.
    """
    # ----------------------------------------------------------------
    # Step 1: fail-fast chapter file verification
    # ----------------------------------------------------------------
    verify_chapter_files(curriculum_map, bronze_dir)

    # ----------------------------------------------------------------
    # Step 2: load + chunk chapters; build per-chapter evidence indexes
    # ----------------------------------------------------------------
    # chapter_no → (chunks, evidence_index)
    chapter_data: dict[int, tuple[list, EvidenceIndex]] = {}
    chapter_file_map: dict[int, Path] = {}  # chapter_no → .txt path
    removed_spans_by_chapter: dict[int, list[str]] = {}

    seen_chapters: set[int] = set()
    for entry in curriculum_map.entries:
        ch_no = entry.chapter_no
        if ch_no in seen_chapters:
            continue
        seen_chapters.add(ch_no)

        # Find .txt file
        ch_file = _find_chapter_file(bronze_dir, ch_no)
        if ch_file is None:
            raise FileNotFoundError(
                f"build_exam: no .txt file found for chapter {ch_no} in {bronze_dir}"
            )
        chapter_file_map[ch_no] = ch_file

        # Load raw lines (1-based tuples)
        numbered_lines = load_chapter(ch_file)
        raw_lines = [text for _, text in numbered_lines]

        # Chunk (also cleans + detects sections)
        chunks = chunk_chapter(
            raw_lines,
            chapter_no=ch_no,
            chapter=entry.chapter,
            semester=blueprint.semester,
            course_slug=blueprint.course_slug,
            source_file=ch_file.name,
        )

        # Build chapter-scoped evidence index from ORIGINAL numbered lines
        evidence_index = EvidenceIndex.from_chapter(
            numbered_lines,
            source_file=ch_file.name,
        )

        chapter_data[ch_no] = (chunks, evidence_index)

        # Collect removed_spans for ingest report
        spans: list[str] = []
        for chunk in chunks:
            spans.extend(chunk.removed_spans)
        removed_spans_by_chapter[ch_no] = spans

    # Flat list of all chunks (all chapters)
    all_chunks = [c for chunks, _ in chapter_data.values() for c in chunks]

    # ----------------------------------------------------------------
    # Step 3: solve blueprint → slot list
    # T036: pass formative_inventory for cross-check (validate_formative_count)
    # ----------------------------------------------------------------
    slots = solve(
        blueprint,
        curriculum_map,
        formative_inventory=formative_inventory,
        quiz_inventory=quiz_inventory,
    )

    # ----------------------------------------------------------------
    # Step 4: generate + verify each slot
    # ----------------------------------------------------------------
    # Cache dir lives under the Silver tier (not Gold) so it survives re-runs
    silver_base = data_root / "silver" / "examen" / f"{blueprint.semester}-{blueprint.course_slug}"
    cache_dir = silver_base / "cache"
    cache = InputHashCache(backend=backend, cache_dir=cache_dir)

    # 형성 슬롯에 인벤토리를 chapter-major 순서로 할당한다.
    # solver 는 formative 슬롯을 chapter-major(장 오름차순) 로 배치하므로
    # 인벤토리도 chapter_no 로 정렬해야 슬롯-인벤토리 장이 일치한다.
    # (인벤토리 파일 순서가 blueprint 장 순서와 다를 수 있으므로 정렬 필수.)
    # 동일 장 내부는 원래 순서를 보존(stable sort)한다.
    sorted_formative = sorted(
        formative_inventory or [],
        key=lambda e: (e.chapter_no if e.chapter_no is not None else 0),
    )
    formative_iter = iter(sorted_formative)

    # 퀴즈 슬롯: solver 가 slot.source_ref 에 선택된 source_ref 를 첨부했으므로
    # source_ref → SourceInventoryEntry 맵으로 조회한다.
    quiz_entry_map: dict[str, SourceInventoryEntry] = {
        entry.source_ref: entry
        for entry in (quiz_inventory or [])
    }

    items: list[ExamItemDraft] = []
    for slot in slots:
        ch_no = slot.chapter_no

        if slot.source == "textbook":
            if ch_no not in chapter_data:
                raise ValueError(
                    f"build_exam: slot '{slot.slot_id}' chapter_no={ch_no} "
                    "has no chapter data — check curriculum_map coverage"
                )
            _chunks_for_ch, evidence_index = chapter_data[ch_no]

            # generate_item handles textbook slots only
            item = generate_item(
                slot=slot,
                chunks=all_chunks,
                evidence_index=evidence_index,
                backend=backend,
                cache=cache,
            )
            item = verify_groundedness(item, evidence_index)
            item = check_format(item)

        elif slot.source == "formative":
            # T034/T036: formative 슬롯 → convert_formative
            try:
                inv_entry = next(formative_iter)
            except StopIteration as exc:
                raise ValueError(
                    f"build_exam: formative slot '{slot.slot_id}' has no "
                    "corresponding formative inventory entry. "
                    "source_mix.formative 와 formative_inventory 크기가 불일치합니다."
                ) from exc

            # 슬롯 장과 인벤토리 장이 일치하는지 확인 (source_ref↔chapter 정합성).
            # 정렬 후에도 어긋나면 인벤토리 장 분포가 solver 슬롯 장 분포와
            # 다르다는 뜻 → 조용한 불일치 금지(located error).
            if inv_entry.chapter_no != slot.chapter_no:
                raise ValueError(
                    f"build_exam: formative slot '{slot.slot_id}' "
                    f"(chapter_no={slot.chapter_no}) 와 인벤토리 항목 "
                    f"{inv_entry.source_ref!r} (chapter_no={inv_entry.chapter_no}) 의 "
                    "장이 일치하지 않습니다. 형성 인벤토리의 장 분포가 blueprint "
                    "source_mix 의 장-균등 형성 슬롯 분포와 어긋납니다."
                )

            item = convert_formative(
                entry=inv_entry,
                backend=backend,
                cache=cache,
            )
            # chapter 필드를 실제 장 이름으로 보정 (slot 에서 조회).
            # item_no 는 GLOBAL 슬롯 위치를 사용해야 교과서 item_no 와 충돌하지 않는다.
            item = item.model_copy(update={
                "item_no": _slot_position(slot.slot_id),
                "chapter": slot.chapter,
                "chapter_no": slot.chapter_no,
                "difficulty": slot.difficulty,
            })
            item = check_format(item)
            item = check_formative(item)  # T035 formative 전용 검증

        elif slot.source == "quiz":
            # T041/T043: quiz 슬롯 → vary_quiz (US3)
            # solver 가 slot.source_ref 에 선택된 quiz source_ref 를 첨부한다.
            quiz_ref = slot.source_ref
            if quiz_ref is None:
                raise ValueError(
                    f"build_exam: quiz slot '{slot.slot_id}' has no source_ref. "
                    "quiz_inventory 를 제공하거나 blueprint.source_mix.quiz 를 0으로 설정하세요."
                )
            quiz_entry = quiz_entry_map.get(quiz_ref)
            if quiz_entry is None:
                raise ValueError(
                    f"build_exam: quiz slot '{slot.slot_id}' source_ref={quiz_ref!r} 를 "
                    "quiz_inventory 에서 찾을 수 없습니다. quiz_inventory 를 확인하세요."
                )

            item = vary_quiz(
                entry=quiz_entry,
                backend=backend,
                cache=cache,
            )
            # 글로벌 슬롯 위치, 장 이름, 난이도를 slot 에서 보정 (formative 와 동일 패턴)
            item = item.model_copy(update={
                "item_no": _slot_position(slot.slot_id),
                "chapter": slot.chapter,
                "chapter_no": slot.chapter_no,
                "difficulty": slot.difficulty,
            })
            item = check_format(item)
            item = check_quiz_variation(item, quiz_entry)  # T042 자카드 가드

        else:
            raise ValueError(
                f"build_exam: unknown slot source {slot.source!r} "
                f"(slot_id={slot.slot_id})"
            )

        items.append(item)

    # ----------------------------------------------------------------
    # Step 4b: US4 post-generation verify pass (T046/T048)
    # Run AFTER all items are collected so dedup can see the full set.
    # - detect_duplicates: flag items sharing the same key_concept.
    # - check_explanation_lengths: flag wrong/leap/intent length violations.
    # Both are non-crashing (flag into review_note / duplicate_flag).
    # ----------------------------------------------------------------
    items = detect_duplicates(items)
    items = [check_explanation_lengths(i) for i in items]

    # ----------------------------------------------------------------
    # Step 4c: US5 answer-key balance (T050)
    # Run AFTER dedup + length check, BEFORE output & quality report so
    # that the final answer distribution is balanced.
    # blueprint.answer_key_balance=True (default) triggers the rebalance.
    # ----------------------------------------------------------------
    if blueprint.answer_key_balance:
        items = balance_answer_keys(items)

    # ----------------------------------------------------------------
    # Step 5: all-or-nothing Gold output
    # xlsx + yaml are byte-identical across identical-input re-runs; the
    # manifest carries the only non-deterministic field (generated_at).
    # ----------------------------------------------------------------
    run_id = _compute_run_id(blueprint, curriculum_map, bronze_dir)
    run_dir = _run_gold_dir(
        blueprint.semester,
        blueprint.course_slug,
        run_id=run_id,
        data_root=data_root,
    )
    run_dir.mkdir(parents=True, exist_ok=True)

    # 5a: xlsx (flattened)
    xlsx_path = run_dir / "기말출제초안.xlsx"
    write_xlsx(items, xlsx_path)
    finalize_xlsx(xlsx_path, _PINNED_WHEN)

    # 5b: yaml (nested full-fidelity)
    yaml_path = run_dir / "기말출제초안.yaml"
    write_yaml(items, yaml_path)

    # 5b-2: ExamItem projection sidecar (immersio 소비용, T047)
    exam_items_path = run_dir / "exam_items.yaml"
    write_exam_item_projection(
        items,
        exam_items_path,
        semester=blueprint.semester,
        course_slug=blueprint.course_slug,
    )

    # 5c: manifest
    generated_at = datetime.datetime.now(datetime.UTC).strftime(
        "%Y-%m-%dT%H:%M:%SZ"
    )
    input_hashes = _build_input_hashes(bronze_dir, curriculum_map)
    config_ids = _build_config_ids(blueprint_path, curriculum_map_path)

    ch_breakdown = dict(sorted(Counter(i.chapter for i in items).items()))
    diff_breakdown = dict(sorted(Counter(i.difficulty for i in items).items()))
    src_breakdown = dict(sorted(Counter(i.source for i in items).items()))
    answer_dist = dict(sorted(Counter(i.answer_no for i in items).items()))
    groundedness_counts = dict(
        sorted(
            Counter(
                (i.textbook_evidence.status if i.textbook_evidence else "미확인")
                for i in items
            ).items()
        )
    )

    # targets_vs_actual — T051: use build_targets_vs_actual for full structured dict
    total = len(items)
    targets_vs_actual: dict[str, Any] = build_targets_vs_actual(items, blueprint)

    # llm_backend reflects the ACTUAL backend that generated the items
    # (subscription / api / none(dry-run) for tests' FakeBackend).
    llm_backend_label = _backend_label(backend)
    # ApiBackend carries a concrete model id; other backends have no model name.
    llm_model = getattr(backend, "_model", None) if isinstance(backend, ApiBackend) else None
    manifest = build_manifest(
        semester=blueprint.semester,
        course_slug=blueprint.course_slug,
        exam_name=blueprint.exam_name,
        input_hashes=input_hashes,
        config_ids=config_ids,
        generated_at=generated_at,
        llm_backend=llm_backend_label,
        llm_model=llm_model,
        cache_hit_rate=cache.cache_hit_rate(),
        item_count=total,
        source_breakdown=src_breakdown,
        difficulty_breakdown=diff_breakdown,
        chapter_breakdown=ch_breakdown,
        answer_no_distribution=answer_dist,
        groundedness=groundedness_counts,
        targets_vs_actual=targets_vs_actual,
    )
    write_manifest(run_dir / "manifest_examen.json", manifest)

    # 5c-2: quality report (T051) — 출제품질리포트.md
    quality_report_text = build_quality_report(items, blueprint)
    write_quality_report(run_dir / "출제품질리포트.md", quality_report_text)

    # 5d: ingest report
    textbook_report: dict[str, Any] = {
        "chapters_required": len(seen_chapters),
        "chapters_found": len(chapter_file_map),
        "removed_span_counts": {
            str(ch_no): len(spans)
            for ch_no, spans in sorted(removed_spans_by_chapter.items())
        },
    }
    n_formative = len(formative_inventory) if formative_inventory else 0
    ingest_report: dict[str, Any] = {
        "stt": {"expected": 0, "found": 0, "missing": [], "filename_violations": []},
        "textbook": textbook_report,
        "formative": {
            "expected_total": blueprint.source_mix.get("formative", 0),
            "found": n_formative,
        },
        "quiz": {
            "weeks": sorted({e.week for e in (quiz_inventory or []) if e.week is not None}),
            "rows": len(quiz_inventory) if quiz_inventory else 0,
        },
    }
    write_ingest_report(run_dir / "ingest_report.json", ingest_report)

    return items, run_dir


# ---------------------------------------------------------------------------
# Re-export run_gold_dir for CLI convenience
# ---------------------------------------------------------------------------

def _run_gold_dir(
    semester: str,
    course_slug: str,
    *,
    run_id: str,
    data_root: Path,
) -> Path:
    """Delegate to ``examen.output.paths.run_gold_dir``."""
    from examen.output.paths import run_gold_dir as _rgd
    return _rgd(semester, course_slug, run_id=run_id, data_root=data_root)


__all__ = ["build_exam"]
