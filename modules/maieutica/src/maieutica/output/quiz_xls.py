"""T032 — LMS quiz upload `.xls` writer (BIFF8, cp949) via xlwt.

Writes ``QuestionUploadExcel_{week}주차.xls`` with two sheets:

- **Sheet 0** — the frozen LMS instruction sheet named
  ``'필독! - 반드시 확인해 주세요!'``, restored verbatim from the frozen asset
  ``assets/lms_quiz_guide_sheet.yaml`` (T031).  The sheet name is an immutable
  LMS contract: the LMS rejects uploads whose first sheet is renamed.
- **Sheet 1** — ``'Sheet1'`` with row 0 = 11 column headers driven by
  ``templates/quiz_column_map.yaml`` (Constitution III — no hardcoded headers in
  this writer's logic) and rows 1..N = quiz candidates.

Cell-type fidelity (SC-003, ``[[lms-excel-cell-types]]``)
---------------------------------------------------------
- ``문제번호`` → numeric cell (``write_number``).
- ``답안`` → TEXT ``str(answer_no)`` (e.g. ``"3"`` — text even without a leading
  zero; the most common LMS trap).
- ``예상주차`` → TEXT zero-padded ``f"{week:03d}"`` (e.g. ``"009"``).
- ``문항유형`` → TEXT constant ``"002"`` (single-choice MCQ).
- ``문제내용`` / ``보기1~5`` / ``답안설명`` → TEXT.

Byte-determinism (SC-009 / R1)
------------------------------
xlwt produces byte-identical output for identical inputs when a single
``Workbook(encoding=...)`` and shared style objects are used (verified by
``determinism.gate_xls_deterministic``); no window/coordinate randomness is
introduced.  The byte-template fallback described in research R1 proved
unnecessary — xlwt is deterministic out of the box for this writer.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

import xlwt
import yaml
from paideia_shared.schemas import QuizItemCandidate

from maieutica.output.paths import atomic_write

# ``templates/`` lives at modules/maieutica/templates, i.e. three parents above
# src/maieutica/output/quiz_xls.py → .../maieutica.
_COLUMN_MAP_PATH = (
    Path(__file__).resolve().parents[3] / "templates" / "quiz_column_map.yaml"
)
# The frozen guide asset lives inside the package, next to this module's parent.
_GUIDE_ASSET_PATH = (
    Path(__file__).resolve().parents[1] / "assets" / "lms_quiz_guide_sheet.yaml"
)

# xlwt encoding for the workbook — BIFF8 text is stored as the workbook encoding.
_WORKBOOK_ENCODING = "utf-8"


@lru_cache(maxsize=1)
def _load_column_map() -> dict[str, Any]:
    """Load and cache ``quiz_column_map.yaml``.

    Returns:
        Parsed column-map mapping.

    Raises:
        FileNotFoundError: If the column-map template is missing (boundary).
    """
    if not _COLUMN_MAP_PATH.is_file():
        raise FileNotFoundError(f"quiz column map not found: {_COLUMN_MAP_PATH}")
    return yaml.safe_load(_COLUMN_MAP_PATH.read_text(encoding="utf-8"))


@lru_cache(maxsize=1)
def _load_guide_asset() -> dict[str, Any]:
    """Load and cache the frozen LMS guide-sheet asset.

    Returns:
        Parsed asset with ``sheet_name``, ``nrows``, ``ncols`` and ``cells``.

    Raises:
        FileNotFoundError: If the frozen asset is missing (boundary).
    """
    if not _GUIDE_ASSET_PATH.is_file():
        raise FileNotFoundError(f"guide sheet asset not found: {_GUIDE_ASSET_PATH}")
    return yaml.safe_load(_GUIDE_ASSET_PATH.read_text(encoding="utf-8"))


def _ordered_columns() -> list[dict[str, Any]]:
    """Return the column definitions in their declared (insertion) order.

    PyYAML preserves mapping insertion order, and ``quiz_column_map.yaml`` lists
    the columns in the exact Sheet1 order required by the LMS.

    Returns:
        List of per-column definition dicts (each carrying ``header``, ``field``,
        ``cell_type`` and optionally ``format``/``constant``).
    """
    column_map = _load_column_map()
    return list(column_map["columns"].values())


@lru_cache(maxsize=1)
def _headers() -> tuple[str, ...]:
    """Return the 11 Sheet1 headers in order, from the column map.

    Returns:
        Tuple of header strings in their LMS-mandated order.
    """
    return tuple(col["header"] for col in _ordered_columns())


# Public, immutable header tuple — sourced from the column map (Constitution III).
QUIZ_HEADERS: tuple[str, ...] = _headers()


def guide_sheet_name() -> str:
    """Return the frozen LMS guide-sheet (Sheet 0) name.

    Returns:
        The immutable instruction-sheet name from the frozen asset.
    """
    return _load_guide_asset()["sheet_name"]


def _field_value(item: QuizItemCandidate, field: str) -> Any:  # noqa: ANN401
    """Resolve a column ``field`` spec against a candidate.

    Supports plain attribute names and ``options[i]`` indexed access, matching
    the field syntax used in ``quiz_column_map.yaml``.

    Args:
        item: The quiz candidate to read from.
        field: Field spec, e.g. ``"item_no"`` or ``"options[0]"``.

    Returns:
        The resolved value.
    """
    if field.startswith("options["):
        idx = int(field[len("options[") : -1])
        return item.options[idx]
    return getattr(item, field)


def _cell_text(item: QuizItemCandidate, column: dict[str, Any], *, week: int) -> str:
    """Compute the TEXT value for one column of one candidate.

    Args:
        item: The quiz candidate.
        column: The column definition (with ``field``/``format``/``constant``).
        week: Target week (for the ``예상주차`` zero-pad format).

    Returns:
        The string to write as a TEXT cell.
    """
    constant = column.get("constant")
    if constant is not None:
        return str(constant)

    fmt = column.get("format")
    if fmt == "zero_pad3":
        # 예상주차: zero-padded 3-digit week, regardless of the candidate's field.
        return f"{week:03d}"

    value = _field_value(item, column["field"])
    return str(value)


def _write_guide_sheet(book: xlwt.Workbook) -> None:
    """Write Sheet 0 from the frozen guide asset onto ``book``.

    Args:
        book: The xlwt workbook to add the guide sheet to.
    """
    asset = _load_guide_asset()
    sheet = book.add_sheet(asset["sheet_name"])
    text_style = xlwt.XFStyle()
    for cell in asset["cells"]:
        sheet.write(cell["row"], cell["col"], cell["text"], text_style)


def _write_data_sheet(
    book: xlwt.Workbook,
    candidates: list[QuizItemCandidate],
    *,
    week: int,
) -> None:
    """Write Sheet 1 (headers + candidate rows) onto ``book``.

    Args:
        book: The xlwt workbook to add the data sheet to.
        candidates: Quiz candidates, one per data row.
        week: Target week (for the ``예상주차`` zero-pad).
    """
    column_map = _load_column_map()
    sheet = book.add_sheet(column_map["sheet"])
    columns = _ordered_columns()

    # A single shared style keeps the xf table small and deterministic.
    text_style = xlwt.XFStyle()
    number_style = xlwt.XFStyle()

    # Header row.
    for col_idx, column in enumerate(columns):
        sheet.write(0, col_idx, column["header"], text_style)

    # Data rows.
    for row_offset, item in enumerate(candidates):
        row = row_offset + 1
        for col_idx, column in enumerate(columns):
            if column.get("cell_type") == "number":
                value = _field_value(item, column["field"])
                sheet.write(row, col_idx, value, number_style)
            else:
                sheet.write(
                    row, col_idx, _cell_text(item, column, week=week), text_style
                )


def write_quiz_xls(
    path: Path,
    candidates: list[QuizItemCandidate],
    *,
    week: int,
) -> None:
    """Write the LMS quiz upload ``.xls`` atomically and deterministically.

    The output is byte-identical across runs for identical ``(candidates, week)``
    (SC-009 / R1).  Cell types follow the column map (SC-003): ``문제번호`` is a
    numeric cell; every other column is text, with ``예상주차``/``문항유형``
    zero-padded.

    Args:
        path: Destination ``.xls`` path.  The parent directory must exist.
        candidates: Quiz candidates (one per data row).
        week: Target week (for the ``예상주차`` zero-pad format).
    """
    def _write(tmp: Path) -> None:
        book = xlwt.Workbook(encoding=_WORKBOOK_ENCODING)
        _write_guide_sheet(book)
        _write_data_sheet(book, candidates, week=week)
        book.save(str(tmp))

    atomic_write(path, _write)


__all__ = ["QUIZ_HEADERS", "guide_sheet_name", "write_quiz_xls"]
