"""Unit tests for maieutica.ingest.report — T020.

TDD: failing tests written BEFORE implementation (RED → GREEN).

Covers:
- write_ingest_report: valid dict → deterministic UTF-8 JSON; sorted keys;
  Korean chars not escaped; parent dirs created; atomic (no partial on failure).
- Anomaly recording: filename violations and unexpected extras appear in the
  JSON; clean input yields zero anomalies.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

# ============================================================================
# T020 — write_ingest_report
# ============================================================================


class TestWriteIngestReport:
    def test_writes_valid_json(self, tmp_path: Path) -> None:
        """write_ingest_report writes valid JSON that round-trips correctly."""
        from maieutica.ingest.report import write_ingest_report

        report = {
            "textbook": {"chapters_required": 1, "chapters_found": 1},
            "anomalies": {"filename_violations": [], "unexpected_files": []},
        }
        dest = tmp_path / "ingest_report.json"
        write_ingest_report(dest, report)

        assert dest.exists()
        loaded = json.loads(dest.read_text(encoding="utf-8"))
        assert loaded["textbook"]["chapters_found"] == 1

    def test_deterministic_output(self, tmp_path: Path) -> None:
        """Two calls with same dict produce byte-identical files."""
        from maieutica.ingest.report import write_ingest_report

        report = {"a": 1, "z": 2, "m": {"nested": True}}
        p1 = tmp_path / "r1.json"
        p2 = tmp_path / "r2.json"
        write_ingest_report(p1, report)
        write_ingest_report(p2, report)
        assert p1.read_bytes() == p2.read_bytes()

    def test_keys_sorted_in_output(self, tmp_path: Path) -> None:
        """JSON output has alphabetically sorted keys."""
        from maieutica.ingest.report import write_ingest_report

        report = {"z_key": 1, "a_key": 2, "m_key": 3}
        dest = tmp_path / "report.json"
        write_ingest_report(dest, report)

        raw = dest.read_text(encoding="utf-8")
        keys_in_order = [
            line.split('"')[1]
            for line in raw.splitlines()
            if '"' in line and ":" in line
        ]
        assert keys_in_order[:3] == sorted(keys_in_order[:3])

    def test_unicode_not_escaped(self, tmp_path: Path) -> None:
        """Korean text is written as UTF-8, not \\uXXXX escaped."""
        from maieutica.ingest.report import write_ingest_report

        report = {"missing": ["8장 호흡계통.txt"]}
        dest = tmp_path / "report.json"
        write_ingest_report(dest, report)

        raw = dest.read_text(encoding="utf-8")
        assert "호흡계통" in raw, "Korean text must not be escaped"

    def test_atomic_no_partial_on_failure(self, tmp_path: Path) -> None:
        """TypeError from unserializable value → no partial file."""
        from maieutica.ingest.report import write_ingest_report

        dest = tmp_path / "report.json"
        with pytest.raises(TypeError):
            write_ingest_report(dest, {"bad": object()})
        assert not dest.exists(), "Partial file must not exist after failure"

    def test_creates_parent_directories(self, tmp_path: Path) -> None:
        """Parent directories are created automatically."""
        from maieutica.ingest.report import write_ingest_report

        dest = tmp_path / "sub" / "deep" / "ingest_report.json"
        write_ingest_report(dest, {"x": 1})
        assert dest.exists()


# ============================================================================
# T020 — anomaly recording (FR-021: anomalies recorded, not silently dropped)
# ============================================================================


class TestAnomalyRecording:
    """Anomalies are written to ingest_report.json; they are never silent."""

    def test_filename_violation_appears_in_report(self, tmp_path: Path) -> None:
        """A filename convention violation is recorded in anomalies."""
        from maieutica.ingest.report import write_ingest_report

        violation = "ch8_respiration.txt (expected '8장 …' format)"
        report = {
            "anomalies": {
                "filename_violations": [violation],
                "unexpected_files": [],
            }
        }
        dest = tmp_path / "ingest_report.json"
        write_ingest_report(dest, report)

        loaded = json.loads(dest.read_text(encoding="utf-8"))
        assert violation in loaded["anomalies"]["filename_violations"]

    def test_unexpected_extra_file_appears_in_report(self, tmp_path: Path) -> None:
        """An unexpected extra file in bronze_dir is recorded."""
        from maieutica.ingest.report import write_ingest_report

        extra = "random_notes.txt"
        report = {
            "anomalies": {
                "filename_violations": [],
                "unexpected_files": [extra],
            }
        }
        dest = tmp_path / "ingest_report.json"
        write_ingest_report(dest, report)

        loaded = json.loads(dest.read_text(encoding="utf-8"))
        assert extra in loaded["anomalies"]["unexpected_files"]

    def test_clean_input_yields_zero_anomalies(self, tmp_path: Path) -> None:
        """Clean input (no violations, no extras) yields empty anomaly lists."""
        from maieutica.ingest.report import write_ingest_report

        report = {
            "anomalies": {
                "filename_violations": [],
                "unexpected_files": [],
            }
        }
        dest = tmp_path / "ingest_report.json"
        write_ingest_report(dest, report)

        loaded = json.loads(dest.read_text(encoding="utf-8"))
        assert loaded["anomalies"]["filename_violations"] == []
        assert loaded["anomalies"]["unexpected_files"] == []
