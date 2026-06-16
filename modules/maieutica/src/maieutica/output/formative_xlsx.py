"""T045 — LMS formative `.xlsx` writer (bhu_text_mining ExamPDFGenerator-compatible).

Writes ``Ch{chapter_no:02d}_{chapter}_FormativeTest.xlsx`` with a single
``'Formative Test'`` sheet: row 0 = 14 column headers driven by
``templates/formative_column_map.yaml`` (Constitution III — no hardcoded
headers in this writer's logic) and rows 1..M = formative candidates.

Cell-type fidelity (SC-003, ``[[lms-excel-cell-types]]``)
---------------------------------------------------------
- ``No.`` / ``Chapter`` → numeric cells (int).
- ``Keywords`` → TEXT, the candidate's ``keywords`` list joined by the
  separator declared in the column map (``", "``, matching the real bronze
  sample ``Ch08_호흡계통_FormativeTest.xlsx``).
- every other column → TEXT.

Byte-determinism (SC-009)
-------------------------
openpyxl stamps ``<dcterms:modified>`` / ``<dcterms:created>`` with
``datetime.now()``.  After ``save()`` the file is repacked by
:func:`maieutica.output.determinism.finalize_xlsx` with a pinned timestamp and
fixed ZipInfo date / compresslevel, so two writes of identical inputs are
byte-identical.
"""

from __future__ import annotations

import datetime
from functools import lru_cache
from pathlib import Path
from typing import Any

import openpyxl
import yaml
from paideia_shared.schemas import FormativeItemCandidate

from maieutica.output.determinism import finalize_xlsx
from maieutica.output.paths import atomic_write

# ``templates/`` lives at modules/maieutica/templates, three parents above
# src/maieutica/output/formative_xlsx.py → .../maieutica.
_COLUMN_MAP_PATH = Path(__file__).resolve().parents[3] / "templates" / "formative_column_map.yaml"

# Pinned timestamp for xlsx determinism (mirrors examen.pipeline._PINNED_WHEN).
_PINNED_WHEN = datetime.datetime(2026, 1, 1, 0, 0, 0, tzinfo=datetime.UTC)


@lru_cache(maxsize=1)
def _load_column_map() -> dict[str, Any]:
    """Load and cache ``formative_column_map.yaml``.

    Returns:
        Parsed column-map mapping.

    Raises:
        FileNotFoundError: If the column-map template is missing (boundary).
    """
    if not _COLUMN_MAP_PATH.is_file():
        raise FileNotFoundError(f"formative column map not found: {_COLUMN_MAP_PATH}")
    return yaml.safe_load(_COLUMN_MAP_PATH.read_text(encoding="utf-8"))


def _ordered_columns() -> list[dict[str, Any]]:
    """Return the column definitions in their declared (insertion) order.

    PyYAML preserves mapping insertion order, and ``formative_column_map.yaml``
    lists the columns in the exact 14-column order required by the LMS.

    Returns:
        List of per-column definition dicts (each carrying ``header``, ``field``
        and ``cell_type``).
    """
    column_map = _load_column_map()
    return list(column_map["columns"].values())


@lru_cache(maxsize=1)
def _headers() -> tuple[str, ...]:
    """Return the 14 headers in order, from the column map.

    Returns:
        Tuple of header strings in their LMS-mandated order.
    """
    return tuple(col["header"] for col in _ordered_columns())


# Public, immutable header tuple — sourced from the column map (Constitution III).
FORMATIVE_HEADERS: tuple[str, ...] = _headers()


def _keywords_separator() -> str:
    """Return the ``Keywords`` list-join separator from the column map.

    Returns:
        The separator string (``", "`` in the real bronze sample).
    """
    return str(_load_column_map()["keywords_separator"])


def _sheet_name() -> str:
    """Return the single data sheet's name from the column map.

    Returns:
        The sheet name (``"Formative Test"`` in the real bronze sample).
    """
    return str(_load_column_map()["sheet"])


def _cell_value(item: FormativeItemCandidate, column: dict[str, Any]) -> Any:  # noqa: ANN401
    """Compute the value to write for one column of one candidate.

    Args:
        item: The formative candidate.
        column: The column definition (with ``field`` / ``cell_type``).

    Returns:
        An ``int`` for numeric cells, a ``str`` for text/keywords cells.
    """
    cell_type = column.get("cell_type")
    if cell_type == "number":
        return int(getattr(item, column["field"]))
    if cell_type == "keywords":
        return _keywords_separator().join(item.keywords)
    return str(getattr(item, column["field"]))


def formative_xlsx_filename(chapter_no: int, chapter: str) -> str:
    """Return the contract filename ``Ch{NN}_{chapter}_FormativeTest.xlsx``.

    Args:
        chapter_no: Chapter number (zero-padded to 2 digits).
        chapter: Chapter display name (used verbatim in the filename).

    Returns:
        The formative ``.xlsx`` filename.
    """
    return f"Ch{chapter_no:02d}_{chapter}_FormativeTest.xlsx"


def write_formative_xlsx(
    path: Path,
    candidates: list[FormativeItemCandidate],
) -> None:
    """Write the LMS formative ``.xlsx`` atomically and deterministically.

    The output is byte-identical across runs for identical ``candidates``
    (SC-009).  Cell types follow the column map (SC-003): ``No.``/``Chapter``
    are numeric cells; every other column is text, with ``Keywords`` joined by
    the column-map separator.

    Args:
        path: Destination ``.xlsx`` path.  Parent directories are created if
            missing (symmetry with the quiz writer).
        candidates: Formative candidates (one per data row).
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    columns = _ordered_columns()
    sheet_name = _sheet_name()

    def _write(tmp: Path) -> None:
        workbook = openpyxl.Workbook()
        sheet = workbook.active
        sheet.title = sheet_name

        # Header row.
        sheet.append([column["header"] for column in columns])

        # Data rows.
        for item in candidates:
            sheet.append([_cell_value(item, column) for column in columns])

        workbook.save(str(tmp))
        finalize_xlsx(tmp, _PINNED_WHEN)

    atomic_write(path, _write)


__all__ = [
    "FORMATIVE_HEADERS",
    "formative_xlsx_filename",
    "write_formative_xlsx",
]
