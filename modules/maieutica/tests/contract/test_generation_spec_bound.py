"""Contract tests for ``MaieuticaGenerationSpec.quiz_count`` upper bound (FR-005).

FR-005: quiz candidate count N must be 1..20 inclusive; out-of-range requests
are rejected before generation with the expected/actual reported.

These tests pin the schema bound (``ge=1, le=20``) and the CLI ``--quiz-count``
override re-validation path (a violating override must exit 2).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from maieutica.cli.main import app
from paideia_shared.schemas import MaieuticaGenerationSpec
from pydantic import ValidationError

_SEMESTER = "2026-1"
_COURSE = "anatomy-physiology"


def _base_generation_spec(**overrides: object) -> dict:
    base: dict = {
        "semester": _SEMESTER,
        "course_slug": _COURSE,
        "week": 1,
        "chapter_no": 1,
        "chapter": "1장 세포의 구조",
        "quiz_count": 20,
        "formative_count": 3,
    }
    base.update(overrides)
    return base


# ---------------------------------------------------------------------------
# Schema bound (T008)
# ---------------------------------------------------------------------------


def test_quiz_count_20_allowed() -> None:
    """quiz_count=20 (the upper bound) constructs without error."""
    spec = MaieuticaGenerationSpec.model_validate(_base_generation_spec(quiz_count=20))
    assert spec.quiz_count == 20


def test_quiz_count_21_rejected() -> None:
    """quiz_count=21 (> 20) raises a ValidationError (FR-005)."""
    with pytest.raises(ValidationError):
        MaieuticaGenerationSpec.model_validate(
            _base_generation_spec(quiz_count=21)
        )


def test_quiz_count_1_allowed() -> None:
    """quiz_count=1 (the lower bound) constructs without error."""
    spec = MaieuticaGenerationSpec.model_validate(_base_generation_spec(quiz_count=1))
    assert spec.quiz_count == 1


def test_quiz_count_0_rejected() -> None:
    """quiz_count=0 (< 1) raises a ValidationError."""
    with pytest.raises(ValidationError):
        MaieuticaGenerationSpec.model_validate(_base_generation_spec(quiz_count=0))


# ---------------------------------------------------------------------------
# CLI --quiz-count override re-validation (T009)
# ---------------------------------------------------------------------------


def _build_plan_bronze(tmp_path: Path) -> None:
    """Lay out a minimal Bronze tree (spec + curriculum map) for ``plan``.

    ``plan`` needs only the generation_spec + curriculum_map (no chapter .txt,
    no LLM responses), so it is the lightest path that exercises
    ``_load_inputs`` override re-validation.
    """
    bronze = tmp_path / "data" / "bronze" / "maieutica" / f"{_SEMESTER}-{_COURSE}"
    bronze.mkdir(parents=True, exist_ok=True)

    spec = _base_generation_spec(quiz_count=20)
    (bronze / "generation_spec.yaml").write_text(
        json.dumps(spec, ensure_ascii=False), encoding="utf-8"
    )

    curriculum = {
        "semester": _SEMESTER,
        "course_slug": _COURSE,
        "entries": [
            {
                "week": 1,
                "chapter": "1장 세포의 구조",
                "chapter_no": 1,
                "sections": ["1. 세포의 구조"],
            }
        ],
    }
    (bronze / "curriculum_map.yaml").write_text(
        json.dumps(curriculum, ensure_ascii=False), encoding="utf-8"
    )


_COMMON = ["--semester", _SEMESTER, "--course", _COURSE, "--week", "1"]


def test_cli_quiz_count_21_override_exits_2(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """``plan --quiz-count 21`` re-validates the override and exits 2 (FR-005)."""
    _build_plan_bronze(tmp_path)
    monkeypatch.chdir(tmp_path)
    rc = app(["plan", *_COMMON, "--quiz-count", "21"])
    assert rc == 2


def test_cli_quiz_count_20_override_succeeds(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """``plan --quiz-count 20`` is within bound and does not error (exit 0)."""
    _build_plan_bronze(tmp_path)
    monkeypatch.chdir(tmp_path)
    rc = app(["plan", *_COMMON, "--quiz-count", "20"])
    assert rc == 0
