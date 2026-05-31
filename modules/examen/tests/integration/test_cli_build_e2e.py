"""T062 — CLI-level end-to-end build (quickstart §1-2 Bronze → Gold).

Closes the CLI wiring gap: ``examen build`` must load the formative and quiz
source inventories from the Bronze convention and pass them to ``build_exam``
so a blueprint whose ``source_mix`` declares ``formative > 0`` / ``quiz > 0``
runs end-to-end (previously it raised because the CLI passed neither).

Approach (backend + quiz-loader seams; no network, no xlwt)
-----------------------------------------------------------
- ``_run_build(args, backend=...)`` grew an explicit ``backend`` seam: tests
  inject a network-free ``FakeBuildBackend`` instead of the real
  Subscription/Api backends.  This is the only handler change needed to make a
  true CLI e2e possible.
- The **formative** source is laid down as REAL Bronze files
  (``형성평가_실제_출제문제들.txt`` + ``Ch*_FormativeTest.yaml``) so the actual
  ``load_formative_inventory`` parses them — proving that path end-to-end.
- The **quiz** source's reader (``load_quiz_inventory``) opens BIFF8 ``.xls``
  via ``xlrd``; ``xlwt`` is unavailable in this environment, so writing a real
  ``.xls`` fixture is impractical.  We instead drop a placeholder ``quiz/*.xls``
  (so the CLI's Bronze-convention existence guard passes) and monkeypatch
  ``examen.ingest.source_inventory.load_quiz_inventory`` to return synthetic
  entries (mirroring the US3/US5 in-memory quiz inventory).  This still proves
  the CLI (a) resolves the quiz dir from the Bronze convention, (b) invokes the
  loader, and (c) routes its result into ``build_exam`` (asserted via quiz
  items in the Gold output).
- Also asserts the fail-fast contract: quiz declared (>0) but no quiz Bronze
  data → exit 2 (no silent skip).

Asserted Gold artefacts (quickstart §3): 기말출제초안.xlsx/.yaml,
출제품질리포트.md, manifest_examen.json, ingest_report.json — item count ==
total_items, with formative + quiz + textbook all represented.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import yaml
from examen.generate.backend import (
    GenerationRequest,
    GenerationResponse,
    LLMBackend,
)
from paideia_shared.schemas import SourceInventoryEntry

# ---------------------------------------------------------------------------
# Constants — 40-item mixed blueprint (textbook + formative + quiz)
# ---------------------------------------------------------------------------

_SEMESTER = "2026-1"
_COURSE = "anatomy"

_N_FORMATIVE = 12
_N_QUIZ = 15
_N_TEXTBOOK = 40 - _N_FORMATIVE - _N_QUIZ  # 13
_TOTAL = 40

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


# ---------------------------------------------------------------------------
# Canned LLM responses (mirror US5 FakeBackend dispatch by metadata.source)
# ---------------------------------------------------------------------------


def _canned_textbook() -> dict[str, Any]:
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
        "answer_no": 1,
        "distractor_rationale": [
            "틀린 진술: 가.",
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


_CANNED_FORMATIVE: dict[str, Any] = {
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

_CANNED_QUIZ: dict[str, Any] = {
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


class FakeBuildBackend(LLMBackend):
    """Network-free backend dispatching canned JSON by ``metadata.source``."""

    def __init__(self) -> None:
        self.call_count = 0

    def generate(self, request: GenerationRequest) -> GenerationResponse:
        self.call_count += 1
        source = request.metadata.get("source", "textbook")
        if source == "formative":
            payload = _CANNED_FORMATIVE
        elif source == "quiz":
            payload = _CANNED_QUIZ
        else:
            payload = _canned_textbook()
        return GenerationResponse(
            slot_id=request.slot_id,
            raw_text=json.dumps(payload, ensure_ascii=False),
            model="fake-build-e2e",
            cache_hit=False,
        )


# ---------------------------------------------------------------------------
# Bronze fixture builders
# ---------------------------------------------------------------------------


def _write_chapter_txt(bronze: Path, chapter_no: int, chapter_name: str) -> None:
    fname = f"{chapter_no}장 {chapter_name}.txt"
    content = (
        f"{chapter_no}장 {chapter_name}\n"
        "1. 기본구조\n"
        f"{chapter_name}에 관한 주요 내용.\n"
        "기관들이 서로 연결되어 있다.\n"
        "2. 기능\n"
        f"{chapter_name}의 기능.\n"
    )
    (bronze / fname).write_text(content, encoding="utf-8")


def _write_blueprint(bronze: Path) -> None:
    bp = {
        "semester": _SEMESTER,
        "course_slug": _COURSE,
        "exam_name": "2026-1학기 기말고사",
        "total_items": _TOTAL,
        "chapters": _CHAPTERS,
        "difficulty_targets": {"easy": 0.45, "medium": 0.35, "hard": 0.20},
        "source_mix": {
            "textbook": _N_TEXTBOOK,
            "formative": _N_FORMATIVE,
            "quiz": _N_QUIZ,
        },
        "answer_key_balance": True,
    }
    (bronze / "blueprint.yaml").write_text(
        yaml.safe_dump(bp, allow_unicode=True, sort_keys=False), encoding="utf-8"
    )


def _write_curriculum_map(bronze: Path) -> None:
    cm = {
        "semester": _SEMESTER,
        "course_slug": _COURSE,
        "entries": [
            {
                "week": week,
                "chapter": chapter,
                "chapter_no": chapter_no,
                "subtopic": None,
                "sections": ["1. 기본구조", "2. 기능"],
            }
            for week, chapter, chapter_no in zip(
                _WEEKS, _CHAPTERS, _CHAPTER_NOS, strict=True
            )
        ],
    }
    (bronze / "curriculum_map.yaml").write_text(
        yaml.safe_dump(cm, allow_unicode=True, sort_keys=False), encoding="utf-8"
    )


def _write_formative_bronze(bronze: Path) -> None:
    """Real formative source: actual_txt + per-chapter Ch*_FormativeTest.yaml.

    2 administered items per chapter (×6 chapters) = 12 formative items, exactly
    ``source_mix.formative``.  These are parsed by the REAL
    ``load_formative_inventory`` (yaml + txt — no native deps).
    """
    formative_dir = bronze / "formative"
    formative_dir.mkdir(parents=True, exist_ok=True)

    actual_lines: list[str] = []
    for chapter_no, week in zip(_CHAPTER_NOS, _WEEKS, strict=True):
        questions = []
        for sn in (1, 2):
            stem = f"{chapter_no}장 형성평가 {sn}번 해당 계통 구조를 설명하시오."
            actual_lines.append(f"{week}주차 {sn}. {stem}")
            questions.append(
                {
                    "sn": sn,
                    "question": stem,
                    "model_answer": "모범답안: 해당 계통은 여러 기관으로 구성된다.",
                    "keywords": ["기관", "기능"],
                    "rubric": {
                        "high": "모두 정확히 설명",
                        "mid": "한 가지만 설명",
                        "low": "완전히 틀린 오개념",
                    },
                }
            )
        ch_yaml = {
            "metadata": {"chapter": chapter_no},
            "questions": questions,
        }
        (formative_dir / f"Ch{chapter_no}_FormativeTest.yaml").write_text(
            yaml.safe_dump(ch_yaml, allow_unicode=True, sort_keys=False),
            encoding="utf-8",
        )

    (formative_dir / "형성평가_실제_출제문제들.txt").write_text(
        "\n".join(actual_lines) + "\n", encoding="utf-8"
    )


def _synthetic_quiz_inventory(n: int = 30) -> list[SourceInventoryEntry]:
    """In-memory quiz inventory (mirrors US3/US5 _make_quiz_inventory)."""
    entries: list[SourceInventoryEntry] = []
    per_chapter = n // len(_CHAPTER_NOS)
    remainder = n % len(_CHAPTER_NOS)
    row = 0
    for i, (chapter_no, week) in enumerate(zip(_CHAPTER_NOS, _WEEKS, strict=True)):
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


def _setup_full_bronze(bronze: Path, *, with_quiz_xls: bool = True) -> None:
    """Lay down a complete Bronze dir per quickstart §1."""
    bronze.mkdir(parents=True, exist_ok=True)
    for chapter_no, chapter in zip(_CHAPTER_NOS, _CHAPTERS, strict=True):
        _write_chapter_txt(bronze, chapter_no, chapter.split(" ", 1)[1])
    _write_blueprint(bronze)
    _write_curriculum_map(bronze)
    _write_formative_bronze(bronze)
    if with_quiz_xls:
        quiz_dir = bronze / "quiz"
        quiz_dir.mkdir(parents=True, exist_ok=True)
        # Placeholder .xls so the CLI's Bronze-convention existence guard passes;
        # the real reader is monkeypatched (xlwt unavailable to write BIFF8).
        (quiz_dir / "QuestionUploadExcel_8주차.xls").write_bytes(b"\xd0\xcf\x11\xe0")


def _make_args(bronze: Path) -> Any:
    """Build the argparse Namespace _run_build expects (bronze paths resolved)."""
    import argparse

    return argparse.Namespace(
        semester=_SEMESTER,
        course=_COURSE,
        blueprint=bronze / "blueprint.yaml",
        curriculum_map=bronze / "curriculum_map.yaml",
        backend="subscription",
        no_emphasis=True,  # degrade STT; keep the e2e free of stt fixtures
        stt=None,
    )


def _patch_quiz_loader(monkeypatch: Any) -> None:
    """Patch load_quiz_inventory to return synthetic entries (no xlrd/.xls read)."""
    import examen.ingest.source_inventory as si

    def _fake_loader(
        xls_paths: list[Path],
        curriculum_map: Any,
        semester: str,
        course_slug: str,
    ) -> list[SourceInventoryEntry]:
        assert xls_paths, "CLI must pass the resolved quiz .xls paths"
        return _synthetic_quiz_inventory(30)

    monkeypatch.setattr(si, "load_quiz_inventory", _fake_loader)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestCLIBuildE2E:
    def _run(self, tmp_path: Path, monkeypatch: Any) -> tuple[int, Path]:
        """Run `_run_build` against a full Bronze fixture; return (rc, gold_base)."""
        from examen.cli.main import _run_build

        bronze = tmp_path / "data" / "bronze" / "examen" / f"{_SEMESTER}-{_COURSE}"
        _setup_full_bronze(bronze)
        _patch_quiz_loader(monkeypatch)

        # build_exam writes Gold under data_root=Path("data"); run from tmp so it
        # lands inside tmp_path/data/gold/... and never touches the repo.
        monkeypatch.chdir(tmp_path)

        rc = _run_build(_make_args(bronze), backend=FakeBuildBackend())
        gold_base = tmp_path / "data" / "gold" / "examen" / f"{_SEMESTER}-{_COURSE}"
        return rc, gold_base

    def _latest_run_dir(self, gold_base: Path) -> Path:
        runs = sorted((gold_base / "runs").iterdir())
        assert runs, f"no run dir produced under {gold_base}/runs"
        return runs[-1]

    def test_build_succeeds_end_to_end(self, tmp_path: Path, monkeypatch: Any) -> None:
        """`examen build` runs to completion (exit 0) with formative+quiz declared."""
        rc, _ = self._run(tmp_path, monkeypatch)
        assert rc == 0, f"expected exit 0, got {rc}"

    def test_gold_artefacts_written(self, tmp_path: Path, monkeypatch: Any) -> None:
        """All quickstart §3 Gold artefacts are produced."""
        _, gold_base = self._run(tmp_path, monkeypatch)
        run_dir = self._latest_run_dir(gold_base)
        for name in (
            "기말출제초안.xlsx",
            "기말출제초안.yaml",
            "출제품질리포트.md",
            "manifest_examen.json",
            "ingest_report.json",
        ):
            assert (run_dir / name).exists(), f"missing Gold artefact: {name}"

    def test_item_count_matches_total(self, tmp_path: Path, monkeypatch: Any) -> None:
        """Item count == blueprint.total_items."""
        _, gold_base = self._run(tmp_path, monkeypatch)
        run_dir = self._latest_run_dir(gold_base)
        manifest = json.loads(
            (run_dir / "manifest_examen.json").read_text(encoding="utf-8")
        )
        assert manifest["item_count"] == _TOTAL

    def test_all_three_sources_represented(
        self, tmp_path: Path, monkeypatch: Any
    ) -> None:
        """formative + quiz + textbook all reach the Gold output."""
        _, gold_base = self._run(tmp_path, monkeypatch)
        run_dir = self._latest_run_dir(gold_base)
        manifest = json.loads(
            (run_dir / "manifest_examen.json").read_text(encoding="utf-8")
        )
        breakdown = manifest["source_breakdown"]
        assert breakdown.get("textbook", 0) == _N_TEXTBOOK
        assert breakdown.get("formative", 0) == _N_FORMATIVE
        assert breakdown.get("quiz", 0) == _N_QUIZ

    def test_ingest_report_records_inventories(
        self, tmp_path: Path, monkeypatch: Any
    ) -> None:
        """ingest_report.json reflects loaded formative & quiz inventories."""
        _, gold_base = self._run(tmp_path, monkeypatch)
        run_dir = self._latest_run_dir(gold_base)
        report = json.loads(
            (run_dir / "ingest_report.json").read_text(encoding="utf-8")
        )
        assert report["formative"]["found"] == _N_FORMATIVE
        assert report["quiz"]["rows"] == 30  # synthetic pool size


class TestCLIBuildFailFast:
    """Declared-but-absent sources fail fast (exit 2) — no silent skip."""

    def test_quiz_declared_but_missing_returns_exit2(
        self, tmp_path: Path, monkeypatch: Any
    ) -> None:
        """source_mix.quiz>0 but no quiz/*.xls Bronze data → exit 2."""
        from examen.cli.main import _run_build

        bronze = tmp_path / "data" / "bronze" / "examen" / f"{_SEMESTER}-{_COURSE}"
        _setup_full_bronze(bronze, with_quiz_xls=False)  # no quiz dir
        monkeypatch.chdir(tmp_path)

        rc = _run_build(_make_args(bronze), backend=FakeBuildBackend())
        assert rc == 2

    def test_formative_declared_but_missing_returns_exit2(
        self, tmp_path: Path, monkeypatch: Any
    ) -> None:
        """source_mix.formative>0 but no formative/ Bronze data → exit 2."""
        from examen.cli.main import _run_build

        bronze = tmp_path / "data" / "bronze" / "examen" / f"{_SEMESTER}-{_COURSE}"
        _setup_full_bronze(bronze)
        # Remove the formative source after setup
        import shutil

        shutil.rmtree(bronze / "formative")
        _patch_quiz_loader(monkeypatch)
        monkeypatch.chdir(tmp_path)

        rc = _run_build(_make_args(bronze), backend=FakeBuildBackend())
        assert rc == 2
