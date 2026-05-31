"""Unit tests for examen.output.determinism — T014.

TDD: tests written BEFORE implementation.
"""

from __future__ import annotations

import datetime
import re
import zipfile
from pathlib import Path

# ---------------------------------------------------------------------------
# finalize_xlsx
# ---------------------------------------------------------------------------

def _make_minimal_xlsx(path: Path) -> None:
    """Create a minimal XLSX file with a docProps/core.xml containing dcterms:modified."""
    import openpyxl

    wb = openpyxl.Workbook()
    wb.save(str(path))


class TestFinalizeXlsx:
    def test_dcterms_modified_is_pinned(self, tmp_path: Path) -> None:
        """After finalize_xlsx, docProps/core.xml dcterms:modified equals the pinned value."""
        from examen.output.determinism import finalize_xlsx

        xlsx = tmp_path / "test.xlsx"
        _make_minimal_xlsx(xlsx)

        when = datetime.datetime(2026, 1, 1, 0, 0, 0)
        finalize_xlsx(xlsx, when)

        with zipfile.ZipFile(xlsx, "r") as zf:
            core_xml = zf.read("docProps/core.xml").decode("utf-8")

        modified_re = re.compile(r"<dcterms:modified[^>]*>([^<]+)</dcterms:modified>")
        match = modified_re.search(core_xml)
        assert match, "dcterms:modified not found in core.xml"
        assert match.group(1) == "2026-01-01T00:00:00Z"

    def test_two_calls_produce_byte_identical_output(self, tmp_path: Path) -> None:
        """Two sequential finalize_xlsx calls on separate copies produce identical bytes."""
        from examen.output.determinism import finalize_xlsx

        xlsx_a = tmp_path / "a.xlsx"
        xlsx_b = tmp_path / "b.xlsx"
        _make_minimal_xlsx(xlsx_a)
        _make_minimal_xlsx(xlsx_b)

        when = datetime.datetime(2026, 3, 15, 12, 0, 0)
        finalize_xlsx(xlsx_a, when)
        finalize_xlsx(xlsx_b, when)

        assert xlsx_a.read_bytes() == xlsx_b.read_bytes(), (
            "finalize_xlsx must produce byte-identical output for identical inputs"
        )

    def test_zip_entries_use_fixed_date_time(self, tmp_path: Path) -> None:
        """All zip entries use the fixed date_time (1980,1,1,0,0,0)."""
        from examen.output.determinism import finalize_xlsx

        xlsx = tmp_path / "fixed_date.xlsx"
        _make_minimal_xlsx(xlsx)
        finalize_xlsx(xlsx, datetime.datetime(2026, 1, 1))

        with zipfile.ZipFile(xlsx, "r") as zf:
            for info in zf.infolist():
                assert info.date_time == (1980, 1, 1, 0, 0, 0), (
                    f"Entry {info.filename!r} has date_time {info.date_time}, expected (1980,1,1,0,0,0)"
                )


# ---------------------------------------------------------------------------
# dump_yaml
# ---------------------------------------------------------------------------

class TestDumpYaml:
    def test_byte_identical_across_two_calls(self) -> None:
        """dump_yaml is deterministic: two calls with same input produce identical output."""
        from examen.output.determinism import dump_yaml

        obj = {"z_key": "value", "a_key": 42, "m_key": [1, 2, 3]}
        r1 = dump_yaml(obj)
        r2 = dump_yaml(obj)
        assert r1 == r2

    def test_unicode_preserved(self) -> None:
        """Korean characters are preserved, not escaped."""
        from examen.output.determinism import dump_yaml

        obj = {"제목": "기말고사", "항목": ["호흡계통", "근육계통"]}
        result = dump_yaml(obj)
        assert "기말고사" in result
        assert "호흡계통" in result
        # Must not be escaped (no \\uXXXX)
        assert "\\u" not in result

    def test_sorted_keys(self) -> None:
        """Keys are sorted alphabetically for determinism."""
        from examen.output.determinism import dump_yaml

        obj = {"z": 1, "a": 2, "m": 3}
        result = dump_yaml(obj)
        lines = [line for line in result.splitlines() if ":" in line]
        keys = [line.split(":")[0].strip() for line in lines]
        assert keys == sorted(keys), f"Keys not sorted: {keys}"

    def test_roundtrip(self) -> None:
        """dump_yaml output can be parsed back to the original object."""
        import yaml as pyyaml
        from examen.output.determinism import dump_yaml

        obj = {"key": "value", "nested": {"a": 1, "b": 2}, "list": [1, 2, 3]}
        dumped = dump_yaml(obj)
        restored = pyyaml.safe_load(dumped)
        assert restored == obj

    def test_ends_with_newline(self) -> None:
        """YAML output ends with exactly one newline."""
        from examen.output.determinism import dump_yaml

        result = dump_yaml({"x": 1})
        assert result.endswith("\n"), "YAML must end with a newline"
        assert not result.endswith("\n\n"), "YAML must not end with double newline"


# ---------------------------------------------------------------------------
# parquet_write_options
# ---------------------------------------------------------------------------

class TestParquetWriteOptions:
    def test_returns_expected_flags(self) -> None:
        """parquet_write_options returns dict with use_dictionary=False, write_statistics=False."""
        from examen.output.determinism import parquet_write_options

        opts = parquet_write_options()
        assert opts["use_dictionary"] is False
        assert opts["write_statistics"] is False

    def test_compression_is_snappy(self) -> None:
        """Default compression is snappy (matches immersio pattern)."""
        from examen.output.determinism import parquet_write_options

        opts = parquet_write_options()
        assert opts.get("compression") == "snappy"
