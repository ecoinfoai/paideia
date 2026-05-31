"""T033 — Unit tests: load_formative_inventory parser + safe txt↔yaml matching.

Covers:
- Happy path: administered txt items matched to YAML questions by sn.
- Strategy-1 (sn==ordinal) cross-checks stem compatibility; falls through to
  stem matching when the professor administered out of order.
- Strategy-2 (stem fallback) raises a located error on ambiguous (>1) matches.
- Fail-fast on unmatched administered item (no silent drop).
- chapter_no resolution via curriculum_map (week→chapter).
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml as _yaml
from paideia_shared.schemas import CurriculumEntry, CurriculumMap

_SEMESTER = "2026-1"
_COURSE = "anatomy"


def _curriculum() -> CurriculumMap:
    return CurriculumMap(
        semester=_SEMESTER,
        course_slug=_COURSE,
        entries=[
            CurriculumEntry(week=8, chapter="8장 호흡계통", chapter_no=8,
                            subtopic=None, sections=["1. 기도"]),
            CurriculumEntry(week=9, chapter="9장 근육계통", chapter_no=9,
                            subtopic=None, sections=["1. 골격근"]),
        ],
    )


def _write_yaml(path: Path, chapter: int, questions: list[dict]) -> None:
    data = {
        "metadata": {"chapter": chapter, "chapter_name": "테스트", "week_num": chapter,
                     "total_questions": len(questions)},
        "questions": questions,
    }
    path.write_text(_yaml.dump(data, allow_unicode=True), encoding="utf-8")


def _q(sn: int, question: str, *, model_answer: str = "모범답안입니다.",
       keywords: list[str] | None = None) -> dict:
    return {
        "sn": sn,
        "topic": "개념이해",
        "question": question,
        "model_answer": model_answer,
        "keywords": keywords or ["키워드1", "키워드2"],
        "rubric": {"high": "상", "mid": "중", "low": "하 오개념"},
    }


class TestLoadFormativeInventoryHappyPath:
    def test_matches_by_sn(self, tmp_path: Path) -> None:
        from examen.ingest.source_inventory import load_formative_inventory

        txt = tmp_path / "actual.txt"
        txt.write_text(
            "8주차 1. 허파꽈리를 구성하는 세포의 종류와 기능을 설명하시오.\n"
            "8주차 2. 표면활성제의 기능을 설명하시오.\n",
            encoding="utf-8",
        )
        ch8 = tmp_path / "Ch8_FormativeTest.yaml"
        _write_yaml(ch8, 8, [
            _q(1, "허파꽈리를 구성하는 세포의 종류와 기능을 설명하시오.",
               model_answer="허파꽈리는 두 종류 세포로 구성된다."),
            _q(2, "표면활성제의 기능을 설명하시오.",
               model_answer="표면활성제는 표면장력을 낮춘다."),
        ])

        inv = load_formative_inventory(
            actual_txt=txt, chapter_yamls=[ch8],
            curriculum_map=_curriculum(), semester=_SEMESTER, course_slug=_COURSE,
        )
        assert len(inv) == 2
        assert inv[0].source_ref == "형성평가:8장#1"
        assert inv[0].chapter_no == 8
        assert inv[0].week == 8
        assert "두 종류 세포" in (inv[0].model_answer or "")
        assert inv[1].source_ref == "형성평가:8장#2"


class TestStrategy1StemCrossCheck:
    def test_sn_match_but_wrong_stem_falls_through(self, tmp_path: Path) -> None:
        """sn==ordinal but stems differ → fall through to stem matching.

        Professor administered question with ordinal 1, but YAML sn=1 is a
        DIFFERENT question; the actually-matching question is YAML sn=2.
        The loader must bind to sn=2 (by stem), not silently to sn=1.
        """
        from examen.ingest.source_inventory import load_formative_inventory

        txt = tmp_path / "actual.txt"
        # administered "1." is actually the 표면활성제 question (YAML sn=2)
        txt.write_text(
            "8주차 1. 표면활성제의 기능을 자세히 설명하시오.\n",
            encoding="utf-8",
        )
        ch8 = tmp_path / "Ch8_FormativeTest.yaml"
        _write_yaml(ch8, 8, [
            _q(1, "허파꽈리를 구성하는 세포의 종류와 기능을 설명하시오.",
               model_answer="세포 모범답안."),
            _q(2, "표면활성제의 기능을 자세히 설명하시오.",
               model_answer="표면활성제 모범답안."),
        ])

        inv = load_formative_inventory(
            actual_txt=txt, chapter_yamls=[ch8],
            curriculum_map=_curriculum(), semester=_SEMESTER, course_slug=_COURSE,
        )
        assert len(inv) == 1
        # Must bind to sn=2 by stem, NOT sn=1 by ordinal
        assert inv[0].source_ref == "형성평가:8장#2", (
            f"expected bind to sn=2 by stem, got {inv[0].source_ref}"
        )
        assert "표면활성제 모범답안" in (inv[0].model_answer or "")


class TestStrategy2Ambiguity:
    def test_ambiguous_stem_raises(self, tmp_path: Path) -> None:
        """>1 YAML question matching the same administered stem → located error."""
        from examen.ingest.source_inventory import load_formative_inventory

        txt = tmp_path / "actual.txt"
        # ordinal 5 has no sn=5; falls to stem matching, which matches TWO
        txt.write_text(
            "8주차 5. 근육의 수축 기전을 설명하시오.\n",
            encoding="utf-8",
        )
        ch8 = tmp_path / "Ch8_FormativeTest.yaml"
        _write_yaml(ch8, 8, [
            _q(1, "근육의 수축 기전을 설명하시오. 추가 설명 A."),
            _q(2, "근육의 수축 기전을 설명하시오. 추가 설명 B."),
        ])

        with pytest.raises(ValueError, match="모호"):
            load_formative_inventory(
                actual_txt=txt, chapter_yamls=[ch8],
                curriculum_map=_curriculum(), semester=_SEMESTER, course_slug=_COURSE,
            )


class TestFailFast:
    def test_unmatched_administered_item_raises(self, tmp_path: Path) -> None:
        """An administered item with no YAML match raises (no silent drop)."""
        from examen.ingest.source_inventory import load_formative_inventory

        txt = tmp_path / "actual.txt"
        txt.write_text("8주차 1. 존재하지 않는 질문입니다.\n", encoding="utf-8")
        ch8 = tmp_path / "Ch8_FormativeTest.yaml"
        _write_yaml(ch8, 8, [_q(2, "전혀 다른 질문.")])

        with pytest.raises(ValueError, match="찾을 수 없"):
            load_formative_inventory(
                actual_txt=txt, chapter_yamls=[ch8],
                curriculum_map=_curriculum(), semester=_SEMESTER, course_slug=_COURSE,
            )

    def test_missing_week_in_curriculum_raises(self, tmp_path: Path) -> None:
        """An administered week absent from curriculum_map raises."""
        from examen.ingest.source_inventory import load_formative_inventory

        txt = tmp_path / "actual.txt"
        txt.write_text("13주차 1. 어떤 질문.\n", encoding="utf-8")  # week 13 not in map
        ch8 = tmp_path / "Ch8_FormativeTest.yaml"
        _write_yaml(ch8, 8, [_q(1, "어떤 질문.")])

        with pytest.raises(ValueError, match="13주차"):
            load_formative_inventory(
                actual_txt=txt, chapter_yamls=[ch8],
                curriculum_map=_curriculum(), semester=_SEMESTER, course_slug=_COURSE,
            )

    def test_malformed_txt_line_raises(self, tmp_path: Path) -> None:
        """A txt line not matching '{week}주차 {n}. {stem}' raises."""
        from examen.ingest.source_inventory import load_formative_inventory

        txt = tmp_path / "actual.txt"
        txt.write_text("이건 형식에 맞지 않는 줄입니다\n", encoding="utf-8")
        ch8 = tmp_path / "Ch8_FormativeTest.yaml"
        _write_yaml(ch8, 8, [_q(1, "질문.")])

        with pytest.raises(ValueError, match="format"):
            load_formative_inventory(
                actual_txt=txt, chapter_yamls=[ch8],
                curriculum_map=_curriculum(), semester=_SEMESTER, course_slug=_COURSE,
            )
