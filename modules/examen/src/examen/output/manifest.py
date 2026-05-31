"""T017 — ExamenManifest builder and writer.

Provides:
- ``build_manifest(**kwargs) -> ExamenManifest`` — constructs and validates
  the manifest via the shared Pydantic schema.
- ``write_manifest(path, manifest)`` — serialises to deterministic UTF-8 JSON
  and writes atomically.

``generated_at`` is the ONLY intentionally non-deterministic field in the
entire examen Gold output.  It is accepted as a caller-supplied string
(ISO8601) and lives only in the manifest; no other Gold bytes carry a
timestamp.

Usage::

    from examen.output.manifest import build_manifest, write_manifest
    from datetime import datetime, timezone

    m = build_manifest(
        semester="2026-1",
        course_slug="anatomy",
        exam_name="2026-1학기 기말고사",
        input_hashes={"8장.txt": "sha256:abc"},
        config_ids={"blueprint": "sha256:def"},
        generated_at=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        llm_backend="none(dry-run)",
        ...
    )
    write_manifest(gold_dir / "manifest_examen.json", m)
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Literal

from paideia_shared.schemas import ExamenManifest

from examen.output.paths import atomic_write


def build_manifest(
    *,
    semester: str,
    course_slug: str,
    exam_name: str,
    input_hashes: dict[str, str],
    config_ids: dict[str, str],
    generated_at: str,
    llm_backend: Literal["subscription", "api", "none(dry-run)"],
    llm_model: str | None,
    cache_hit_rate: float | None,
    item_count: int,
    source_breakdown: dict[str, int],
    difficulty_breakdown: dict[str, int],
    chapter_breakdown: dict[str, int],
    answer_no_distribution: dict[int, int],
    groundedness: dict[str, int],
    targets_vs_actual: dict[str, Any],
    emphasis_summary: dict[str, Any] | None = None,
) -> ExamenManifest:
    """Construct and validate an ExamenManifest.

    All fields are passed explicitly (no **kwargs magic) so that IDE
    completion and type checkers can verify caller correctness.

    Args:
        semester: Semester code validated by ``SemesterCode`` (e.g. ``"2026-1"``).
        course_slug: ASCII kebab-case slug (e.g. ``"anatomy"``).
        exam_name: Human-readable exam name (e.g. ``"2026-1학기 기말고사"``).
        input_hashes: Bronze input file → SHA-256 mapping.
        config_ids: Config file identifier mapping (blueprint, curriculum_map, etc.).
        generated_at: Wall-clock ISO8601 UTC string.  The only non-deterministic
            field in the examen Gold layer.
        llm_backend: One of ``"subscription"``, ``"api"``, ``"none(dry-run)"``.
        llm_model: LLM model identifier, or ``None`` for dry-run.
        cache_hit_rate: LLM cache hit rate (0.0–1.0), or ``None``.
        item_count: Total number of generated exam items.
        source_breakdown: Items per source (formative / quiz / textbook).
        difficulty_breakdown: Items per difficulty level.
        chapter_breakdown: Items per chapter.
        answer_no_distribution: Count per answer number (1–5).
        groundedness: ``{"확인": N, "미확인": M}`` grounding summary.
        targets_vs_actual: Targets vs. actual metrics dict.
        emphasis_summary: US7 lecture-emphasis aggregation summary
            (``{"sections_total", "emphasized", "by_chapter"}``), or ``None``.
            Recorded as a first-class manifest field so downstream immersio can
            consume emphasis strength independently of ``targets_vs_actual``.

    Returns:
        Validated ExamenManifest instance.

    Raises:
        pydantic.ValidationError: If any field fails schema validation.
    """
    return ExamenManifest.model_validate(
        {
            "semester": semester,
            "course_slug": course_slug,
            "exam_name": exam_name,
            "input_hashes": input_hashes,
            "config_ids": config_ids,
            "generated_at": generated_at,
            "llm_backend": llm_backend,
            "llm_model": llm_model,
            "cache_hit_rate": cache_hit_rate,
            "item_count": item_count,
            "source_breakdown": source_breakdown,
            "difficulty_breakdown": difficulty_breakdown,
            "chapter_breakdown": chapter_breakdown,
            "answer_no_distribution": answer_no_distribution,
            "groundedness": groundedness,
            "targets_vs_actual": targets_vs_actual,
            "emphasis_summary": emphasis_summary,
        }
    )


def write_manifest(path: Path, manifest: ExamenManifest) -> None:
    """Serialise ``manifest`` to a deterministic UTF-8 JSON file.

    Output properties:
    - ``sort_keys=True`` — alphabetical key order.
    - ``ensure_ascii=False`` — Korean characters written as-is.
    - ``indent=2`` — human-readable.
    - Written atomically (temp→rename, constitution V: 부분 산출 금지).
    - Parent directories are created if they do not exist.

    Args:
        path: Destination path (e.g. ``gold_dir / "manifest_examen.json"``).
        manifest: Validated ExamenManifest to write.
    """
    # Pydantic → dict, 그대로 JSON 직렬화 (int key 처리 포함)
    # 직렬화를 먼저 — 실패 시 디렉터리 부수효과 없음
    raw = manifest.model_dump(mode="json")
    serialized = json.dumps(
        raw,
        sort_keys=True,
        ensure_ascii=False,
        indent=2,
    )
    if not serialized.endswith("\n"):
        serialized += "\n"

    # 직렬화 성공 후에만 부모 디렉터리 생성
    path.parent.mkdir(parents=True, exist_ok=True)

    def _write(tmp: Path) -> None:
        tmp.write_text(serialized, encoding="utf-8")

    atomic_write(path, _write)


__all__ = ["build_manifest", "write_manifest"]
