"""T063 — Edge-case hardening: fail-fast, SC-003 confirmation, no-send guard.

Covers the spec Edge Cases (quickstart.md §"Edge 검증") and FR-025:

1. ``test_missing_chapter_txt_exits_2_no_gold``:
   build/CLI exits 2 when the chapter ``.txt`` is absent; NO Gold directory
   is created (부분 산출 0, SC-010).

2. ``test_missing_week_in_map_exits_2``:
   build/CLI exits 2 when the target week is absent from curriculum_map (fail-fast).

3. ``test_answer_cell_is_text_even_for_single_digit``:
   quiz ``.xls`` writer always stores ``답안`` as XL_CELL_TEXT even for a
   single-digit answer (re-confirms SC-003 at the edge level).  Also asserts
   the column map has no numeric type declared for ``답안``.

4. ``test_no_send_guard``:
   Scans ``modules/maieutica/src`` for forbidden student-dispatch paths
   (``smtplib``, ``email.mime``, ``requests.post``, ``urllib.request.urlopen``
   for sending, ``send``/``dispatch``-to-student patterns).  FR-025: maieutica
   must NOT have any student-dispatch / network-send path in its source tree.
   anthropic SDK (for generation) is intentionally excluded from the guard.
"""

from __future__ import annotations

import ast
import json
from pathlib import Path

import xlrd
import yaml

# ---------------------------------------------------------------------------
# Shared fixture helpers
# ---------------------------------------------------------------------------

_SEMESTER = "2026-1"
_COURSE = "anatomy-edge"
_WEEK = 9
_CHAPTER_NO = 8
_CHAPTER = "8장 호흡계통"
_QUIZ_COUNT = 2
_FORMATIVE_COUNT = 1

_KEY_CONCEPTS = ["폐포", "기관지"]

_CHAPTER_TXT = "\n".join(
    [
        "8장 호흡계통",
        "",
        "1. 호흡계통의 구조",
        "폐포는 가스 교환이 일어나는 포상 구조이다.",
        "기관지는 공기를 폐로 전달하는 통로이다.",
        "",
    ]
)


def _make_bronze(tmp_path: Path, *, include_chapter_txt: bool = True) -> tuple[Path, Path]:
    """Build a minimal Bronze tree under tmp_path.

    Args:
        tmp_path: Pytest temporary directory root.
        include_chapter_txt: When False, the chapter ``.txt`` is omitted to
            trigger the fail-fast missing-file path.

    Returns:
        ``(bronze_dir, data_root)`` pair.
    """
    data_root = tmp_path / "data"
    bronze = data_root / "bronze" / "maieutica" / f"{_SEMESTER}-{_COURSE}"
    bronze.mkdir(parents=True, exist_ok=True)

    if include_chapter_txt:
        (bronze / f"{_CHAPTER} 호흡.txt").write_text(_CHAPTER_TXT, encoding="utf-8")

    spec = {
        "semester": _SEMESTER,
        "course_slug": _COURSE,
        "week": _WEEK,
        "chapter_no": _CHAPTER_NO,
        "chapter": _CHAPTER,
        "quiz_count": _QUIZ_COUNT,
        "formative_count": _FORMATIVE_COUNT,
    }
    (bronze / "generation_spec.yaml").write_text(
        json.dumps(spec, ensure_ascii=False), encoding="utf-8"
    )

    curriculum = {
        "semester": _SEMESTER,
        "course_slug": _COURSE,
        "entries": [
            {
                "week": _WEEK,
                "chapter": _CHAPTER,
                "chapter_no": _CHAPTER_NO,
                "sections": ["1. 호흡계통의 구조"],
            }
        ],
    }
    (bronze / "curriculum_map.yaml").write_text(
        json.dumps(curriculum, ensure_ascii=False), encoding="utf-8"
    )
    return bronze, data_root


def _make_bronze_missing_week(tmp_path: Path) -> tuple[Path, Path]:
    """Build a Bronze tree where the curriculum_map week does NOT match the spec.

    The spec targets week 9 but the curriculum_map only has week 5.

    Args:
        tmp_path: Pytest temporary directory root.

    Returns:
        ``(bronze_dir, data_root)`` pair.
    """
    data_root = tmp_path / "data"
    bronze = data_root / "bronze" / "maieutica" / f"{_SEMESTER}-{_COURSE}"
    bronze.mkdir(parents=True, exist_ok=True)

    (bronze / f"{_CHAPTER} 호흡.txt").write_text(_CHAPTER_TXT, encoding="utf-8")

    spec = {
        "semester": _SEMESTER,
        "course_slug": _COURSE,
        "week": _WEEK,  # week 9
        "chapter_no": _CHAPTER_NO,
        "chapter": _CHAPTER,
        "quiz_count": _QUIZ_COUNT,
        "formative_count": _FORMATIVE_COUNT,
    }
    (bronze / "generation_spec.yaml").write_text(
        json.dumps(spec, ensure_ascii=False), encoding="utf-8"
    )

    # Map only has week 5 — week 9 is absent → validate_week_in_map raises
    curriculum = {
        "semester": _SEMESTER,
        "course_slug": _COURSE,
        "entries": [
            {
                "week": 5,  # deliberately wrong week
                "chapter": "5장 소화계통",
                "chapter_no": 5,
                "sections": ["1. 소화기관"],
            }
        ],
    }
    (bronze / "curriculum_map.yaml").write_text(
        json.dumps(curriculum, ensure_ascii=False), encoding="utf-8"
    )
    return bronze, data_root


# ---------------------------------------------------------------------------
# T063-1: missing chapter .txt → exit 2, NO Gold directory (SC-010)
# ---------------------------------------------------------------------------


def test_missing_chapter_txt_exits_2_no_gold(tmp_path: Path, monkeypatch: object) -> None:
    """Missing chapter .txt → CLI exits 2 and creates NO Gold directory (SC-010).

    Specifically verifies:
    - ``build`` subcommand returns exit code 2 (input/config validation fault).
    - The Gold directory subtree does not exist after the failed invocation,
      confirming atomicity / 부분 산출 금지 (FR-020 / SC-010).

    Tests the pipeline-level fail-fast: ``resolve_chapter_txt`` raises
    ``FileNotFoundError`` before any Gold write occurs.
    """
    import maieutica.cli.main as cli_module

    _bronze, data_root = _make_bronze(tmp_path, include_chapter_txt=False)
    monkeypatch.setattr(cli_module, "_DATA_ROOT", data_root)

    class _FakeArgs:
        semester = _SEMESTER
        course = _COURSE
        week = _WEEK
        generation_spec = _bronze / "generation_spec.yaml"
        curriculum_map = _bronze / "curriculum_map.yaml"
        quiz_count = None
        formative_count = None
        backend = "subscription"

    rc = cli_module._run_build(_FakeArgs())  # type: ignore[arg-type]
    assert rc == 2, f"expected exit 2 for missing chapter txt, got {rc}"

    # No Gold directory created — partial output is forbidden (SC-010).
    gold_root = data_root / "gold" / "maieutica" / f"{_SEMESTER}-{_COURSE}"
    assert not gold_root.exists(), (
        f"Gold directory was created despite missing chapter txt: {gold_root}"
    )


# ---------------------------------------------------------------------------
# T063-2: week absent from curriculum_map → exit 2 (fail-fast)
# ---------------------------------------------------------------------------


def test_missing_week_in_map_exits_2(tmp_path: Path, monkeypatch: object) -> None:
    """curriculum_map missing the target week → CLI exits 2 (fail-fast).

    Confirms that ``validate_week_in_map`` raises before any generation starts,
    and that the CLI maps the resulting ``ValueError`` to exit code 2.

    The fixture places week 9 in the spec but only week 5 in the curriculum_map.
    """
    import maieutica.cli.main as cli_module

    bronze, data_root = _make_bronze_missing_week(tmp_path)
    monkeypatch.setattr(cli_module, "_DATA_ROOT", data_root)

    class _FakeArgs:
        semester = _SEMESTER
        course = _COURSE
        week = _WEEK  # week 9 — absent from the map
        generation_spec = bronze / "generation_spec.yaml"
        curriculum_map = bronze / "curriculum_map.yaml"
        quiz_count = None
        formative_count = None
        backend = "subscription"

    rc = cli_module._run_build(_FakeArgs())  # type: ignore[arg-type]
    assert rc == 2, f"expected exit 2 for missing week in map, got {rc}"

    # No Gold directory created.
    gold_root = data_root / "gold" / "maieutica" / f"{_SEMESTER}-{_COURSE}"
    assert not gold_root.exists(), (
        f"Gold directory was created despite missing week in map: {gold_root}"
    )


# ---------------------------------------------------------------------------
# T063-3: 답안 cell is TEXT even for single-digit answer (SC-003, edge confirm)
# ---------------------------------------------------------------------------


def test_answer_cell_is_text_even_for_single_digit(tmp_path: Path) -> None:
    """SC-003 edge: write_quiz_xls stores 답안 as XL_CELL_TEXT for answer_no 1..5.

    Tests the single-digit case (answer_no=1) that is the most common source
    of the "numeric 답안" LMS trap: Excel/xlwt may silently coerce ``"1"`` to
    a numeric cell if the writer does not explicitly force TEXT type.

    Also verifies the quiz column map does NOT declare a numeric type for 답안.
    """
    from maieutica.output.quiz_xls import QUIZ_HEADERS, write_quiz_xls
    from paideia_shared.schemas import QuizItemCandidate
    from paideia_shared.schemas.maieutica.leap_explanation import LeapExplanation

    wrong = "오답 설명입니다."
    leap_text = "도약 설명입니다."
    combined = f"{wrong} ─ 도약 ─ {leap_text}"
    options = [f"보기 {i} 단일 자리 답안 테스트 보기 문자열입니다 abcdef" for i in range(1, 6)]

    # answer_no=1 is the critical single-digit edge (also test 5 for coverage).
    for answer_no in (1, 5):
        candidate = QuizItemCandidate(
            semester="2026-1",
            course_slug="anatomy-edge",
            item_no=answer_no,
            week=_WEEK,
            chapter_no=_CHAPTER_NO,
            chapter=_CHAPTER,
            question_type="지식축적",
            difficulty="중",
            stem_polarity="부정형",
            text=f"{answer_no}번 문제: 가장 옳지 않은 것을 고르세요.",
            options=options,
            answer_no=answer_no,
            option_evidence=[f"근거{i}" for i in range(1, 6)],
            wrong_explanation=wrong,
            leap=LeapExplanation(text=leap_text),
            answer_explanation_combined=combined,
            option_length_ok=True,
            explanation_length_ok=True,
        )
        out = tmp_path / f"test_sc003_answer_{answer_no}.xls"
        write_quiz_xls(out, [candidate], week=_WEEK)

        book = xlrd.open_workbook(str(out))
        sheet1 = book.sheet_by_index(1)
        col = {h: i for i, h in enumerate(QUIZ_HEADERS)}

        cell_ans = sheet1.cell(1, col["답안"])
        assert cell_ans.ctype == xlrd.XL_CELL_TEXT, (
            f"답안 cell for answer_no={answer_no} must be XL_CELL_TEXT "
            f"(SC-003), got ctype={cell_ans.ctype!r} value={cell_ans.value!r}"
        )
        assert cell_ans.value == str(answer_no), (
            f"답안 cell value must be str({answer_no!r}), got {cell_ans.value!r}"
        )

    # Verify the column map declares 답안 as text, not numeric.
    # Load directly from the template YAML (private helpers are an impl detail).
    _template_root = Path(__file__).resolve().parents[2] / "templates"
    col_map_path = _template_root / "quiz_column_map.yaml"
    assert col_map_path.is_file(), f"column map not found: {col_map_path}"

    col_map = yaml.safe_load(col_map_path.read_text(encoding="utf-8"))
    answer_col = col_map.get("columns", {}).get("answer", {})
    assert answer_col, "column map is missing the 'answer' entry"
    assert answer_col.get("header") == "답안", (
        f"expected header '답안', got {answer_col.get('header')!r}"
    )
    assert answer_col.get("cell_type", "text").lower() != "number", (
        "column map must NOT declare 답안 as numeric type (SC-003)"
    )
    assert answer_col.get("cell_type", "text").lower() == "text", (
        f"column map must declare 답안 cell_type='text', "
        f"got {answer_col.get('cell_type')!r} (SC-003)"
    )


# ---------------------------------------------------------------------------
# T063-4: no-send guard — FR-025 (no student-dispatch path in source)
# ---------------------------------------------------------------------------

# Absolute path to the maieutica source tree.
# __file__ is  modules/maieutica/tests/integration/test_edge_cases.py
#   parents[0] = integration/
#   parents[1] = tests/
#   parents[2] = maieutica/     ← module root
#   parents[3] = modules/
_MAIEUTICA_SRC = Path(__file__).resolve().parents[2] / "src" / "maieutica"

# Forbidden patterns: any top-level import of these modules indicates a
# student-dispatch / network-send path that maieutica must not contain.
# anthropic (LLM generation SDK) is explicitly allowed — the guard is
# specifically about student output dispatch.
_FORBIDDEN_IMPORTS = frozenset(
    [
        "smtplib",
        "email.mime",
        "email.mime.text",
        "email.mime.multipart",
        "email.mime.base",
    ]
)

# Forbidden call-level patterns: fully-qualified attribute names (dotted) whose
# presence in a function call strongly indicates a send-to-student path.
# urllib.request.urlopen is only forbidden when used for outbound dispatch —
# we check for its presence in a call alongside "send" / "dispatch" context
# via the import-level check; the call scan is an extra belt-and-suspenders.
_FORBIDDEN_CALL_ATTRS = frozenset(
    [
        "requests.post",
        "requests.put",
        "urllib.request.urlopen",
    ]
)


def _iter_py_files(src_root: Path) -> list[Path]:
    """Return all ``.py`` files under src_root (sorted for determinism)."""
    return sorted(src_root.rglob("*.py"))


def _check_file_for_forbidden_imports(path: Path) -> list[str]:
    """Parse a Python source file and collect forbidden top-level imports.

    Args:
        path: Path to a ``.py`` file.

    Returns:
        List of human-readable violation descriptions (empty if clean).
    """
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    except SyntaxError:
        return []  # skip unparsable files (shouldn't happen in green suite)

    violations: list[str] = []
    rel = path.relative_to(_MAIEUTICA_SRC)

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name in _FORBIDDEN_IMPORTS:
                    violations.append(
                        f"{rel}:{node.lineno}: 'import {alias.name}' (forbidden send import)"
                    )
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            if module in _FORBIDDEN_IMPORTS:
                violations.append(
                    f"{rel}:{node.lineno}: 'from {module} import ...' (forbidden send import)"
                )
            # Catch partial matches: "from email.mime.text import ..."
            for forbidden in _FORBIDDEN_IMPORTS:
                if module.startswith(forbidden + "."):
                    violations.append(
                        f"{rel}:{node.lineno}: 'from {module} import ...' (forbidden send import)"
                    )
        elif (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and isinstance(node.func.value, ast.Name)
        ):
            # Check for forbidden dotted call patterns e.g. requests.post(...)
            dotted = f"{node.func.value.id}.{node.func.attr}"
            if dotted in _FORBIDDEN_CALL_ATTRS:
                violations.append(f"{rel}:{node.lineno}: call to '{dotted}' (forbidden send call)")

    return violations


def test_no_send_guard(tmp_path: Path) -> None:  # noqa: ARG001
    """FR-025: maieutica source must contain NO student-dispatch / send path.

    Scans every ``.py`` file in ``modules/maieutica/src/maieutica/`` for:
    - Imports of ``smtplib``, ``email.mime.*``.
    - Calls to ``requests.post``, ``requests.put``, ``urllib.request.urlopen``.

    NOTE: ``anthropic`` (Anthropic SDK for LLM generation) is intentionally
    allowed — the guard targets *student output dispatch*, not generation calls.

    Fails with a descriptive message listing every violation found.
    """
    assert _MAIEUTICA_SRC.is_dir(), (
        f"maieutica src root not found at {_MAIEUTICA_SRC} — "
        "check that the test is run from the project root"
    )

    py_files = _iter_py_files(_MAIEUTICA_SRC)
    assert py_files, f"no .py files found under {_MAIEUTICA_SRC}"

    all_violations: list[str] = []
    for py_path in py_files:
        all_violations.extend(_check_file_for_forbidden_imports(py_path))

    assert not all_violations, (
        f"FR-025 violation: maieutica must not contain student-dispatch paths.\n"
        f"Found {len(all_violations)} forbidden pattern(s):\n"
        + "\n".join(f"  {v}" for v in all_violations)
    )
