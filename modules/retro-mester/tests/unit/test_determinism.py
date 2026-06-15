"""T017 — Unit tests for retro_mester.output.determinism.

RED→GREEN: tests written first (no impl yet).

Tests:
- finalize_xlsx: two writes with same ``when`` → byte-identical files.
- parquet_write_options: correct dict shape.
- dump_yaml: stable and sort_keys-sorted output.
"""

from __future__ import annotations

import datetime
import io
import zipfile
from pathlib import Path
from typing import Any

import openpyxl
import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_xlsx(path: Path) -> None:
    """Write a minimal xlsx with one cell to ``path``."""
    wb = openpyxl.Workbook()
    ws = wb.active
    ws["A1"] = "retro-mester test"  # type: ignore[index]
    wb.save(path)


# ---------------------------------------------------------------------------
# finalize_xlsx
# ---------------------------------------------------------------------------


def test_finalize_xlsx_byte_identical(tmp_path: Path) -> None:
    """Two xlsx files finalised with the same ``when`` must be byte-identical."""
    from retro_mester.output.determinism import finalize_xlsx

    when = datetime.datetime(2025, 1, 1, 0, 0, 0, tzinfo=datetime.timezone.utc)

    path_a = tmp_path / "a.xlsx"
    path_b = tmp_path / "b.xlsx"

    _make_xlsx(path_a)
    _make_xlsx(path_b)

    finalize_xlsx(path_a, when)
    finalize_xlsx(path_b, when)

    assert path_a.read_bytes() == path_b.read_bytes(), (
        "finalize_xlsx must produce byte-identical output for the same `when`"
    )


def test_finalize_xlsx_pins_modified(tmp_path: Path) -> None:
    """``<dcterms:modified>`` must reflect the supplied ``when``."""
    from retro_mester.output.determinism import finalize_xlsx

    when = datetime.datetime(2024, 6, 15, 12, 0, 0, tzinfo=datetime.timezone.utc)
    path = tmp_path / "test.xlsx"
    _make_xlsx(path)
    finalize_xlsx(path, when)

    with zipfile.ZipFile(path, "r") as zf:
        core_xml = zf.read("docProps/core.xml").decode("utf-8")

    assert "2024-06-15T12:00:00Z" in core_xml, (
        "finalize_xlsx must pin <dcterms:modified> to the supplied when"
    )


def test_finalize_xlsx_pins_created(tmp_path: Path) -> None:
    """``<dcterms:created>`` must also be pinned to ``when``."""
    from retro_mester.output.determinism import finalize_xlsx

    when = datetime.datetime(2024, 6, 15, 12, 0, 0, tzinfo=datetime.timezone.utc)
    path = tmp_path / "test.xlsx"
    _make_xlsx(path)
    finalize_xlsx(path, when)

    with zipfile.ZipFile(path, "r") as zf:
        core_xml = zf.read("docProps/core.xml").decode("utf-8")

    # Both dcterms elements must be pinned (not just modified)
    assert core_xml.count("2024-06-15T12:00:00Z") >= 2, (
        "finalize_xlsx must pin BOTH <dcterms:created> and <dcterms:modified>"
    )


# ---------------------------------------------------------------------------
# parquet_write_options
# ---------------------------------------------------------------------------


def test_parquet_write_options_shape() -> None:
    """parquet_write_options() must return the mandated dict."""
    from retro_mester.output.determinism import parquet_write_options

    opts = parquet_write_options()
    assert opts == {
        "use_dictionary": False,
        "write_statistics": False,
        "compression": "snappy",
    }


# ---------------------------------------------------------------------------
# dump_yaml
# ---------------------------------------------------------------------------


def test_dump_yaml_sorted_keys() -> None:
    """dump_yaml must emit keys in alphabetical order."""
    from retro_mester.output.determinism import dump_yaml

    obj = {"z_key": 1, "a_key": 2, "m_key": 3}
    result = dump_yaml(obj)
    lines = [ln for ln in result.splitlines() if ":" in ln]
    keys = [ln.split(":")[0].strip() for ln in lines]
    assert keys == sorted(keys), f"Keys not sorted: {keys}"


def test_dump_yaml_stable() -> None:
    """Two calls with equal obj must return identical strings."""
    from retro_mester.output.determinism import dump_yaml

    obj = {"b": [3, 1, 2], "a": {"x": 10, "y": 20}}
    assert dump_yaml(obj) == dump_yaml(obj)


def test_dump_yaml_ends_with_newline() -> None:
    """Output must end with exactly one newline."""
    from retro_mester.output.determinism import dump_yaml

    result = dump_yaml({"key": "value"})
    assert result.endswith("\n")
    assert not result.endswith("\n\n")


def test_dump_yaml_unicode_passthrough() -> None:
    """Korean characters must not be escaped."""
    from retro_mester.output.determinism import dump_yaml

    result = dump_yaml({"항목": "값"})
    assert "항목" in result
    assert "값" in result
