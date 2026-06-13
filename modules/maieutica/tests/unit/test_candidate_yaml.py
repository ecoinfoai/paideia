"""T040 / T048 — unit tests for ``maieutica.output.candidate_yaml``.

``write_candidate_yaml(quiz_items, formative_items, path)`` writes
``출제후보_완전판.yaml`` — the nested full-fidelity output with top-level keys
``"quiz"`` and ``"formative"``, preserving the FULL (untruncated) ``leap.text``,
per-option ``option_evidence``, and ``textbook_evidence`` (item- and leap-level).
The ``─ 도약 ─`` separator must allow a mechanical round-trip split of
``answer_explanation_combined`` back into wrong + leap.
"""

from __future__ import annotations

from pathlib import Path

import yaml
from paideia_shared.schemas import (
    FormativeItemCandidate,
    MaieuticaTextbookEvidence,
    QuizItemCandidate,
)
from paideia_shared.schemas.maieutica.leap_explanation import LeapExplanation

_SEP = " ─ 도약 ─ "


def _quiz_candidate(item_no: int, wrong: str, leap_text: str) -> QuizItemCandidate:
    options = [f"보기 {item_no}-{i} 길이 충분한 보기 문자열 padding" for i in range(1, 6)]
    return QuizItemCandidate(
        semester="2026-1",
        course_slug="anatomy",
        item_no=item_no,
        week=9,
        chapter_no=8,
        chapter="호흡계통",
        question_type="지식축적",
        difficulty="중",
        stem_polarity="부정형",
        text=f"{item_no}번 문제",
        options=options,
        answer_no=3,
        option_evidence=[f"근거{item_no}-{i}" for i in range(1, 6)],
        wrong_explanation=wrong,
        leap=LeapExplanation(text=leap_text),
        answer_explanation_combined=f"{wrong}{_SEP}{leap_text}",
        option_length_ok=True,
        explanation_length_ok=True,
    )


def _formative_candidate(no: int) -> FormativeItemCandidate:
    return FormativeItemCandidate(
        semester="2026-1",
        course_slug="anatomy",
        no=no,
        chapter_no=8,
        topic=f"주제{no}",
        question=f"{no}번 형성문제",
        limit="200자 내외",
        model_answer=f"모범답안{no}",
        purpose=f"목적{no}",
        keywords=[f"키워드{no}"],
        rubric_high="상 루브릭",
        rubric_mid="중 루브릭",
        rubric_low="하 루브릭",
        support_high="상위 지원",
        support_mid="중위 지원",
        support_low="하위 지원",
    )


def test_writes_file_with_top_level_quiz_and_formative_keys(tmp_path: Path) -> None:
    """Top-level yaml must have 'quiz' and 'formative' keys."""
    from maieutica.output.candidate_yaml import write_candidate_yaml

    items = [_quiz_candidate(1, "오답 설명", "도약")]
    formative = [_formative_candidate(1)]
    out = tmp_path / "출제후보_완전판.yaml"
    write_candidate_yaml(items, formative, out)

    assert out.is_file()
    doc = yaml.safe_load(out.read_text(encoding="utf-8"))
    assert isinstance(doc, dict)
    assert "quiz" in doc
    assert "formative" in doc
    assert len(doc["quiz"]) == 1
    assert len(doc["formative"]) == 1


def test_writes_file_with_full_leap_text(tmp_path: Path) -> None:
    from maieutica.output.candidate_yaml import write_candidate_yaml

    leap = "이것은 매우 긴 도약 설명이며 절대 잘리지 않고 완전판에 보존되어야 합니다 " * 5
    items = [_quiz_candidate(1, "오답 설명", leap)]
    out = tmp_path / "출제후보_완전판.yaml"
    write_candidate_yaml(items, [], out)

    assert out.is_file()
    doc = yaml.safe_load(out.read_text(encoding="utf-8"))
    assert doc["quiz"][0]["leap"]["text"] == leap


def test_preserves_option_and_textbook_evidence(tmp_path: Path) -> None:
    from maieutica.output.candidate_yaml import write_candidate_yaml

    items = [_quiz_candidate(1, "오답", "도약")]
    out = tmp_path / "출제후보_완전판.yaml"
    write_candidate_yaml(items, [], out)
    doc = yaml.safe_load(out.read_text(encoding="utf-8"))
    q = doc["quiz"][0]
    assert q["option_evidence"] == [f"근거1-{i}" for i in range(1, 6)]
    assert "textbook_evidence" in q
    assert "leap" in q
    assert "textbook_evidence" in q["leap"]


def test_nested_leap_evidence_preserves_structural_keys(tmp_path: Path) -> None:
    """A grounded leap dumps a nested evidence dict with its structural keys."""
    from maieutica.output.candidate_yaml import write_candidate_yaml

    leap_evidence = MaieuticaTextbookEvidence(
        chunk_id="chunk0800",
        source_file="8장 호흡계통.txt",
        char_start=10,
        char_end=20,
        found_text="허파꽈리",
        search_term="허파꽈리",
        status="확인",
    )
    item = _quiz_candidate(1, "오답", "도약").model_copy(
        update={
            "leap": LeapExplanation(text="도약", textbook_evidence=leap_evidence),
            "textbook_evidence": leap_evidence.model_copy(),
        }
    )
    out = tmp_path / "출제후보_완전판.yaml"
    write_candidate_yaml([item], [], out)

    doc = yaml.safe_load(out.read_text(encoding="utf-8"))
    leap_ev = doc["quiz"][0]["leap"]["textbook_evidence"]
    assert isinstance(leap_ev, dict)
    assert leap_ev["status"] == "확인"
    assert leap_ev["chunk_id"] == "chunk0800"
    assert leap_ev["found_text"] == "허파꽈리"
    assert leap_ev["char_start"] == 10
    assert leap_ev["char_end"] == 20


def test_combined_round_trip_split(tmp_path: Path) -> None:
    """Splitting answer_explanation_combined on the separator recovers parts."""
    from maieutica.output.candidate_yaml import write_candidate_yaml

    wrong = "오답 설명 본문"
    leap = "도약 설명 본문"
    items = [_quiz_candidate(1, wrong, leap)]
    out = tmp_path / "출제후보_완전판.yaml"
    write_candidate_yaml(items, [], out)
    doc = yaml.safe_load(out.read_text(encoding="utf-8"))
    combined = doc["quiz"][0]["answer_explanation_combined"]
    recovered_wrong, recovered_leap = combined.split(_SEP, 1)
    assert recovered_wrong == wrong
    assert recovered_leap == leap


def test_deterministic_bytes(tmp_path: Path) -> None:
    from maieutica.output.candidate_yaml import write_candidate_yaml

    items = [_quiz_candidate(1, "오답", "도약 " * 10), _quiz_candidate(2, "오답2", "도약2")]
    formative = [_formative_candidate(1)]
    a = tmp_path / "a.yaml"
    b = tmp_path / "b.yaml"
    write_candidate_yaml(items, formative, a)
    write_candidate_yaml(items, formative, b)
    assert a.read_bytes() == b.read_bytes()


def test_formative_fields_present(tmp_path: Path) -> None:
    """Formative items must carry adoption_status, review_note, and rubric fields."""
    from maieutica.output.candidate_yaml import write_candidate_yaml

    formative = [_formative_candidate(1)]
    out = tmp_path / "출제후보_완전판.yaml"
    write_candidate_yaml([], formative, out)
    doc = yaml.safe_load(out.read_text(encoding="utf-8"))
    f = doc["formative"][0]
    for field in (
        "no",
        "topic",
        "review_note",
        "adoption_status",
        "rubric_high",
        "rubric_mid",
        "rubric_low",
        "support_high",
        "support_mid",
        "support_low",
        "keywords",
        "textbook_evidence",
    ):
        assert field in f, f"formative item missing field: {field}"
    assert f["adoption_status"] == "생성"
