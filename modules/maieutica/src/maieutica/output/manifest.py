"""T033 — MaieuticaManifest builder and deterministic writer.

Provides:
- ``build_manifest(**kwargs) -> MaieuticaManifest`` — constructs and validates
  the manifest via the shared Pydantic schema.
- ``write_manifest(path, manifest)`` — serialises to deterministic UTF-8 JSON
  and writes atomically.

``generated_at`` is the ONLY intentionally non-deterministic field in the
entire maieutica Gold output (R11); every other Gold byte (``.xls`` / ``.xlsx``
/ yaml) is byte-identical for identical inputs.  ``answer_no_distribution`` is
produced by ``maieutica.verify.format_checks.answer_no_distribution`` and passed
in by the caller.

Mirrors ``modules/examen/src/examen/output/manifest.py``.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Literal

from paideia_shared.schemas import MaieuticaManifest

from maieutica.output.paths import atomic_write


def build_manifest(
    *,
    semester: str,
    course_slug: str,
    week: int,
    chapter_no: int,
    chapter: str,
    input_hashes: dict[str, str],
    config_ids: dict[str, str],
    generated_at: str,
    llm_backend: Literal["subscription", "api", "none(dry-run)"],
    llm_model: str | None,
    cache_hit_rate: float | None,
    quiz_count: int,
    formative_count: int,
    answer_no_distribution: dict[int, int],
    stem_polarity_breakdown: dict[str, int],
    difficulty_breakdown: dict[str, int],
    groundedness: dict[str, int],
    option_length_violations: int,
    explanation_length_violations: int,
) -> MaieuticaManifest:
    """Construct and validate a MaieuticaManifest.

    All fields are passed explicitly (no ``**kwargs`` magic) so type checkers can
    verify caller correctness.

    Args:
        semester: Semester code validated by ``SemesterCode`` (e.g. ``"2026-1"``).
        course_slug: ASCII kebab-case course slug (e.g. ``"anatomy"``).
        week: Target week number.
        chapter_no: Source chapter number.
        chapter: Chapter display name.
        input_hashes: Bronze input file → SHA-256 mapping.
        config_ids: ``generation_spec`` / ``curriculum_map`` /
            ``lms_quiz_guide_sheet`` identifier mapping (SHA-256).
        generated_at: Wall-clock ISO8601 UTC string.  The only non-deterministic
            field in the maieutica Gold layer.
        llm_backend: One of ``"subscription"``, ``"api"``, ``"none(dry-run)"``.
        llm_model: LLM model identifier, or ``None`` for dry-run.
        cache_hit_rate: LLM cache hit rate (0.0–1.0), or ``None``.
        quiz_count: Number of quiz candidates produced.
        formative_count: Number of formative candidates produced.
        answer_no_distribution: Count per answer position (1–5), from
            ``verify.format_checks.answer_no_distribution``.
        stem_polarity_breakdown: Count of 부정형 / 긍정형 items (SC-005).
        difficulty_breakdown: Count per difficulty level 상/중/하.
        groundedness: ``{"확인": N, "미확인": M}`` grounding summary (SC-007).
        option_length_violations: Quiz items with any out-of-window option
            (SC-004; target 0).
        explanation_length_violations: Quiz items with
            ``explanation_length_ok=False`` (SC-006; target 0).

    Returns:
        Validated MaieuticaManifest instance.

    Raises:
        pydantic.ValidationError: If any field fails schema validation.
    """
    return MaieuticaManifest.model_validate(
        {
            "semester": semester,
            "course_slug": course_slug,
            "week": week,
            "chapter_no": chapter_no,
            "chapter": chapter,
            "input_hashes": input_hashes,
            "config_ids": config_ids,
            "generated_at": generated_at,
            "llm_backend": llm_backend,
            "llm_model": llm_model,
            "cache_hit_rate": cache_hit_rate,
            "quiz_count": quiz_count,
            "formative_count": formative_count,
            "answer_no_distribution": answer_no_distribution,
            "stem_polarity_breakdown": stem_polarity_breakdown,
            "difficulty_breakdown": difficulty_breakdown,
            "groundedness": groundedness,
            "option_length_violations": option_length_violations,
            "explanation_length_violations": explanation_length_violations,
        }
    )


def write_manifest(path: Path, manifest: MaieuticaManifest) -> None:
    """Serialise ``manifest`` to a deterministic UTF-8 JSON file.

    Output properties:
    - ``sort_keys=True`` — alphabetical key order.
    - ``ensure_ascii=False`` — Korean characters written verbatim.
    - ``indent=2`` — human-readable.
    - Written atomically (temp→rename, constitution V: 부분 산출 금지).
    - Parent directories are created if they do not exist.

    Args:
        path: Destination path (e.g. ``run_dir / "manifest_maieutica.json"``).
        manifest: Validated MaieuticaManifest to write.
    """
    # Serialise first — failure leaves no directory side effects.
    raw = manifest.model_dump(mode="json")
    serialized = json.dumps(raw, sort_keys=True, ensure_ascii=False, indent=2)
    if not serialized.endswith("\n"):
        serialized += "\n"

    path.parent.mkdir(parents=True, exist_ok=True)

    def _write(tmp: Path) -> None:
        tmp.write_text(serialized, encoding="utf-8")

    atomic_write(path, _write)


__all__ = ["build_manifest", "write_manifest"]
