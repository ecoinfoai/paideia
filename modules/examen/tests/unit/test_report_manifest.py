"""Unit tests for examen.ingest.report and examen.output.manifest — T017.

TDD: tests written BEFORE implementation.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# T017 — ingest_report writer
# ---------------------------------------------------------------------------

class TestWriteIngestReport:
    def test_writes_valid_json(self, tmp_path: Path) -> None:
        from examen.ingest.report import write_ingest_report

        report = {
            "stt": {"expected": 48, "found": 47, "missing": ["1C_11주차_2차시"], "filename_violations": []},
            "textbook": {"chapters_required": 6, "chapters_found": 6, "removed_span_counts": {"8장": 31}},
            "formative": {"expected_total": 12, "found": 12},
            "quiz": {"weeks": [9, 10, 11, 12, 13], "rows": 60},
        }
        dest = tmp_path / "ingest_report.json"
        write_ingest_report(dest, report)

        assert dest.exists()
        loaded = json.loads(dest.read_text(encoding="utf-8"))
        assert loaded["stt"]["found"] == 47

    def test_deterministic_json_output(self, tmp_path: Path) -> None:
        """Two calls with same dict produce byte-identical files."""
        from examen.ingest.report import write_ingest_report

        report = {"a": 1, "z": 2, "m": {"nested": True}}
        p1 = tmp_path / "r1.json"
        p2 = tmp_path / "r2.json"
        write_ingest_report(p1, report)
        write_ingest_report(p2, report)
        assert p1.read_bytes() == p2.read_bytes()

    def test_keys_sorted_in_output(self, tmp_path: Path) -> None:
        """JSON output has keys sorted (sort_keys=True)."""
        from examen.ingest.report import write_ingest_report

        report = {"z_key": 1, "a_key": 2, "m_key": 3}
        dest = tmp_path / "report.json"
        write_ingest_report(dest, report)

        raw = dest.read_text(encoding="utf-8")
        # Verify by parsing the raw text order
        keys_in_order = [
            line.split('"')[1]
            for line in raw.splitlines()
            if '"' in line and ":" in line
        ]
        assert keys_in_order == sorted(keys_in_order[:3])

    def test_unicode_not_escaped(self, tmp_path: Path) -> None:
        """Korean text is written as UTF-8, not \\uXXXX escaped."""
        from examen.ingest.report import write_ingest_report

        report = {"missing": ["1C_11주차_2차시"]}
        dest = tmp_path / "report.json"
        write_ingest_report(dest, report)

        raw = dest.read_text(encoding="utf-8")
        assert "주차" in raw, "Korean text must not be escaped"

    def test_atomic_no_partial_on_failure(self, tmp_path: Path) -> None:
        """If an error occurs, no partial file is left behind."""
        from examen.ingest.report import write_ingest_report

        # Pass an unserializable object
        dest = tmp_path / "report.json"
        with pytest.raises(TypeError):
            write_ingest_report(dest, {"bad": object()})

        assert not dest.exists(), "Partial file must not exist after failure"

    def test_creates_parent_directories(self, tmp_path: Path) -> None:
        """Parent directories are created if they don't exist."""
        from examen.ingest.report import write_ingest_report

        dest = tmp_path / "sub" / "deep" / "ingest_report.json"
        write_ingest_report(dest, {"x": 1})
        assert dest.exists()


# ---------------------------------------------------------------------------
# T017 — build_manifest and write_manifest
# ---------------------------------------------------------------------------

def _make_valid_manifest_kwargs() -> dict:
    return {
        "semester": "2026-1",
        "course_slug": "anatomy",
        "exam_name": "2026-1학기 기말고사",
        "input_hashes": {"8장.txt": "sha256:abc"},
        "config_ids": {"blueprint": "sha256:def"},
        "generated_at": "2026-06-01T10:00:00Z",
        "llm_backend": "none(dry-run)",
        "llm_model": None,
        "cache_hit_rate": None,
        "item_count": 48,
        "source_breakdown": {"formative": 12, "quiz": 15, "textbook": 21},
        "difficulty_breakdown": {"쉬움": 22, "보통": 17, "어려움": 9},
        "chapter_breakdown": {"8장. 호흡계통": 8},
        "answer_no_distribution": {1: 10, 2: 10, 3: 9, 4: 9, 5: 10},
        "groundedness": {"확인": 47, "미확인": 1},
        "targets_vs_actual": {},
    }


class TestBuildManifest:
    def test_build_returns_examen_manifest(self) -> None:
        from examen.output.manifest import build_manifest
        from paideia_shared.schemas import ExamenManifest

        kwargs = _make_valid_manifest_kwargs()
        m = build_manifest(**kwargs)
        assert isinstance(m, ExamenManifest)
        assert m.item_count == 48

    def test_build_accepts_llm_backends(self) -> None:
        from examen.output.manifest import build_manifest

        for backend in ("subscription", "api", "none(dry-run)"):
            kwargs = _make_valid_manifest_kwargs()
            kwargs["llm_backend"] = backend
            m = build_manifest(**kwargs)
            assert m.llm_backend == backend


class TestWriteManifest:
    def test_writes_valid_json(self, tmp_path: Path) -> None:
        from examen.output.manifest import build_manifest, write_manifest
        from paideia_shared.schemas import ExamenManifest

        m = build_manifest(**_make_valid_manifest_kwargs())
        dest = tmp_path / "manifest_examen.json"
        write_manifest(dest, m)

        assert dest.exists()
        raw = json.loads(dest.read_text(encoding="utf-8"))
        # Round-trip schema validation
        m2 = ExamenManifest.model_validate(raw)
        assert m2.semester == m.semester

    def test_creates_parent_directories(self, tmp_path: Path) -> None:
        """Parent directories are created if they do not exist."""
        from examen.output.manifest import build_manifest, write_manifest

        m = build_manifest(**_make_valid_manifest_kwargs())
        dest = tmp_path / "deep" / "sub" / "manifest_examen.json"
        write_manifest(dest, m)
        assert dest.exists()

    def test_atomic_no_partial_on_write_failure(self, tmp_path: Path) -> None:
        """On a hard write failure, no partial file and no leftover .tmp_* remain."""
        from examen.output.manifest import build_manifest, write_manifest

        m = build_manifest(**_make_valid_manifest_kwargs())
        # Target path is itself a directory → os.replace(tmp, dest) raises.
        dest = tmp_path / "manifest_examen.json"
        dest.mkdir()

        with pytest.raises(OSError):
            write_manifest(dest, m)

        # The directory still exists, but no temp file should be orphaned.
        assert dest.is_dir()
        assert not list(tmp_path.glob(".tmp_*")), "orphaned temp file left behind"

    def test_generated_at_only_non_deterministic_field(self, tmp_path: Path) -> None:
        """Two manifests with the same generated_at produce byte-identical files."""
        from examen.output.manifest import build_manifest, write_manifest

        kwargs = _make_valid_manifest_kwargs()
        m1 = build_manifest(**kwargs)
        m2 = build_manifest(**kwargs)

        p1 = tmp_path / "m1.json"
        p2 = tmp_path / "m2.json"
        write_manifest(p1, m1)
        write_manifest(p2, m2)
        assert p1.read_bytes() == p2.read_bytes()

    def test_unicode_not_escaped(self, tmp_path: Path) -> None:
        """Korean characters in manifest are written as UTF-8."""
        from examen.output.manifest import build_manifest, write_manifest

        m = build_manifest(**_make_valid_manifest_kwargs())
        dest = tmp_path / "manifest.json"
        write_manifest(dest, m)
        raw = dest.read_text(encoding="utf-8")
        assert "쉬움" in raw  # Korean written as UTF-8, not \\uXXXX
        assert "\\u" not in raw
