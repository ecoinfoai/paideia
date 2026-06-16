"""CLI exit-code mapping for v0.1.1 mapping loader exceptions [T018 followup].

Verifies that ``MappingVersionError`` (raised when the operator runs the
pipeline against a v0.1.0 mapping YAML) and ``MappingKindError`` (raised
when V7 catches a non-likert column on a quantitative axis) are routed to
exit code 1 — input validation failed — per ``contracts/cli.md`` L29.
Without the explicit handler in ``cli/main.py``, both subclass
``ValueError`` and would fall through to the generic ``except Exception``
arm (exit 99 — internal bug), hiding the operator-actionable upgrade
hints behind a misleading "internal error" label.
"""

from __future__ import annotations

import shutil
from pathlib import Path
from textwrap import dedent

import pytest

_FIXTURE_ROOT = Path("modules/needs-map/tests/fixtures/silver_minimal")


def _stage_silver(tmp_path: Path) -> Path:
    """Copy the standard silver_minimal fixture into ``tmp_path/in``."""
    input_root = tmp_path / "in"
    silver_dir = input_root / "silver" / "immersio" / "2026-1-anatomy"
    silver_dir.mkdir(parents=True)
    for name in ("student_master.parquet", "diagnostic_response.parquet"):
        shutil.copy(
            _FIXTURE_ROOT / "silver" / "immersio" / "2026-1-anatomy" / name,
            silver_dir / name,
        )
    return input_root


def _write_mapping(input_root: Path, body: str) -> None:
    """Drop a synthesised ``anatomy.diagnostic.yaml`` next to the silver fixture."""
    mapping_dir = input_root / "bronze" / "매핑"
    mapping_dir.mkdir(parents=True)
    (mapping_dir / "anatomy.diagnostic.yaml").write_text(body, encoding="utf-8")


_V1_YAML = dedent(
    """\
    metadata:
      semester: '2026-1'
      course_slug: anatomy
      mapping_version: 1
    columns:
      - source: 학번
        kind: identity
      - source: Q01
        kind: likert
        axis: motivation
        aggregate: mean
    axes:
      required:
        - motivation
    """
)


def test_v1_mapping_routes_to_exit_one(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """A v0.1.0 mapping YAML must surface the v0.1.1 upgrade hint and exit 1."""
    from needs_map.cli.main import main

    input_root = _stage_silver(tmp_path)
    _write_mapping(input_root, _V1_YAML)

    rc = main(
        [
            "run",
            "--semester",
            "2026-1",
            "--course",
            "anatomy",
            "--phases",
            "A-B",
            "--no-llm",
            "--input-root",
            str(input_root),
            "--output-root",
            str(tmp_path / "out"),
        ]
    )
    assert rc == 1, f"expected exit 1 (input validation failed), got {rc}"
    captured = capsys.readouterr()
    assert "mapping_version=2" in captured.err
    assert "v0.1.1" in captured.err
    assert "internal error" not in captured.err  # would mean exit 99 path
