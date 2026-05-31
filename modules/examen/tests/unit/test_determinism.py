"""Unit tests for examen.output.determinism — T014.

TDD: tests written BEFORE implementation.
"""

from __future__ import annotations

import datetime
import json as _json
import re
import zipfile
from pathlib import Path
from typing import Any as _Any

from examen.generate.backend import (
    GenerationRequest,
    GenerationResponse,
    LLMBackend,
)
from paideia_shared.schemas import (
    CurriculumEntry,
    CurriculumMap,
    ExamenBlueprint,
)

# ---------------------------------------------------------------------------
# finalize_xlsx
# ---------------------------------------------------------------------------

def _make_minimal_xlsx(path: Path) -> None:
    """Create a minimal XLSX file with a docProps/core.xml containing dcterms:modified."""
    import openpyxl

    wb = openpyxl.Workbook()
    wb.save(str(path))


class TestFinalizeXlsx:
    def test_dcterms_modified_is_pinned(self, tmp_path: Path) -> None:
        """After finalize_xlsx, docProps/core.xml dcterms:modified equals the pinned value."""
        from examen.output.determinism import finalize_xlsx

        xlsx = tmp_path / "test.xlsx"
        _make_minimal_xlsx(xlsx)

        when = datetime.datetime(2026, 1, 1, 0, 0, 0)
        finalize_xlsx(xlsx, when)

        with zipfile.ZipFile(xlsx, "r") as zf:
            core_xml = zf.read("docProps/core.xml").decode("utf-8")

        modified_re = re.compile(r"<dcterms:modified[^>]*>([^<]+)</dcterms:modified>")
        match = modified_re.search(core_xml)
        assert match, "dcterms:modified not found in core.xml"
        assert match.group(1) == "2026-01-01T00:00:00Z"

    def test_two_calls_produce_byte_identical_output(self, tmp_path: Path) -> None:
        """Two sequential finalize_xlsx calls on separate copies produce identical bytes."""
        from examen.output.determinism import finalize_xlsx

        xlsx_a = tmp_path / "a.xlsx"
        xlsx_b = tmp_path / "b.xlsx"
        _make_minimal_xlsx(xlsx_a)
        _make_minimal_xlsx(xlsx_b)

        when = datetime.datetime(2026, 3, 15, 12, 0, 0)
        finalize_xlsx(xlsx_a, when)
        finalize_xlsx(xlsx_b, when)

        assert xlsx_a.read_bytes() == xlsx_b.read_bytes(), (
            "finalize_xlsx must produce byte-identical output for identical inputs"
        )

    def test_dcterms_created_is_pinned(self, tmp_path: Path) -> None:
        """After finalize_xlsx, docProps/core.xml dcterms:created equals the pinned value.

        Regression: openpyxl stamps BOTH <dcterms:created> and <dcterms:modified>
        with datetime.now().  Pinning only <dcterms:modified> left <dcterms:created>
        time-based → two runs straddling a second boundary diverged (the
        intermittent full-suite test_rerun_xlsx_byte_identical flake).
        """
        from examen.output.determinism import finalize_xlsx

        xlsx = tmp_path / "test_created.xlsx"
        _make_minimal_xlsx(xlsx)

        when = datetime.datetime(2026, 1, 1, 0, 0, 0)
        finalize_xlsx(xlsx, when)

        with zipfile.ZipFile(xlsx, "r") as zf:
            core_xml = zf.read("docProps/core.xml").decode("utf-8")

        created_re = re.compile(r"<dcterms:created[^>]*>([^<]+)</dcterms:created>")
        match = created_re.search(core_xml)
        assert match, "dcterms:created not found in core.xml"
        assert match.group(1) == "2026-01-01T00:00:00Z", (
            f"dcterms:created not pinned: {match.group(1)!r}"
        )

    def test_byte_identical_when_created_timestamps_differ(self, tmp_path: Path) -> None:
        """Two xlsx with DIFFERENT openpyxl created timestamps finalize byte-identical.

        Simulates the real flake: build #1 and build #2 of build_exam land in
        different wall-clock seconds, so openpyxl writes different
        <dcterms:created>.  finalize_xlsx must normalise BOTH so the bytes match.
        """
        from examen.output.determinism import finalize_xlsx

        xlsx_a = tmp_path / "created_a.xlsx"
        xlsx_b = tmp_path / "created_b.xlsx"
        _make_minimal_xlsx(xlsx_a)
        _make_minimal_xlsx(xlsx_b)

        # Inject DIFFERENT created/modified timestamps into the two core.xml,
        # mimicking openpyxl writing at two different wall-clock seconds.
        def _inject_core(path: Path, ts: str) -> None:
            import io

            with zipfile.ZipFile(path, "r") as src:
                members = [(i.filename, src.read(i.filename), i.compress_type)
                           for i in src.infolist()]
            buf = io.BytesIO()
            with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as dst:
                for name, data, ct in members:
                    if name == "docProps/core.xml":
                        text = data.decode("utf-8")
                        text = re.sub(
                            r"(<dcterms:created[^>]*>)[^<]+(</dcterms:created>)",
                            rf"\g<1>{ts}\g<2>", text)
                        text = re.sub(
                            r"(<dcterms:modified[^>]*>)[^<]+(</dcterms:modified>)",
                            rf"\g<1>{ts}\g<2>", text)
                        data = text.encode("utf-8")
                    dst.writestr(name, data, compress_type=ct)
            path.write_bytes(buf.getvalue())

        _inject_core(xlsx_a, "2026-05-31T08:00:01Z")
        _inject_core(xlsx_b, "2026-05-31T08:00:02Z")  # 1 second later

        when = datetime.datetime(2026, 1, 1, 0, 0, 0)
        finalize_xlsx(xlsx_a, when)
        finalize_xlsx(xlsx_b, when)

        assert xlsx_a.read_bytes() == xlsx_b.read_bytes(), (
            "finalize_xlsx must produce byte-identical output even when the source "
            "xlsx had different <dcterms:created> timestamps"
        )

    def test_zip_entries_use_fixed_date_time(self, tmp_path: Path) -> None:
        """All zip entries use the fixed date_time (1980,1,1,0,0,0)."""
        from examen.output.determinism import finalize_xlsx

        xlsx = tmp_path / "fixed_date.xlsx"
        _make_minimal_xlsx(xlsx)
        finalize_xlsx(xlsx, datetime.datetime(2026, 1, 1))

        with zipfile.ZipFile(xlsx, "r") as zf:
            for info in zf.infolist():
                assert info.date_time == (1980, 1, 1, 0, 0, 0), (
                    f"Entry {info.filename!r} has date_time {info.date_time}, expected (1980,1,1,0,0,0)"
                )


# ---------------------------------------------------------------------------
# dump_yaml
# ---------------------------------------------------------------------------

class TestDumpYaml:
    def test_byte_identical_across_two_calls(self) -> None:
        """dump_yaml is deterministic: two calls with same input produce identical output."""
        from examen.output.determinism import dump_yaml

        obj = {"z_key": "value", "a_key": 42, "m_key": [1, 2, 3]}
        r1 = dump_yaml(obj)
        r2 = dump_yaml(obj)
        assert r1 == r2

    def test_unicode_preserved(self) -> None:
        """Korean characters are preserved, not escaped."""
        from examen.output.determinism import dump_yaml

        obj = {"제목": "기말고사", "항목": ["호흡계통", "근육계통"]}
        result = dump_yaml(obj)
        assert "기말고사" in result
        assert "호흡계통" in result
        # Must not be escaped (no \\uXXXX)
        assert "\\u" not in result

    def test_sorted_keys(self) -> None:
        """Keys are sorted alphabetically for determinism."""
        from examen.output.determinism import dump_yaml

        obj = {"z": 1, "a": 2, "m": 3}
        result = dump_yaml(obj)
        lines = [line for line in result.splitlines() if ":" in line]
        keys = [line.split(":")[0].strip() for line in lines]
        assert keys == sorted(keys), f"Keys not sorted: {keys}"

    def test_roundtrip(self) -> None:
        """dump_yaml output can be parsed back to the original object."""
        import yaml as pyyaml
        from examen.output.determinism import dump_yaml

        obj = {"key": "value", "nested": {"a": 1, "b": 2}, "list": [1, 2, 3]}
        dumped = dump_yaml(obj)
        restored = pyyaml.safe_load(dumped)
        assert restored == obj

    def test_ends_with_newline(self) -> None:
        """YAML output ends with exactly one newline."""
        from examen.output.determinism import dump_yaml

        result = dump_yaml({"x": 1})
        assert result.endswith("\n"), "YAML must end with a newline"
        assert not result.endswith("\n\n"), "YAML must not end with double newline"


# ---------------------------------------------------------------------------
# parquet_write_options
# ---------------------------------------------------------------------------

class TestParquetWriteOptions:
    def test_returns_expected_flags(self) -> None:
        """parquet_write_options returns dict with use_dictionary=False, write_statistics=False."""
        from examen.output.determinism import parquet_write_options

        opts = parquet_write_options()
        assert opts["use_dictionary"] is False
        assert opts["write_statistics"] is False

    def test_compression_is_snappy(self) -> None:
        """Default compression is snappy (matches immersio pattern)."""
        from examen.output.determinism import parquet_write_options

        opts = parquet_write_options()
        assert opts.get("compression") == "snappy"


# ---------------------------------------------------------------------------
# T060 — Pipeline-level determinism property test
#   - re-run byte-identical (xlsx / yaml)
#   - SC-012: 자동 생성 호출 수 ≤ 미캐시 슬롯 수 (warm cache → 0 calls)
# ---------------------------------------------------------------------------

_DET_SEMESTER = "2026-1"
_DET_COURSE = "anatomy"
_DET_CHAPTERS = ["8장 호흡계통", "9장 근육계통", "10장 소화계통"]
_DET_CHAPTER_NOS = [8, 9, 10]
_DET_WEEKS = [8, 9, 10]
_DET_TOTAL = 42  # 3 chapters × 14 textbook items (ExamenBlueprint requires ≥40)


def _det_canned_json(answer_no: int = 1) -> dict[str, _Any]:
    return {
        "question_type": "지식축적",
        "difficulty": "2_보통",
        "stem_polarity": "부정형",
        "text": "다음 중 폐포에 대한 설명으로 가장 옳지 않은 것은?",
        "options": [
            "① " + "가" * 28,
            "② " + "나" * 28,
            "③ " + "다" * 28,
            "④ " + "라" * 28,
            "⑤ " + "마" * 28,
        ],
        "answer_no": answer_no,
        "distractor_rationale": [
            "옳은 진술: 가.",
            "옳은 진술: 나.",
            "옳은 진술: 다.",
            "옳은 진술: 라.",
            "옳은 진술: 마.",
        ],
        "wrong_explanation": "오답 설명 텍스트입니다." * 20,
        "leap_explanation": "도약 설명 텍스트입니다." * 20,
        "intent": "기본 구조와 기능을 확인한다.",
        "key_concept": None,
    }


class _DetCountingBackend(LLMBackend):
    """Textbook-only FakeBackend that counts generate() calls (SC-012)."""

    def __init__(self) -> None:
        self.call_count = 0

    def generate(self, request: GenerationRequest) -> GenerationResponse:
        self.call_count += 1
        return GenerationResponse(
            slot_id=request.slot_id,
            raw_text=_json.dumps(_det_canned_json(), ensure_ascii=False),
            model="fake-det",
            cache_hit=False,
        )


def _det_blueprint() -> ExamenBlueprint:
    return ExamenBlueprint(
        semester=_DET_SEMESTER,
        course_slug=_DET_COURSE,
        exam_name="결정성 테스트",
        total_items=_DET_TOTAL,
        chapters=_DET_CHAPTERS,
        difficulty_targets={"easy": 0.45, "medium": 0.35, "hard": 0.20},
        source_mix={"textbook": _DET_TOTAL, "formative": 0, "quiz": 0},
        answer_key_balance=True,
    )


def _det_curriculum_map() -> CurriculumMap:
    entries = [
        CurriculumEntry(
            week=w, chapter=c, chapter_no=n, subtopic=None,
            sections=["1. 기본구조", "2. 기능"],
        )
        for w, c, n in zip(_DET_WEEKS, _DET_CHAPTERS, _DET_CHAPTER_NOS, strict=False)
    ]
    return CurriculumMap(semester=_DET_SEMESTER, course_slug=_DET_COURSE, entries=entries)


def _det_setup_bronze(bronze_dir: Path) -> None:
    bronze_dir.mkdir(parents=True, exist_ok=True)
    for n, c in zip(_DET_CHAPTER_NOS, _DET_CHAPTERS, strict=False):
        name = c.split(" ", 1)[1]
        (bronze_dir / f"{c}.txt").write_text(
            f"{c}\n1. 기본구조\n{name}에 관한 주요 내용.\n기관들이 연결되어 있다.\n2. 기능\n{name}의 기능.\n",
            encoding="utf-8",
        )


def _det_run(tmp_path: Path, backend: LLMBackend) -> tuple[list, Path]:
    from examen.pipeline import build_exam

    bronze_dir = tmp_path / "data" / "bronze" / "examen" / f"{_DET_SEMESTER}-{_DET_COURSE}"
    _det_setup_bronze(bronze_dir)
    return build_exam(
        blueprint=_det_blueprint(),
        curriculum_map=_det_curriculum_map(),
        bronze_dir=bronze_dir,
        data_root=tmp_path / "data",
        backend=backend,
    )


class TestPipelineDeterminism:
    """Full build_exam determinism + SC-012 cache call-count property."""

    def test_rerun_xlsx_yaml_byte_identical(self, tmp_path: Path) -> None:
        """Two builds on the SAME tmp data_root (warm cache) → identical xlsx + yaml bytes."""
        items1, run1 = _det_run(tmp_path, _DetCountingBackend())
        items2, run2 = _det_run(tmp_path, _DetCountingBackend())
        assert run1 == run2, "Identical inputs must map to the same run_id Gold dir"
        for name in ("기말출제초안.xlsx", "기말출제초안.yaml"):
            assert (run1 / name).read_bytes() == (run2 / name).read_bytes(), (
                f"{name} must be byte-identical across identical-input re-runs"
            )

    def test_sc012_calls_le_uncached_slots(self, tmp_path: Path) -> None:
        """SC-012: first run calls == #slots (all uncached); warm-cache run makes 0 calls."""
        b1 = _DetCountingBackend()
        items1, _ = _det_run(tmp_path, b1)
        n_slots = len(items1)
        # Cold cache: one call per slot, never more than the uncached-slot count.
        assert b1.call_count == n_slots, (
            f"cold-cache backend calls ({b1.call_count}) must equal slot count ({n_slots})"
        )

        # Warm cache (same data_root → cache persisted under silver): 0 calls.
        b2 = _DetCountingBackend()
        _det_run(tmp_path, b2)
        assert b2.call_count == 0, (
            f"warm-cache backend must make 0 calls (made {b2.call_count}); "
            "cache must short-circuit every previously-generated slot"
        )
        # Invariant restated: calls ≤ number of uncached slots in both runs.
        assert b2.call_count <= n_slots

    def test_manifest_only_differs_by_generated_at(self, tmp_path: Path) -> None:
        """Re-run manifests are identical except for the generated_at timestamp."""
        _, run1 = _det_run(tmp_path, _DetCountingBackend())
        m1 = _json.loads((run1 / "manifest_examen.json").read_text(encoding="utf-8"))
        _, run2 = _det_run(tmp_path, _DetCountingBackend())
        m2 = _json.loads((run2 / "manifest_examen.json").read_text(encoding="utf-8"))
        m1.pop("generated_at", None)
        m2.pop("generated_at", None)
        # cache_hit_rate legitimately differs (cold vs warm) — normalise it out.
        m1.pop("cache_hit_rate", None)
        m2.pop("cache_hit_rate", None)
        assert m1 == m2, "Manifest must be stable apart from generated_at / cache_hit_rate"
