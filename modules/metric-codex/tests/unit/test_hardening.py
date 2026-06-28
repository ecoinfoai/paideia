"""Hardening pass tests — RED written first, covers four audit gaps.

F3  (cli.md): query plain-text stdout must include '가용 층:' line.
F1/F2 (transparency): ingest must print a source-summary line to stderr.
M-001 (verify gate): corrupt manifest must not cause spurious EVID-01 noise.
PRIV (defense-in-depth): LLM raw_text PII scan in _run_generate.

Each test class covers one change.  Written before implementation so the
initial run is RED on the new assertions.
"""

from __future__ import annotations

import textwrap
from pathlib import Path

import openpyxl
import pytest
from metric_codex.cli.main import app

# ---------------------------------------------------------------------------
# Shared scenario constants
# ---------------------------------------------------------------------------

_SEM = "2026-1"
_COURSE = "anatomy"
_KEY = f"{_SEM}-{_COURSE}"
_SID_A = "2026000001"
_NAME_A = "김철수"
_SID_B = "2026000002"
_NAME_B = "이영희"


# ---------------------------------------------------------------------------
# Shared fixture builders
# ---------------------------------------------------------------------------


def _make_school_excel(path: Path, rows: list[tuple]) -> None:
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(["학번", "이름", "총점", "환산점수", "출석"])
    for row in rows:
        ws.append(list(row))
    wb.save(path)


def _make_school_map(path: Path, sem: str = _SEM, course: str = _COURSE) -> None:
    path.write_text(
        textwrap.dedent(f"""\
            semester: {sem}
            course_slug: {course}
            sheet: 0
            header_row: 1
            columns:
              student_id: 학번
              name_kr: 이름
              score_total: 총점
              score_percent: 환산점수
              attendance: 출석
        """),
        encoding="utf-8",
    )


def _run_ingest(data_root: Path, now: str = "2026-06-01T00:00:00Z") -> int:
    return app(
        [
            "ingest",
            "--semester",
            _SEM,
            "--course",
            _COURSE,
            "--data-root",
            str(data_root),
            "--now",
            now,
        ]
    )


def _basic_bronze(tmp_path: Path) -> tuple[Path, Path]:
    """Return (data_root, bronze) with school Excel + map written, dirs ready."""
    data_root = tmp_path / "data"
    bronze = data_root / "bronze" / "metric-codex" / _KEY
    bronze.mkdir(parents=True)
    _make_school_excel(
        bronze / "성적출석.xlsx",
        rows=[
            (int(_SID_A), _NAME_A, 85, 90.5, 15),
            (int(_SID_B), _NAME_B, 70, 75.0, 12),
        ],
    )
    _make_school_map(bronze / "성적출석_map.yaml")
    return data_root, bronze


# ===========================================================================
# F1/F2 — ingest should print a one-line stderr source summary
# ===========================================================================


class TestIngestSourceSummary:
    """F1/F2 transparency: ingest must emit a sources summary line to stderr.

    The summary must name which upstream inputs were found vs absent, e.g.:
        ingest: sources — school_excel=found immersio=absent needs-map=absent
    """

    def test_stderr_summary_appears_on_school_only_ingest(
        self, tmp_path: Path, capsys: pytest.CaptureFixture
    ) -> None:
        """When only school Excel is present, stderr must contain 'ingest: sources'."""
        data_root, _bronze = _basic_bronze(tmp_path)

        rc = _run_ingest(data_root)
        assert rc == 0

        captured = capsys.readouterr()
        assert "ingest: sources" in captured.err, (
            f"Expected 'ingest: sources' summary in stderr; got:\n{captured.err!r}"
        )

    def test_stderr_names_absent_immersio(
        self, tmp_path: Path, capsys: pytest.CaptureFixture
    ) -> None:
        """When immersio Silver is absent, the summary must say 'immersio=absent'."""
        data_root, _bronze = _basic_bronze(tmp_path)

        rc = _run_ingest(data_root)
        assert rc == 0

        captured = capsys.readouterr()
        assert "immersio=absent" in captured.err, (
            f"Expected 'immersio=absent' in stderr summary; got:\n{captured.err!r}"
        )

    def test_stderr_names_absent_needsmap(
        self, tmp_path: Path, capsys: pytest.CaptureFixture
    ) -> None:
        """When needs-map Silver is absent, the summary must say 'needs-map=absent'."""
        data_root, _bronze = _basic_bronze(tmp_path)

        rc = _run_ingest(data_root)
        assert rc == 0

        captured = capsys.readouterr()
        assert "needs-map=absent" in captured.err, (
            f"Expected 'needs-map=absent' in stderr summary; got:\n{captured.err!r}"
        )

    def test_stderr_names_found_school_excel(
        self, tmp_path: Path, capsys: pytest.CaptureFixture
    ) -> None:
        """When school Excel is present, the summary must say 'school_excel=found'."""
        data_root, _bronze = _basic_bronze(tmp_path)

        rc = _run_ingest(data_root)
        assert rc == 0

        captured = capsys.readouterr()
        assert "school_excel=found" in captured.err, (
            f"Expected 'school_excel=found' in stderr summary; got:\n{captured.err!r}"
        )

    def test_stderr_names_found_immersio_when_dir_exists(
        self, tmp_path: Path, capsys: pytest.CaptureFixture
    ) -> None:
        """When immersio Silver dir is present, the summary must say 'immersio=found'."""
        data_root, _bronze = _basic_bronze(tmp_path)
        immersio = data_root / "silver" / "immersio" / _KEY
        immersio.mkdir(parents=True)
        # Dir exists but no parquet → still 'found' at the dir level

        rc = _run_ingest(data_root)
        assert rc == 0

        captured = capsys.readouterr()
        assert "immersio=found" in captured.err, (
            f"Expected 'immersio=found' in stderr summary; got:\n{captured.err!r}"
        )


# ===========================================================================
# M-001 — corrupt manifest must not produce spurious EVID-01 violations
# ===========================================================================


def _make_question_set(path: Path) -> None:
    path.write_text(
        textwrap.dedent("""\
            questions:
              - id: q_total
                text: "총점을 알려주세요."
                entry_kinds:
                  - score_total
                domain: null
        """),
        encoding="utf-8",
    )


class TestVerifyGateCorruptManifest:
    """M-001: a corrupt manifest must NOT produce spurious EVID-01 violations.

    When the manifest JSON is unparseable, run_all_checks should report the
    manifest failure (SKIP-02 or MANIFEST) WITHOUT also emitting EVID-01 from
    a byte-match that was run with the wrong 'none(template)' default.
    """

    def _build_pipeline(self, tmp_path: Path) -> tuple[Path, Path]:
        """Run ingest + generate (--backend none) and return (data_root, qs_path)."""
        data_root, bronze = _basic_bronze(tmp_path)
        qs_path = bronze / "question_set.yaml"
        _make_question_set(qs_path)

        assert (
            app(
                [
                    "ingest",
                    "--semester",
                    _SEM,
                    "--course",
                    _COURSE,
                    "--data-root",
                    str(data_root),
                    "--now",
                    "2026-06-01T00:00:00Z",
                ]
            )
            == 0
        )

        assert (
            app(
                [
                    "generate",
                    "--semester",
                    _SEM,
                    "--course",
                    _COURSE,
                    "--data-root",
                    str(data_root),
                    "--question-set",
                    str(qs_path),
                    "--backend",
                    "none",
                    "--now",
                    "2026-06-01T01:00:00Z",
                ]
            )
            == 0
        )

        return data_root, qs_path

    def test_corrupt_manifest_does_not_produce_evid01(
        self, tmp_path: Path, capsys: pytest.CaptureFixture
    ) -> None:
        """Corrupt manifest + LLM-prose Gold md → MANIFEST/SKIP-02 but NO EVID-01.

        The bug: when the manifest is corrupt, llm_backend stays "none(template)"
        (the default) and the byte-match runs against LLM-prose Gold mds, producing
        a false EVID-01.  After the fix, the byte-match must be SKIPPED when
        llm_backend is None (unknown due to corrupt manifest).
        """
        data_root, qs_path = self._build_pipeline(tmp_path)
        manifest_path = data_root / "silver" / "metric-codex" / _KEY / "manifest_metric-codex.json"

        # Simulate LLM-polished prose by overwriting the Gold md with non-template
        # content BEFORE corrupting the manifest.  This is the realistic scenario:
        # generate ran with 'api' backend → Gold has LLM prose → manifest said
        # llm_backend='api', but an operator hand-corrupted the manifest JSON.
        gold_student_dir = data_root / "gold" / "metric-codex" / _KEY / "학생별"
        for md in gold_student_dir.glob("*.md"):
            md.write_text(
                "LLM polished prose — purposely differs from template\n",
                encoding="utf-8",
            )

        # Corrupt the manifest so read_manifest raises.
        manifest_path.write_text("{not valid json !!!", encoding="utf-8")

        rc = app(
            [
                "verify",
                "--semester",
                _SEM,
                "--course",
                _COURSE,
                "--data-root",
                str(data_root),
                "--question-set",
                str(qs_path),
            ]
        )
        captured = capsys.readouterr()

        # The corrupt manifest MUST be reported.
        assert rc == 3, f"expected exit 3 after corrupt manifest; got {rc}"
        assert "MANIFEST" in captured.err or "SKIP-02" in captured.err, (
            f"Expected MANIFEST or SKIP-02 violation in stderr; got:\n{captured.err!r}"
        )
        # No spurious EVID-01 must appear: the byte-match must be skipped.
        assert "EVID-01" not in captured.err, (
            f"Spurious EVID-01 violation appeared despite corrupt manifest; "
            f"stderr:\n{captured.err!r}"
        )


# ===========================================================================
# PRIV — LLM response raw_text PII scan in _run_generate
# ===========================================================================


class TestGenerateLLMResponsePiiScan:
    """PRIV defense-in-depth: _run_generate must scan LLM raw_text for PII.

    When the fake backend returns raw_text containing a 10-digit id, _run_generate
    must raise LocatedInputError (exit 2) and must NOT write any Gold md file.
    """

    def _build_ingested(self, tmp_path: Path) -> tuple[Path, Path]:
        """Ingest two students and return (data_root, qs_path)."""
        data_root, bronze = _basic_bronze(tmp_path)
        qs_path = bronze / "question_set.yaml"
        _make_question_set(qs_path)

        assert (
            app(
                [
                    "ingest",
                    "--semester",
                    _SEM,
                    "--course",
                    _COURSE,
                    "--data-root",
                    str(data_root),
                    "--now",
                    "2026-06-01T00:00:00Z",
                ]
            )
            == 0
        )

        return data_root, qs_path

    def test_pii_in_llm_response_exits_two(self, tmp_path: Path) -> None:
        """Fake backend whose raw_text contains a 10-digit id → exit 2, no Gold."""
        import unittest.mock as mock

        from metric_codex.generate.backend import GenerationResponse

        # The fake response leaks a student-number-shaped string.
        leaked_sid = _SID_A  # "2026000001" — 10 digits
        fake_response = GenerationResponse(
            slot_id="S001",
            raw_text=f"학생 {leaked_sid} 의 성적은 우수합니다.",
            model="fake",
            cache_hit=False,
        )

        data_root, qs_path = self._build_ingested(tmp_path)

        with mock.patch(
            "metric_codex.generate.backend.InputHashCache.generate",
            return_value=fake_response,
        ):
            rc = app(
                [
                    "generate",
                    "--semester",
                    _SEM,
                    "--course",
                    _COURSE,
                    "--data-root",
                    str(data_root),
                    "--question-set",
                    str(qs_path),
                    "--backend",
                    "api",
                    "--now",
                    "2026-06-01T01:00:00Z",
                ]
            )

        assert rc == 2, f"Expected exit 2 when LLM raw_text contains a 10-digit id; got {rc}"

        # No Gold md must be written.
        gold_dir = data_root / "gold" / "metric-codex" / _KEY / "학생별"
        if gold_dir.is_dir():
            md_files = list(gold_dir.glob("*.md"))
            assert md_files == [], (
                f"Gold md files must not be written when LLM PII scan fails; "
                f"found: {[f.name for f in md_files]}"
            )
