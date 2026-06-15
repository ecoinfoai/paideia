"""T020 — Manifest build and write for retro-mester Gold outputs.

Provides:
- ``build_manifest(..., when) -> RetroManifest`` — construct the audit
  manifest for one pipeline run.
- ``write_manifest(path, manifest, when) -> None`` — serialise as JSON with
  ``sort_keys=True`` and ``ensure_ascii=False``; ``generated_at_utc`` is the
  only field reflecting ``when`` so all other fields remain deterministic.

Design notes:
- Both functions accept an explicit ``when: datetime`` parameter (do NOT call
  ``datetime.now()`` here — callers supply it; tests pass a fixed value).
- JSON is written atomically via ``atomic_write_text`` so the file is never
  in a partial state.
"""

from __future__ import annotations

import datetime
import json
from pathlib import Path

from paideia_shared.schemas import RetroManifest

from retro_mester.output.manager import atomic_write_text


def build_manifest(
    *,
    when: datetime.datetime,
    module_version: str,
    schema_version: str,
    semester: str,
    course_slug: str,
    inputs: dict[str, str],
    thresholds: dict[str, float],
    counts: dict[str, float],
    degrade: dict[str, bool | str],
) -> RetroManifest:
    """Construct a ``RetroManifest`` for one pipeline run.

    Args:
        when: Run timestamp; used only to populate ``generated_at_utc``.
        module_version: retro-mester package version (SemVer).
        schema_version: paideia_shared schema version in use.
        semester: Semester code, e.g. ``"2026-1"``.
        course_slug: Kebab-case course identifier, e.g. ``"anatomy"``.
        inputs: Map of input artefact role → resolved file path.
        thresholds: Active threshold values from ``RetroMesterConfig``.
        counts: Row/item counts for key pipeline outputs.
        degrade: Degradation flags keyed by pipeline stage.

    Returns:
        Frozen ``RetroManifest`` instance.
    """
    generated_at_utc = when.strftime("%Y-%m-%dT%H:%M:%SZ")
    return RetroManifest(
        module_version=module_version,
        schema_version=schema_version,
        semester=semester,
        course_slug=course_slug,
        inputs=inputs,
        thresholds=thresholds,
        counts=counts,
        degrade=degrade,
        generated_at_utc=generated_at_utc,
    )


def write_manifest(path: Path, manifest: RetroManifest, when: datetime.datetime) -> None:
    """Serialise ``manifest`` to JSON at ``path``.

    Properties:
    - ``sort_keys=True`` — alphabetical key order.
    - ``ensure_ascii=False`` — Korean/Unicode characters written as-is.
    - ``generated_at_utc`` is the ONLY field that reflects ``when``; all
      other fields are taken verbatim from ``manifest`` so the output is
      byte-identical given the same inputs and the same ``when``.
    - Written atomically (temp-file + rename) — ``path`` never appears
      partially written.

    Args:
        path: Destination file path.  Parent directory must exist.
        manifest: The ``RetroManifest`` to serialise.
        when: Explicit run timestamp (used only if ``manifest`` was built
            with a different ``when`` — in normal use pass the same value
            as given to ``build_manifest``).
    """
    # model_dump() returns a plain dict; generated_at_utc is already set
    # inside the manifest from build_manifest, so we just serialise as-is.
    payload = manifest.model_dump()
    text = json.dumps(payload, sort_keys=True, ensure_ascii=False, indent=2) + "\n"
    atomic_write_text(path, text, encoding="utf-8")


__all__ = ["build_manifest", "write_manifest"]
