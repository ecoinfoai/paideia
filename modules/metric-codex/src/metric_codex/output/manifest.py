"""T018 — MetricCodexManifest builder and writer.

Provides:
- ``build_manifest(**kwargs) -> MetricCodexManifest`` — constructs and validates
  the manifest via the shared Pydantic schema.
- ``write_manifest(manifest, path) -> None`` — serialises to deterministic UTF-8
  JSON and writes atomically.

``generated_at`` is the ONLY intentionally non-deterministic field.  It is
accepted as a caller-supplied ISO8601 string and lives only in the manifest;
no other Gold bytes carry a timestamp.

Usage::

    from metric_codex.output.manifest import build_manifest, write_manifest
    from datetime import datetime, timezone

    m = build_manifest(
        semester="2026-1",
        course_slug="anatomy",
        input_hashes={"grades.xlsx": "sha256:abc"},
        config_ids={"성적출석_map.yaml": "sha256:def"},
        generated_at=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        llm_backend="none(template)",
        llm_model=None,
        cache_hit_rate=None,
        student_count=42,
        entry_count=126,
        bundle_summary=summary,
    )
    write_manifest(gold_dir / "manifest_metric-codex.json", m)
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Literal

from paideia_shared.schemas import AdvisorBundleSummary, MetricCodexManifest

from metric_codex.output.determinism import atomic_write


def build_manifest(
    *,
    semester: str,
    course_slug: str,
    input_hashes: dict[str, str],
    config_ids: dict[str, str],
    generated_at: str,
    llm_backend: Literal["subscription", "api", "none(template)"],
    llm_model: str | None,
    cache_hit_rate: float | None,
    student_count: int,
    entry_count: int,
    bundle_summary: AdvisorBundleSummary,
) -> MetricCodexManifest:
    """Construct and validate a MetricCodexManifest.

    All fields are passed explicitly so IDE completion and type checkers
    can verify caller correctness.

    Args:
        semester: Semester code validated by ``SemesterCode`` (e.g. ``"2026-1"``).
        course_slug: ASCII kebab-case slug (e.g. ``"anatomy"``).
        input_hashes: source_id → SHA-256 hex digest of each input file.
        config_ids: Config file path → SHA-256 hex digest mapping.
        generated_at: Wall-clock ISO8601 UTC string.  The only non-deterministic
            field in the metric-codex Gold layer.
        llm_backend: One of ``"subscription"``, ``"api"``, ``"none(template)"``.
        llm_model: LLM model identifier, or ``None`` when backend is template.
        cache_hit_rate: LLM cache hit rate (0.0–1.0), or ``None`` when LLM unused.
        student_count: Number of distinct students with at least one CodexEntry.
        entry_count: Total number of CodexEntry rows written in this run.
        bundle_summary: Embedded advisor assignment coverage summary.

    Returns:
        Validated MetricCodexManifest instance.

    Raises:
        pydantic.ValidationError: If any field fails schema validation.
    """
    return MetricCodexManifest.model_validate(
        {
            "semester": semester,
            "course_slug": course_slug,
            "input_hashes": input_hashes,
            "config_ids": config_ids,
            "generated_at": generated_at,
            "llm_backend": llm_backend,
            "llm_model": llm_model,
            "cache_hit_rate": cache_hit_rate,
            "student_count": student_count,
            "entry_count": entry_count,
            "bundle_summary": bundle_summary.model_dump(),
        }
    )


def write_manifest(path: Path, manifest: MetricCodexManifest) -> None:
    """Serialise ``manifest`` to a deterministic UTF-8 JSON file.

    Output properties:
    - ``sort_keys=True`` — alphabetical key order.
    - ``ensure_ascii=False`` — Korean characters written as-is.
    - ``indent=2`` — human-readable.
    - Ends with exactly one newline.
    - Written atomically (temp→rename, constitution V: no partial output).
    - Parent directories are created if they do not exist.

    Args:
        path: Destination path (e.g. ``gold_dir / "manifest_metric-codex.json"``).
        manifest: Validated MetricCodexManifest to serialise.
    """
    # Serialise first — if it fails, no filesystem side-effect.
    raw = manifest.model_dump(mode="json")
    serialized = json.dumps(raw, sort_keys=True, ensure_ascii=False, indent=2)
    if not serialized.endswith("\n"):
        serialized += "\n"

    # Create parent directories only after successful serialisation.
    path.parent.mkdir(parents=True, exist_ok=True)

    def _write(tmp: Path) -> None:
        tmp.write_text(serialized, encoding="utf-8")

    atomic_write(path, _write)


__all__ = ["build_manifest", "write_manifest"]
