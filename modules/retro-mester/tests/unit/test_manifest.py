"""T020 — Unit tests for retro_mester.output.manifest.

RED→GREEN: tests written first (no impl yet).

Tests:
- build_manifest returns a RetroManifest with correct fields.
- write_manifest writes valid JSON with sort_keys=True, ensure_ascii=False.
- Same inputs + same when → byte-identical JSON file (determinism).
- generated_at_utc reflects the ``when`` argument (not runtime clock).
"""

from __future__ import annotations

import datetime
import json
from pathlib import Path

_WHEN = datetime.datetime(2025, 6, 15, 9, 30, 0, tzinfo=datetime.UTC)
_WHEN_ISO = "2025-06-15T09:30:00Z"


def _sample_kwargs() -> dict:
    """Minimal valid kwargs for build_manifest."""
    return {
        "module_version": "0.1.1",
        "schema_version": "0.1.1",
        "semester": "2026-1",
        "course_slug": "anatomy",
        "inputs": {"examen_gold": "data/gold/examen/2026-1-anatomy/draft.xlsx"},
        "thresholds": {"pass_rate_min": 0.6, "gap_score_max": 30.0},
        "counts": {"total_items": 45.0, "gap_items": 3.0},
        "degrade": {"llm": False, "load": False},
    }


# ---------------------------------------------------------------------------
# build_manifest
# ---------------------------------------------------------------------------


def test_build_manifest_returns_retro_manifest() -> None:
    """build_manifest must return a RetroManifest instance."""
    from paideia_shared.schemas import RetroManifest
    from retro_mester.output.manifest import build_manifest

    result = build_manifest(when=_WHEN, **_sample_kwargs())
    assert isinstance(result, RetroManifest)


def test_build_manifest_fields() -> None:
    """build_manifest must populate all fields correctly."""
    from retro_mester.output.manifest import build_manifest

    kwargs = _sample_kwargs()
    result = build_manifest(when=_WHEN, **kwargs)

    assert result.module_version == "0.1.1"
    assert result.schema_version == "0.1.1"
    assert result.semester == "2026-1"
    assert result.course_slug == "anatomy"
    assert result.thresholds == {"pass_rate_min": 0.6, "gap_score_max": 30.0}
    assert result.counts == {"total_items": 45.0, "gap_items": 3.0}
    assert result.degrade == {"llm": False, "load": False}


def test_build_manifest_generated_at_reflects_when() -> None:
    """generated_at_utc must be the ISO-8601 UTC form of ``when``."""
    from retro_mester.output.manifest import build_manifest

    result = build_manifest(when=_WHEN, **_sample_kwargs())
    assert result.generated_at_utc == _WHEN_ISO


# ---------------------------------------------------------------------------
# write_manifest
# ---------------------------------------------------------------------------


def test_write_manifest_valid_json(tmp_path: Path) -> None:
    """write_manifest must produce a valid JSON file."""
    from retro_mester.output.manifest import build_manifest, write_manifest

    manifest = build_manifest(when=_WHEN, **_sample_kwargs())
    dest = tmp_path / "manifest_retro.json"
    write_manifest(dest, manifest, _WHEN)

    payload = json.loads(dest.read_text(encoding="utf-8"))
    assert isinstance(payload, dict)
    assert payload["module_version"] == "0.1.1"
    assert payload["generated_at_utc"] == _WHEN_ISO


def test_write_manifest_sort_keys(tmp_path: Path) -> None:
    """JSON output must have alphabetically sorted top-level keys."""
    from retro_mester.output.manifest import build_manifest, write_manifest

    manifest = build_manifest(when=_WHEN, **_sample_kwargs())
    dest = tmp_path / "manifest_retro.json"
    write_manifest(dest, manifest, _WHEN)

    raw = dest.read_text(encoding="utf-8")
    # Re-parse and check key order by searching position
    payload = json.loads(raw)
    keys = list(payload.keys())
    assert keys == sorted(keys), f"JSON keys not sorted: {keys}"


def test_write_manifest_unicode_not_escaped(tmp_path: Path) -> None:
    """Korean text in values must appear as-is (ensure_ascii=False)."""
    from retro_mester.output.manifest import build_manifest, write_manifest

    kwargs = _sample_kwargs()
    kwargs["inputs"]["교재"] = "data/bronze/textbook.pdf"
    manifest = build_manifest(when=_WHEN, **kwargs)
    dest = tmp_path / "manifest_retro.json"
    write_manifest(dest, manifest, _WHEN)

    raw = dest.read_text(encoding="utf-8")
    assert "교재" in raw, "Korean keys must not be escaped in JSON output"


def test_write_manifest_byte_identical(tmp_path: Path) -> None:
    """Same inputs + same when → byte-identical JSON on two separate writes."""
    from retro_mester.output.manifest import build_manifest, write_manifest

    manifest = build_manifest(when=_WHEN, **_sample_kwargs())

    dest_a = tmp_path / "a.json"
    dest_b = tmp_path / "b.json"
    write_manifest(dest_a, manifest, _WHEN)
    write_manifest(dest_b, manifest, _WHEN)

    assert dest_a.read_bytes() == dest_b.read_bytes(), (
        "write_manifest must be byte-identical for identical inputs and when"
    )


def test_write_manifest_generated_at_reflects_when_not_now(tmp_path: Path) -> None:
    """generated_at_utc in the file must match ``when``, not the real clock."""
    from retro_mester.output.manifest import build_manifest, write_manifest

    fixed_when = datetime.datetime(2000, 1, 1, 0, 0, 0, tzinfo=datetime.UTC)
    manifest = build_manifest(when=fixed_when, **_sample_kwargs())
    dest = tmp_path / "manifest_retro.json"
    write_manifest(dest, manifest, fixed_when)

    payload = json.loads(dest.read_text(encoding="utf-8"))
    assert payload["generated_at_utc"] == "2000-01-01T00:00:00Z"
