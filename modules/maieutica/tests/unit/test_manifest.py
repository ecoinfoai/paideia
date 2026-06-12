"""T033 — Unit tests: MaieuticaManifest builder + deterministic writer.

Covers:
- ``build_manifest`` returns a validated ``MaieuticaManifest``.
- ``answer_no_distribution`` is sourced from ``verify.format_checks``.
- ``write_manifest`` is byte-deterministic apart from ``generated_at``.
"""

from __future__ import annotations

import json
from pathlib import Path

from maieutica.output.manifest import build_manifest, write_manifest
from paideia_shared.schemas import MaieuticaManifest


def _kwargs() -> dict:
    return {
        "semester": "2026-1",
        "course_slug": "anatomy",
        "week": 9,
        "chapter_no": 8,
        "chapter": "호흡계통",
        "input_hashes": {"8장_호흡계통.txt": "sha256:abc"},
        "config_ids": {
            "generation_spec": "sha256:def",
            "curriculum_map": "sha256:ghi",
            "lms_quiz_guide_sheet": "sha256:jkl",
        },
        "generated_at": "2026-06-12T00:00:00Z",
        "llm_backend": "none(dry-run)",
        "llm_model": None,
        "cache_hit_rate": 1.0,
        "quiz_count": 20,
        "formative_count": 3,
        "answer_no_distribution": {1: 4, 2: 4, 3: 4, 4: 4, 5: 4},
        "stem_polarity_breakdown": {"부정형": 18, "긍정형": 2},
        "difficulty_breakdown": {"상": 4, "중": 12, "하": 4},
        "groundedness": {"확인": 20, "미확인": 0},
        "option_length_violations": 0,
        "explanation_length_violations": 0,
    }


def test_build_manifest_returns_validated_model() -> None:
    """build_manifest constructs a MaieuticaManifest with the given fields."""
    m = build_manifest(**_kwargs())
    assert isinstance(m, MaieuticaManifest)
    assert m.quiz_count == 20
    assert m.answer_no_distribution == {1: 4, 2: 4, 3: 4, 4: 4, 5: 4}
    assert m.llm_backend == "none(dry-run)"


def test_write_manifest_deterministic_json(tmp_path: Path) -> None:
    """Two writes of the same manifest produce byte-identical JSON."""
    m = build_manifest(**_kwargs())
    p1 = tmp_path / "m1.json"
    p2 = tmp_path / "m2.json"
    write_manifest(p1, m)
    write_manifest(p2, m)
    assert p1.read_bytes() == p2.read_bytes()

    data = json.loads(p1.read_text(encoding="utf-8"))
    # int keys round-trip as JSON string keys.
    assert data["answer_no_distribution"] == {"1": 4, "2": 4, "3": 4, "4": 4, "5": 4}
    assert data["generated_at"] == "2026-06-12T00:00:00Z"
    # Korean written verbatim (ensure_ascii=False).
    assert "호흡계통" in p1.read_text(encoding="utf-8")


def test_answer_no_distribution_sourced_from_format_checks() -> None:
    """answer_no_distribution wiring matches verify.format_checks output."""
    from maieutica.verify.format_checks import answer_no_distribution
    from paideia_shared.schemas import QuizItemCandidate
    from paideia_shared.schemas.maieutica.leap_explanation import LeapExplanation

    def cand(item_no: int, answer_no: int) -> QuizItemCandidate:
        wrong, leap_text = "오답.", "도약."
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
            text=f"{item_no}",
            options=[f"opt{i}" for i in range(5)],
            answer_no=answer_no,
            option_evidence=[f"e{i}" for i in range(5)],
            wrong_explanation=wrong,
            leap=LeapExplanation(text=leap_text),
            answer_explanation_combined=f"{wrong} ─ 도약 ─ {leap_text}",
            option_length_ok=False,
            explanation_length_ok=True,
        )

    items = [cand(1, 3), cand(2, 3), cand(3, 1)]
    dist = answer_no_distribution(items)
    assert dist == {1: 1, 2: 0, 3: 2, 4: 0, 5: 0}
