"""T018 — Unit tests for retro_mester.output.paths.

RED→GREEN: tests written first (no impl yet).

Tests:
- bronze_dir / silver_dir / gold_dir: return expected data/{tier}/retro-mester/{key}/ paths.
- output_key: returns "{semester}-{course_slug}".
- data_root override is respected.
"""

from __future__ import annotations

from pathlib import Path


def test_bronze_dir_default_root() -> None:
    """bronze_dir uses 'data' as default root."""
    from retro_mester.output.paths import bronze_dir

    result = bronze_dir("2026-1", "anatomy")
    assert result == Path("data") / "bronze" / "retro-mester" / "2026-1-anatomy"


def test_silver_dir_default_root() -> None:
    """silver_dir uses 'data' as default root."""
    from retro_mester.output.paths import silver_dir

    result = silver_dir("2026-1", "anatomy")
    assert result == Path("data") / "silver" / "retro-mester" / "2026-1-anatomy"


def test_gold_dir_default_root() -> None:
    """gold_dir uses 'data' as default root."""
    from retro_mester.output.paths import gold_dir

    result = gold_dir("2026-1", "anatomy")
    assert result == Path("data") / "gold" / "retro-mester" / "2026-1-anatomy"


def test_bronze_dir_custom_root(tmp_path: Path) -> None:
    """bronze_dir respects data_root override."""
    from retro_mester.output.paths import bronze_dir

    result = bronze_dir("2025-2", "nursing", data_root=tmp_path)
    assert result == tmp_path / "bronze" / "retro-mester" / "2025-2-nursing"


def test_silver_dir_custom_root(tmp_path: Path) -> None:
    """silver_dir respects data_root override."""
    from retro_mester.output.paths import silver_dir

    result = silver_dir("2025-2", "nursing", data_root=tmp_path)
    assert result == tmp_path / "silver" / "retro-mester" / "2025-2-nursing"


def test_gold_dir_custom_root(tmp_path: Path) -> None:
    """gold_dir respects data_root override."""
    from retro_mester.output.paths import gold_dir

    result = gold_dir("2025-2", "nursing", data_root=tmp_path)
    assert result == tmp_path / "gold" / "retro-mester" / "2025-2-nursing"


def test_output_key_format() -> None:
    """output_key returns '{semester}-{course_slug}'."""
    from retro_mester.output.paths import output_key

    assert output_key("2026-1", "anatomy") == "2026-1-anatomy"
    assert output_key("2025-2", "nursing") == "2025-2-nursing"


def test_module_name_is_retro_mester_hyphen() -> None:
    """Path middle segment must be 'retro-mester' (hyphen, not underscore)."""
    from retro_mester.output.paths import gold_dir

    result = gold_dir("2026-1", "anatomy")
    parts = result.parts
    assert "retro-mester" in parts, f"Expected 'retro-mester' in path parts, got {parts}"
