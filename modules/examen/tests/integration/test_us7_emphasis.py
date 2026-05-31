"""T054 — Integration: lecture-emphasis enrichment (US7).

TDD (RED phase): tests written before implementation.

Covers:
1. Degrade — ``build_exam(..., stt_dir=None)`` (or nonexistent dir) completes;
   items have ``is_emphasized is None``; ingest_report stt is zeros. (SC-013)
2. Intersection with a missing session — a keyword in ALL available classes →
   ``is_emphasized=True`` and ``emphasized==available``; a missing session is
   excluded from availability (NOT counted as "not emphasized") and is flagged
   in ingest_report stt.missing.
3. Partial emphasis — keyword in only some classes → ``is_emphasized=False`` and
   ``emphasized < available``.
4. Filename violation — a malformed STT filename is recorded in
   ingest_report stt.filename_violations (never silently dropped; FR-024).
5. Determinism — two builds produce identical emphasis.yaml + cell ordering.
6. Unit tests for ``parse_stt_filename`` and ``aggregate_emphasis`` math.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from examen.generate.backend import (
    GenerationRequest,
    GenerationResponse,
    LLMBackend,
)
from paideia_shared.schemas import (
    CurriculumEntry,
    CurriculumMap,
    ExamenBlueprint,
    ExamItemDraft,
    SourceInventoryEntry,
)

# ---------------------------------------------------------------------------
# Constants (mirror US5 build)
# ---------------------------------------------------------------------------

_SEMESTER = "2026-1"
_COURSE = "anatomy"

_CHAPTERS = [
    "8장 호흡계통",
    "9장 근육계통",
    "10장 소화계통",
    "11장 순환계통",
    "12장 비뇨계통",
    "13장 신경계통",
]
_CHAPTER_NOS = [8, 9, 10, 11, 12, 13]
_WEEKS = [8, 9, 10, 11, 12, 13]

_N_FORMATIVE = 12
_N_QUIZ = 15
_N_TEXTBOOK = 40 - _N_FORMATIVE - _N_QUIZ  # 13


# ---------------------------------------------------------------------------
# FakeBackend (canned JSON, mirrors US5)
# ---------------------------------------------------------------------------

def _make_canned_json(answer_no: int = 1) -> dict[str, Any]:
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


_CANNED_FORMATIVE_JSON: dict[str, Any] = {
    "question_type": "지식축적",
    "difficulty": "2_보통",
    "stem_polarity": "부정형",
    "text": "다음 중 허파꽈리 세포에 대한 설명으로 가장 옳지 않은 것은?",
    "options": [
        "① 제1형허파세포는가스교환을담당한다.",
        "② 제2형허파세포는표면활성제를분비한다.",
        "③ 표면활성제는표면장력을낮추는기능있다.",
        "④ 허파꽈리벽은두종류세포로구성된다것.",
        "⑤ 제2형허파세포는섬모를보유하고있는세포.",
    ],
    "answer_no": 5,
    "distractor_rationale": [
        "옳은 진술.",
        "옳은 진술.",
        "옳은 진술.",
        "옳은 진술.",
        "틀린 진술: 섬모 없음.",
    ],
    "wrong_explanation": "오답 설명 텍스트." * 15,
    "leap_explanation": "도약 설명 텍스트." * 15,
    "intent": "허파꽈리 세포 기능.",
    "key_concept": None,
    "wrong_option_no": 5,
}

_CANNED_QUIZ_JSON: dict[str, Any] = {
    "question_type": "지식축적",
    "difficulty": "2_보통",
    "stem_polarity": "부정형",
    "text": "다음 중 호흡생리에 관한 설명으로 가장 옳지 않은 것은?",
    "options": [
        "① 변형된보기내용으로원본과다른표현을사용했다.",
        "② 변형된보기내용으로원본과다른표현을사용했다.",
        "③ 변형된보기내용으로원본과다른표현을사용했다.",
        "④ 변형된보기내용으로원본과다른표현을사용했다.",
        "⑤ 변형된보기내용으로원본과다른표현을사용했다.",
    ],
    "answer_no": 1,
    "distractor_rationale": [
        "틀린 진술: 변형 오개념.",
        "옳은 진술: 변형.",
        "옳은 진술: 변형.",
        "옳은 진술: 변형.",
        "옳은 진술: 변형.",
    ],
    "wrong_explanation": "변형 오답 설명." * 20,
    "leap_explanation": "변형 도약 설명." * 20,
    "intent": "변형된 문항 의도.",
    "key_concept": None,
}


class FakeBackend(LLMBackend):
    """Returns canned JSON by source (no network)."""

    def __init__(self) -> None:
        self.call_count = 0

    def generate(self, request: GenerationRequest) -> GenerationResponse:
        self.call_count += 1
        source = request.metadata.get("source", "textbook")
        if source == "formative":
            raw = json.dumps(_CANNED_FORMATIVE_JSON, ensure_ascii=False)
        elif source == "quiz":
            raw = json.dumps(_CANNED_QUIZ_JSON, ensure_ascii=False)
        else:
            raw = json.dumps(_make_canned_json(answer_no=1), ensure_ascii=False)
        return GenerationResponse(
            slot_id=request.slot_id,
            raw_text=raw,
            model="fake-us7",
            cache_hit=False,
        )


# ---------------------------------------------------------------------------
# Fixture builders
# ---------------------------------------------------------------------------

def _make_blueprint() -> ExamenBlueprint:
    return ExamenBlueprint(
        semester=_SEMESTER,
        course_slug=_COURSE,
        exam_name="2026-1학기 기말고사",
        total_items=40,
        chapters=_CHAPTERS,
        difficulty_targets={"easy": 0.45, "medium": 0.35, "hard": 0.20},
        source_mix={"textbook": _N_TEXTBOOK, "formative": _N_FORMATIVE, "quiz": _N_QUIZ},
        answer_key_balance=True,
    )


def _make_curriculum_map() -> CurriculumMap:
    entries = []
    for week, chapter, chapter_no in zip(_WEEKS, _CHAPTERS, _CHAPTER_NOS, strict=False):
        entries.append(
            CurriculumEntry(
                week=week,
                chapter=chapter,
                chapter_no=chapter_no,
                subtopic=None,
                sections=["1. 기본구조", "2. 기능"],
            )
        )
    return CurriculumMap(semester=_SEMESTER, course_slug=_COURSE, entries=entries)


def _make_quiz_inventory(n: int = 30) -> list[SourceInventoryEntry]:
    entries = []
    per_chapter = n // len(_CHAPTER_NOS)
    remainder = n % len(_CHAPTER_NOS)
    row = 0
    for i, (chapter_no, week) in enumerate(zip(_CHAPTER_NOS, _WEEKS, strict=False)):
        count = per_chapter + (1 if i < remainder else 0)
        for j in range(count):
            row += 1
            entries.append(
                SourceInventoryEntry(
                    semester=_SEMESTER,
                    course_slug=_COURSE,
                    source="quiz",
                    source_ref=f"퀴즈:{week}주#{row}",
                    chapter_no=chapter_no,
                    week=week,
                    stem=f"{chapter_no}장 {j + 1}번: 해당 계통에 관한 설명 중 옳지 않은 것은?",
                    options=[
                        f"① {chapter_no}장 보기A {j}번 텍스트",
                        f"② {chapter_no}장 보기B {j}번 텍스트",
                        f"③ {chapter_no}장 보기C {j}번 텍스트",
                        f"④ {chapter_no}장 보기D {j}번 텍스트",
                        f"⑤ {chapter_no}장 보기E {j}번 텍스트",
                    ],
                    answer=f"{(j % 5) + 1}",
                )
            )
    return entries


def _make_formative_inventory() -> list[SourceInventoryEntry]:
    entries = []
    for chapter_no, week in zip(_CHAPTER_NOS, _WEEKS, strict=False):
        for j in range(2):
            entries.append(
                SourceInventoryEntry(
                    semester=_SEMESTER,
                    course_slug=_COURSE,
                    source="formative",
                    source_ref=f"형성평가:{chapter_no}장#{j + 1}",
                    chapter_no=chapter_no,
                    week=week,
                    stem=f"{chapter_no}장 형성평가 {j + 1}번: 해당 계통 구조 설명.",
                    model_answer="모범답안: 해당 계통은 여러 기관으로 구성된다.",
                    keywords=["기관", "기능"],
                    rubric={"high": "모두", "mid": "한 가지", "low": "오개념"},
                )
            )
    return entries


def _setup_bronze(bronze_dir: Path) -> None:
    bronze_dir.mkdir(parents=True, exist_ok=True)
    for chapter_no, chapter in zip(_CHAPTER_NOS, _CHAPTERS, strict=False):
        name = chapter.split(" ", 1)[1]
        content = (
            f"{chapter}\n1. 기본구조\n{name}에 관한 주요 내용.\n"
            "기관들이 서로 연결되어 있다.\n2. 기능\n"
            f"{name}의 기능.\n"
        )
        (bronze_dir / f"{chapter}.txt").write_text(content, encoding="utf-8")


def _run_build(
    tmp_path: Path,
    *,
    stt_dir: Path | None = None,
) -> tuple[list[ExamItemDraft], Path]:
    from examen.pipeline import build_exam

    bronze_dir = tmp_path / "data" / "bronze" / "examen" / f"{_SEMESTER}-{_COURSE}"
    _setup_bronze(bronze_dir)
    items, run_dir = build_exam(
        blueprint=_make_blueprint(),
        curriculum_map=_make_curriculum_map(),
        bronze_dir=bronze_dir,
        data_root=tmp_path / "data",
        backend=FakeBackend(),
        formative_inventory=_make_formative_inventory(),
        quiz_inventory=_make_quiz_inventory(),
        stt_dir=stt_dir,
    )
    return items, run_dir


# ---------------------------------------------------------------------------
# STT dir fixture builders
# ---------------------------------------------------------------------------

def _write_stt(
    stt_dir: Path,
    class_id: str,
    week: int,
    session: int,
    text: str,
) -> None:
    wk = stt_dir / f"{week}주차"
    wk.mkdir(parents=True, exist_ok=True)
    (wk / f"{class_id}_{week}주차_{session}차시.txt").write_text(text, encoding="utf-8")


# ---------------------------------------------------------------------------
# Scenario 1 — degrade (no STT)
# ---------------------------------------------------------------------------

class TestDegradeNoStt:
    def test_build_completes_with_stt_none(self, tmp_path: Path) -> None:
        items, run_dir = _run_build(tmp_path, stt_dir=None)
        assert len(items) == 40
        assert run_dir.exists()

    def test_items_emphasis_is_none(self, tmp_path: Path) -> None:
        items, _ = _run_build(tmp_path, stt_dir=None)
        assert all(i.is_emphasized is None for i in items)
        assert all(i.emphasis_class_count is None for i in items)

    def test_ingest_report_stt_zeros(self, tmp_path: Path) -> None:
        _, run_dir = _run_build(tmp_path, stt_dir=None)
        report = json.loads((run_dir / "ingest_report.json").read_text(encoding="utf-8"))
        assert report["stt"]["expected"] == 0
        assert report["stt"]["found"] == 0
        assert report["stt"]["missing"] == []
        assert report["stt"]["filename_violations"] == []

    def test_nonexistent_dir_degrades(self, tmp_path: Path) -> None:
        items, run_dir = _run_build(tmp_path, stt_dir=tmp_path / "no" / "such" / "dir")
        assert len(items) == 40
        assert all(i.is_emphasized is None for i in items)
        report = json.loads((run_dir / "ingest_report.json").read_text(encoding="utf-8"))
        assert report["stt"]["expected"] == 0

    def test_no_emphasis_yaml_when_degraded(self, tmp_path: Path) -> None:
        _run_build(tmp_path, stt_dir=None)
        silver = tmp_path / "data" / "silver" / "examen" / f"{_SEMESTER}-{_COURSE}"
        assert not (silver / "emphasis.yaml").exists()


# ---------------------------------------------------------------------------
# Scenario 2 — intersection with a missing session
# ---------------------------------------------------------------------------

class TestIntersectionMissingSession:
    def _setup_stt(self, tmp_path: Path) -> Path:
        """4 classes for week 8; keyword '기본구조' appears in ALL classes.

        1C is missing its 2차시 (other classes have 2차시 that week) → flagged
        as missing and excluded from availability.
        """
        stt_dir = tmp_path / "stt"
        for cls in ("1A", "1B", "1C", "1D"):
            _write_stt(stt_dir, cls, 8, 1, "오늘은 기본구조 를 강조합니다. 폐포 구조.")
        for cls in ("1A", "1B", "1D"):
            _write_stt(stt_dir, cls, 8, 2, "기본구조 추가 설명. 기능도 다룸.")
        # 1C is missing week-8 2차시.
        return stt_dir

    def test_emphasized_section_is_intersection(self, tmp_path: Path) -> None:
        from examen.ingest.stt import scan_stt_dir
        from examen.silver.emphasis import aggregate_emphasis, build_keyword_dict

        stt_dir = self._setup_stt(tmp_path)
        cmap = _make_curriculum_map()
        scan = scan_stt_dir(stt_dir)
        kw = build_keyword_dict(cmap)
        cells = aggregate_emphasis(
            scan, cmap, kw, semester=_SEMESTER, course_slug=_COURSE
        )
        # The week-8 chapter (8장) section "1. 기본구조": all 4 classes have data
        # for week 8 (1C has 1차시), and '기본구조' appears in all → emphasized.
        week8 = [c for c in cells if c.chapter_no == 8 and "기본구조" in c.section]
        assert week8, f"no 8장 기본구조 cell. cells: {[(c.chapter_no, c.section) for c in cells]}"
        cell = week8[0]
        assert cell.available_class_count == 4
        assert cell.emphasized_class_count == 4
        assert cell.is_emphasized is True

    def test_missing_session_flagged_in_ingest_report(self, tmp_path: Path) -> None:
        stt_dir = self._setup_stt(tmp_path)
        bronze_dir = tmp_path / "data" / "bronze" / "examen" / f"{_SEMESTER}-{_COURSE}"
        _setup_bronze(bronze_dir)
        from examen.pipeline import build_exam

        _, run_dir = build_exam(
            blueprint=_make_blueprint(),
            curriculum_map=_make_curriculum_map(),
            bronze_dir=bronze_dir,
            data_root=tmp_path / "data",
            backend=FakeBackend(),
            formative_inventory=_make_formative_inventory(),
            quiz_inventory=_make_quiz_inventory(),
            stt_dir=stt_dir,
        )
        report = json.loads((run_dir / "ingest_report.json").read_text(encoding="utf-8"))
        missing = report["stt"]["missing"]
        # 1C week8 2차시 must be flagged.
        assert any("1C" in m and "8주차" in m and "2차시" in m for m in missing), (
            f"1C/8주차/2차시 not in missing: {missing}"
        )
        assert report["stt"]["found"] > 0

    def test_missing_class_excluded_not_counted_as_unemphasized(
        self, tmp_path: Path
    ) -> None:
        """1C has only 1차시 (no keyword absent there) — it still counts in week-8
        availability because it has week-8 data, and the keyword IS in its 1차시.
        """
        from examen.ingest.stt import scan_stt_dir
        from examen.silver.emphasis import aggregate_emphasis, build_keyword_dict

        stt_dir = self._setup_stt(tmp_path)
        cmap = _make_curriculum_map()
        scan = scan_stt_dir(stt_dir)
        kw = build_keyword_dict(cmap)
        cells = aggregate_emphasis(
            scan, cmap, kw, semester=_SEMESTER, course_slug=_COURSE
        )
        cell = next(c for c in cells if c.chapter_no == 8 and "기본구조" in c.section)
        # availability == emphasized → intersection holds despite 1C missing 2차시.
        assert cell.available_class_count == cell.emphasized_class_count


# ---------------------------------------------------------------------------
# Scenario 3 — partial emphasis
# ---------------------------------------------------------------------------

class TestPartialEmphasis:
    def test_partial_not_emphasized(self, tmp_path: Path) -> None:
        from examen.ingest.stt import scan_stt_dir
        from examen.silver.emphasis import aggregate_emphasis, build_keyword_dict

        stt_dir = tmp_path / "stt"
        # Keyword '기본구조' only in 1A, 1B (not 1C, 1D) — all 4 have week-8 data.
        _write_stt(stt_dir, "1A", 8, 1, "기본구조 강조함.")
        _write_stt(stt_dir, "1B", 8, 1, "기본구조 강조함.")
        _write_stt(stt_dir, "1C", 8, 1, "다른 내용만 다룸.")
        _write_stt(stt_dir, "1D", 8, 1, "또 다른 내용.")
        cmap = _make_curriculum_map()
        scan = scan_stt_dir(stt_dir)
        kw = build_keyword_dict(cmap)
        cells = aggregate_emphasis(
            scan, cmap, kw, semester=_SEMESTER, course_slug=_COURSE
        )
        cell = next(c for c in cells if c.chapter_no == 8 and "기본구조" in c.section)
        assert cell.available_class_count == 4
        assert cell.emphasized_class_count == 2
        assert cell.is_emphasized is False


# ---------------------------------------------------------------------------
# Scenario 4 — filename violation (FR-024)
# ---------------------------------------------------------------------------

class TestFilenameViolation:
    def test_malformed_filename_recorded(self, tmp_path: Path) -> None:
        stt_dir = tmp_path / "stt"
        _write_stt(stt_dir, "1A", 8, 1, "기본구조 강조.")
        # A malformed file that does NOT match the strict pattern.
        wk = stt_dir / "8주차"
        (wk / "엉뚱한파일이름.txt").write_text("noise", encoding="utf-8")

        bronze_dir = tmp_path / "data" / "bronze" / "examen" / f"{_SEMESTER}-{_COURSE}"
        _setup_bronze(bronze_dir)
        from examen.pipeline import build_exam

        _, run_dir = build_exam(
            blueprint=_make_blueprint(),
            curriculum_map=_make_curriculum_map(),
            bronze_dir=bronze_dir,
            data_root=tmp_path / "data",
            backend=FakeBackend(),
            formative_inventory=_make_formative_inventory(),
            quiz_inventory=_make_quiz_inventory(),
            stt_dir=stt_dir,
        )
        report = json.loads((run_dir / "ingest_report.json").read_text(encoding="utf-8"))
        violations = report["stt"]["filename_violations"]
        assert any("엉뚱한파일이름" in v for v in violations), (
            f"malformed file not flagged: {violations}"
        )


# ---------------------------------------------------------------------------
# Scenario 5 — determinism
# ---------------------------------------------------------------------------

class TestDeterminism:
    def _setup_stt(self, tmp_path: Path) -> Path:
        stt_dir = tmp_path / "stt"
        for cls in ("1A", "1B", "1C", "1D"):
            _write_stt(stt_dir, cls, 8, 1, "기본구조 강조. 기능도 다룸.")
        return stt_dir

    def test_emphasis_yaml_identical_across_runs(self, tmp_path: Path) -> None:
        stt_dir = self._setup_stt(tmp_path)
        from examen.pipeline import build_exam

        def _build(root: Path) -> Path:
            bronze_dir = root / "data" / "bronze" / "examen" / f"{_SEMESTER}-{_COURSE}"
            _setup_bronze(bronze_dir)
            _, run_dir = build_exam(
                blueprint=_make_blueprint(),
                curriculum_map=_make_curriculum_map(),
                bronze_dir=bronze_dir,
                data_root=root / "data",
                backend=FakeBackend(),
                formative_inventory=_make_formative_inventory(),
                quiz_inventory=_make_quiz_inventory(),
                stt_dir=stt_dir,
            )
            silver = root / "data" / "silver" / "examen" / f"{_SEMESTER}-{_COURSE}"
            return silver / "emphasis.yaml"

        r1 = tmp_path / "r1"
        r2 = tmp_path / "r2"
        y1 = _build(r1)
        y2 = _build(r2)
        assert y1.exists() and y2.exists()
        assert y1.read_text(encoding="utf-8") == y2.read_text(encoding="utf-8")

    def test_cell_order_deterministic(self, tmp_path: Path) -> None:
        from examen.ingest.stt import scan_stt_dir
        from examen.silver.emphasis import aggregate_emphasis, build_keyword_dict

        stt_dir = self._setup_stt(tmp_path)
        cmap = _make_curriculum_map()
        scan = scan_stt_dir(stt_dir)
        kw = build_keyword_dict(cmap)
        c1 = aggregate_emphasis(scan, cmap, kw, semester=_SEMESTER, course_slug=_COURSE)
        c2 = aggregate_emphasis(scan, cmap, kw, semester=_SEMESTER, course_slug=_COURSE)
        keys1 = [(c.chapter_no, c.section) for c in c1]
        keys2 = [(c.chapter_no, c.section) for c in c2]
        assert keys1 == keys2
        assert keys1 == sorted(keys1)


# ---------------------------------------------------------------------------
# Scenario 6 — unit tests
# ---------------------------------------------------------------------------

class TestParseSttFilename:
    def test_valid(self) -> None:
        from examen.ingest.stt import parse_stt_filename

        assert parse_stt_filename("1A_8주차_1차시.txt") == ("1A", 8, 1)
        assert parse_stt_filename("1C_11주차_2차시.txt") == ("1C", 11, 2)
        assert parse_stt_filename("1D_13주차_2차시") == ("1D", 13, 2)

    def test_invalid_returns_none(self) -> None:
        from examen.ingest.stt import parse_stt_filename

        assert parse_stt_filename("엉뚱한파일이름.txt") is None
        assert parse_stt_filename("1A-8주차-1차시.txt") is None
        assert parse_stt_filename("1A_8주_1차시.txt") is None
        assert parse_stt_filename("XX_8주차_1차시.txt") is None
        assert parse_stt_filename("") is None


class TestAggregateEmphasisMath:
    def test_intersection_true(self, tmp_path: Path) -> None:
        from examen.ingest.stt import scan_stt_dir
        from examen.silver.emphasis import aggregate_emphasis, build_keyword_dict

        stt_dir = tmp_path / "stt"
        for cls in ("1A", "1B"):
            _write_stt(stt_dir, cls, 8, 1, "기본구조 강조.")
        cmap = CurriculumMap(
            semester=_SEMESTER,
            course_slug=_COURSE,
            entries=[
                CurriculumEntry(
                    week=8, chapter="8장 호흡계통", chapter_no=8,
                    sections=["1. 기본구조", "2. 기능"],
                )
            ],
        )
        scan = scan_stt_dir(stt_dir)
        kw = build_keyword_dict(cmap)
        cells = aggregate_emphasis(scan, cmap, kw, semester=_SEMESTER, course_slug=_COURSE)
        struct = next(c for c in cells if "기본구조" in c.section)
        assert struct.available_class_count == 2
        assert struct.emphasized_class_count == 2
        assert struct.is_emphasized is True
        # "2. 기능" not mentioned → not emphasized.
        func = next(c for c in cells if "기능" in c.section)
        assert func.emphasized_class_count == 0
        assert func.is_emphasized is False

    def test_empty_scan_returns_empty(self, tmp_path: Path) -> None:
        from examen.ingest.stt import scan_stt_dir
        from examen.silver.emphasis import aggregate_emphasis, build_keyword_dict

        scan = scan_stt_dir(tmp_path / "nonexistent")
        cmap = _make_curriculum_map()
        kw = build_keyword_dict(cmap)
        assert aggregate_emphasis(
            scan, cmap, kw, semester=_SEMESTER, course_slug=_COURSE
        ) == []

    def test_evidence_refs_sorted(self, tmp_path: Path) -> None:
        from examen.ingest.stt import scan_stt_dir
        from examen.silver.emphasis import aggregate_emphasis, build_keyword_dict

        stt_dir = tmp_path / "stt"
        for cls in ("1B", "1A"):  # deliberately reversed write order
            _write_stt(stt_dir, cls, 8, 1, "기본구조 강조.")
        cmap = CurriculumMap(
            semester=_SEMESTER,
            course_slug=_COURSE,
            entries=[
                CurriculumEntry(
                    week=8, chapter="8장 호흡계통", chapter_no=8,
                    sections=["1. 기본구조"],
                )
            ],
        )
        scan = scan_stt_dir(stt_dir)
        kw = build_keyword_dict(cmap)
        cells = aggregate_emphasis(scan, cmap, kw, semester=_SEMESTER, course_slug=_COURSE)
        cell = cells[0]
        assert cell.evidence_refs == sorted(cell.evidence_refs)


# ---------------------------------------------------------------------------
# N3 — direct unit tests for label_items_with_emphasis
# ---------------------------------------------------------------------------

def _make_item(
    *,
    chapter_no: int = 8,
    section: str | None = None,
    key_concept: str | None = None,
) -> ExamItemDraft:
    """Construct a minimal valid ExamItemDraft for labeling tests."""
    return ExamItemDraft(
        semester=_SEMESTER,
        course_slug=_COURSE,
        item_no=1,
        source="textbook",
        chapter=f"{chapter_no}장 테스트계통",
        chapter_no=chapter_no,
        section=section,
        key_concept=key_concept,
        question_type="지식축적",
        difficulty="2_보통",
        stem_polarity="부정형",
        text="다음 중 가장 옳지 않은 것은?",
        options=[
            "① " + "가" * 28,
            "② " + "나" * 28,
            "③ " + "다" * 28,
            "④ " + "라" * 28,
            "⑤ " + "마" * 28,
        ],
        answer_no=1,
        distractor_rationale=["옳은 진술." for _ in range(5)],
        wrong_explanation="오답 설명." * 10,
        leap_explanation="도약 설명." * 10,
        intent="출제의도 텍스트 테스트.",
        option_length_ok=True,
    )


def _make_cell(
    *,
    chapter_no: int,
    section: str,
    emphasized: int,
    available: int,
) -> Any:
    from paideia_shared.schemas import EmphasisCell

    return EmphasisCell(
        semester=_SEMESTER,
        course_slug=_COURSE,
        chapter_no=chapter_no,
        section=section,
        emphasized_class_count=emphasized,
        available_class_count=available,
        is_emphasized=(emphasized == available and available > 0),
    )


class TestLabelItemsWithEmphasis:
    def test_section_level_hit(self) -> None:
        from examen.silver.emphasis import build_keyword_dict, label_items_with_emphasis

        item = _make_item(chapter_no=8, section="1. 기본구조")
        cell = _make_cell(chapter_no=8, section="1. 기본구조", emphasized=4, available=4)
        kw = build_keyword_dict(_make_curriculum_map())
        out = label_items_with_emphasis([item], [cell], kw)
        assert out[0].is_emphasized is True
        assert out[0].emphasis_class_count == 4

    def test_key_concept_reverse_map_hit(self) -> None:
        from examen.silver.emphasis import build_keyword_dict, label_items_with_emphasis

        # section=None; key_concept '기본구조' maps to "1. 기본구조" in chapter 8.
        item = _make_item(chapter_no=8, section=None, key_concept="기본구조")
        cell = _make_cell(chapter_no=8, section="1. 기본구조", emphasized=3, available=4)
        kw = build_keyword_dict(_make_curriculum_map())
        out = label_items_with_emphasis([item], [cell], kw)
        assert out[0].is_emphasized is False
        assert out[0].emphasis_class_count == 3

    def test_chapter_level_fallback(self) -> None:
        from examen.silver.emphasis import build_keyword_dict, label_items_with_emphasis

        # No section, no key_concept match → chapter-level fallback.
        item = _make_item(chapter_no=8, section=None, key_concept="존재하지않는개념")
        cells = [
            _make_cell(chapter_no=8, section="1. 기본구조", emphasized=4, available=4),
            _make_cell(chapter_no=8, section="2. 기능", emphasized=2, available=4),
        ]
        kw = build_keyword_dict(_make_curriculum_map())
        out = label_items_with_emphasis([item], cells, kw)
        # any emphasized → True; max emphasized_class_count over chapter == 4.
        assert out[0].is_emphasized is True
        assert out[0].emphasis_class_count == 4

    def test_chapter_with_no_cells_untouched(self) -> None:
        from examen.silver.emphasis import build_keyword_dict, label_items_with_emphasis

        # Item is in chapter 9, but cells only cover chapter 8 → untouched (None).
        item = _make_item(chapter_no=9, section=None, key_concept=None)
        cell = _make_cell(chapter_no=8, section="1. 기본구조", emphasized=4, available=4)
        kw = build_keyword_dict(_make_curriculum_map())
        out = label_items_with_emphasis([item], [cell], kw)
        assert out[0].is_emphasized is None
        assert out[0].emphasis_class_count is None

    def test_empty_cells_unchanged(self) -> None:
        from examen.silver.emphasis import build_keyword_dict, label_items_with_emphasis

        item = _make_item(chapter_no=8, section="1. 기본구조")
        kw = build_keyword_dict(_make_curriculum_map())
        out = label_items_with_emphasis([item], [], kw)
        assert out[0].is_emphasized is None
        assert out[0].emphasis_class_count is None
