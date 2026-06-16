"""Integration test: font missing → exit 6 + zero disk writes (T021 RED).

Per spec FR-001 + FR-005 (US1, atomic fail-fast):
- When ``resolve_korean_font_paths`` raises ``KoreanFontUnavailableError``
  at CLI entry, the pipeline MUST refuse to start.
- Exit code MUST be 6 (per contracts/cli.md L40).
- Zero files MUST land in either ``data/silver/needs-map/{key}/`` or
  ``data/gold/needs-map/{key}/`` (atomicity).
- The stderr block MUST carry the platform install hints
  (NixOS / Ubuntu / macOS) per contracts/cli.md L66-69.

This test monkeypatches the resolver so it does not depend on the
operator's actual font installation; the goal is to verify the CLI's
*reaction* to ``KoreanFontUnavailableError``, not to test fc-match itself
(those unit tests live in ``tests/unit/test_fonts.py``).

Spec: 003-needs-map-v0-1-1/tasks.md T021.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

_FIXTURE_ROOT = Path("modules/needs-map/tests/fixtures/silver_minimal")
_FULL_MAPPING = Path("modules/needs-map/tests/fixtures/mappings/anatomy_full.diagnostic.yaml")


def _stage(tmp_path: Path) -> Path:
    """Stage silver_minimal fixture under ``tmp_path/in`` and return input root."""
    input_root = tmp_path / "in"
    silver_dir = input_root / "silver" / "immersio" / "2026-1-anatomy"
    silver_dir.mkdir(parents=True)
    for name in ("student_master.parquet", "diagnostic_response.parquet"):
        shutil.copy(
            _FIXTURE_ROOT / "silver" / "immersio" / "2026-1-anatomy" / name,
            silver_dir / name,
        )
    mapping_dir = input_root / "bronze" / "매핑"
    mapping_dir.mkdir(parents=True)
    shutil.copy(_FULL_MAPPING, mapping_dir / "anatomy.diagnostic.yaml")
    return input_root


def _count_files(directory: Path) -> int:
    if not directory.exists():
        return 0
    return sum(1 for _ in directory.rglob("*") if _.is_file())


def test_font_unavailable_exits_six_and_writes_nothing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Pipeline entry must short-circuit on KoreanFontUnavailableError.

    - exit code 6
    - zero files under data/silver/needs-map/{key}/
    - zero files under data/gold/needs-map/{key}/
    - stderr contains platform install hints (NixOS / Ubuntu / macOS)
    """
    from needs_map import fonts as fonts_module
    from needs_map.cli.main import main

    input_root = _stage(tmp_path)
    output_root = tmp_path / "out"
    silver_target = output_root / "silver" / "needs-map" / "2026-1-anatomy"
    gold_target = output_root / "gold" / "needs-map" / "2026-1-anatomy"

    def _raise_unavailable() -> tuple[Path, Path]:
        raise fonts_module.KoreanFontUnavailableError(
            "ERROR: Required Korean font 'NanumGothic Regular' not resolved.\n"
            "  Tried (in order):\n"
            "    1. PAIDEIA_KR_FONT_PATH (env-var)            → not set\n"
            "    2. fc-match 'NanumGothic'                    → matched 'DejaVu Sans'\n"
            "                                                 (NanumGothic not in result path)\n"
            "  Install:\n"
            "    NixOS:        home.packages = [ pkgs.nanum ];\n"
            "    Ubuntu/Debian: sudo apt install fonts-nanum\n"
            "    macOS:         brew install --cask font-nanum-gothic\n"
            "  Then re-run, or set PAIDEIA_KR_FONT_PATH to a verified .ttf path.\n"
            "Exit code: 6"
        )

    monkeypatch.setattr(fonts_module, "resolve_korean_font_paths", _raise_unavailable)

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
            str(output_root),
        ]
    )
    captured = capsys.readouterr()

    assert rc == 6, f"expected exit 6 (font unavailable), got {rc}"
    assert _count_files(silver_target) == 0, (
        f"expected zero silver files, found {_count_files(silver_target)}"
    )
    assert _count_files(gold_target) == 0, (
        f"expected zero gold files, found {_count_files(gold_target)}"
    )
    # platform install hints (contracts/cli.md L66-69)
    assert "NixOS" in captured.err
    assert "Ubuntu" in captured.err or "apt install" in captured.err
    assert "macOS" in captured.err or "brew install" in captured.err
