"""--semester / --course / --exam-name format tests (T102, FR-F03 + FR-B04)."""

from __future__ import annotations

import pytest

from immersio.cli.main import _build_parser


def _parse(*extra: str):
    """argparse with required base args + extra; returns (args | exit_code)."""
    parser = _build_parser()
    base = [
        "email",
        "--profile",
        "alpha-prof",
        "--exam-name",
        "중간고사",
    ]
    return parser.parse_args(base + list(extra))


def test_semester_2026_1_accepted() -> None:
    args = _parse("--semester", "2026-1", "--course", "anatomy")
    assert args.semester == "2026-1"


def test_semester_2025_w_accepted() -> None:
    """W (winter) is a valid semester code per SemesterCode regex."""
    args = _parse("--semester", "2025-W", "--course", "anatomy")
    assert args.semester == "2025-W"


def test_course_anatomy_accepted() -> None:
    args = _parse("--semester", "2026-1", "--course", "anatomy")
    assert args.course == "anatomy"


def test_exam_name_korean_accepted() -> None:
    args = _parse(
        "--semester", "2026-1", "--course", "anatomy"
    )
    # default already injected by _parse — ensures Korean string survives
    assert args.exam_name == "중간고사"


# Format violations are enforced by the email subparser's pipeline /
# pre-flight validation (Pydantic + regex inside semantics rather than
# argparse choices). The argparse layer accepts any string then the
# pipeline rejects with exit 1 — covered by the existing CLI smoke +
# pipeline integration tests. The unit-level concern below is that the
# CLI accepts the strings WITHOUT crashing (downstream handles the
# regex check).


def test_semester_invalid_format_passes_argparse() -> None:
    """argparse accepts the string; pipeline-level regex (FR-F03) rejects."""
    args = _parse("--semester", "26-1", "--course", "anatomy")
    # argparse layer accepts; downstream pipeline _SEMESTER_PATTERN check
    # would reject. This invariant is owned by pipeline-level tests.
    assert args.semester == "26-1"


def test_required_args_missing_exits_2() -> None:
    parser = _build_parser()
    with pytest.raises(SystemExit) as exc_info:
        parser.parse_args(["email", "--profile", "alpha-prof"])
    assert exc_info.value.code == 2


# CLI entry-level format validation (post-argparse) — FR-F03 + FR-B04.
# Closes the gap between unit tests (argparse-only) and the actual CLI
# behavior. Without this guard, malformed --semester surfaces as Phase B
# "directory not found" with a misleading error message.

from immersio.cli.main import app


def test_email_invalid_semester_exits_1(capsys) -> None:
    """--semester '26-1' rejected at CLI entry, before pipeline starts."""
    rc = app([
        "email",
        "--profile", "alpha-prof",
        "--semester", "26-1",
        "--course", "anatomy",
        "--exam-name", "중간고사",
    ])
    assert rc == 1
    captured = capsys.readouterr()
    assert "invalid_semester" in captured.err
    assert "YYYY-N" in captured.err


def test_email_invalid_course_exits_1(capsys) -> None:
    """--course 'Anatomy' (uppercase) rejected at CLI entry."""
    rc = app([
        "email",
        "--profile", "alpha-prof",
        "--semester", "2026-1",
        "--course", "Anatomy",
        "--exam-name", "중간고사",
    ])
    assert rc == 1
    captured = capsys.readouterr()
    assert "invalid_course" in captured.err


def test_email_empty_exam_name_exits_1(capsys) -> None:
    """--exam-name whitespace-only rejected (FR-B04)."""
    rc = app([
        "email",
        "--profile", "alpha-prof",
        "--semester", "2026-1",
        "--course", "anatomy",
        "--exam-name", "   ",
    ])
    assert rc == 1
    captured = capsys.readouterr()
    assert "invalid_exam_name" in captured.err
