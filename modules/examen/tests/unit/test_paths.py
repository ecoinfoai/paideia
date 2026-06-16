"""Unit tests for examen.output.paths — T013.

TDD: tests written BEFORE implementation.
"""

from __future__ import annotations

from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Path convention helpers
# ---------------------------------------------------------------------------


class TestDataPaths:
    def test_bronze_dir_convention(self, tmp_path: Path) -> None:
        from examen.output.paths import bronze_dir

        b = bronze_dir("2026-1", "anatomy", data_root=tmp_path)
        assert b == tmp_path / "bronze" / "examen" / "2026-1-anatomy"

    def test_silver_dir_convention(self, tmp_path: Path) -> None:
        from examen.output.paths import silver_dir

        s = silver_dir("2026-1", "anatomy", data_root=tmp_path)
        assert s == tmp_path / "silver" / "examen" / "2026-1-anatomy"

    def test_gold_dir_convention(self, tmp_path: Path) -> None:
        from examen.output.paths import gold_dir

        g = gold_dir("2026-1", "anatomy", data_root=tmp_path)
        assert g == tmp_path / "gold" / "examen" / "2026-1-anatomy"

    def test_paths_follow_module_convention(self, tmp_path: Path) -> None:
        """All three tiers use /examen/ subdirectory."""
        from examen.output.paths import bronze_dir, gold_dir, silver_dir

        for fn in (bronze_dir, silver_dir, gold_dir):
            p = fn("2026-1", "anatomy", data_root=tmp_path)
            assert "examen" in p.parts


# ---------------------------------------------------------------------------
# atomic_write
# ---------------------------------------------------------------------------


class TestAtomicWrite:
    def test_successful_write_produces_file(self, tmp_path: Path) -> None:
        from examen.output.paths import atomic_write

        target = tmp_path / "sub" / "out.txt"
        target.parent.mkdir(parents=True)

        def writer(p: Path) -> None:
            p.write_text("hello", encoding="utf-8")

        atomic_write(target, writer)
        assert target.read_text(encoding="utf-8") == "hello"

    def test_no_partial_file_on_failure(self, tmp_path: Path) -> None:
        """If write_fn raises, the target file must NOT exist afterward."""
        from examen.output.paths import atomic_write

        target = tmp_path / "out.txt"

        def bad_writer(p: Path) -> None:
            p.write_text("partial content", encoding="utf-8")
            raise RuntimeError("simulated failure")

        with pytest.raises(RuntimeError, match="simulated failure"):
            atomic_write(target, bad_writer)

        # Target must not exist (atomic guarantee)
        assert not target.exists()
        # No orphaned temp file should remain
        assert not list(tmp_path.glob(".tmp_*"))

    def test_atomic_write_replaces_existing_file(self, tmp_path: Path) -> None:
        """Existing file is atomically replaced."""
        from examen.output.paths import atomic_write

        target = tmp_path / "out.txt"
        target.write_text("old", encoding="utf-8")

        def writer(p: Path) -> None:
            p.write_text("new", encoding="utf-8")

        atomic_write(target, writer)
        assert target.read_text(encoding="utf-8") == "new"

    def test_temp_file_in_same_directory(self, tmp_path: Path) -> None:
        """Temp file is placed in the same directory as target (same-device rename)."""
        from examen.output.paths import atomic_write

        target = tmp_path / "out.txt"
        seen_parent: list[Path] = []

        def writer(p: Path) -> None:
            seen_parent.append(p.parent)
            p.write_text("x", encoding="utf-8")

        atomic_write(target, writer)
        assert seen_parent[0] == tmp_path


# ---------------------------------------------------------------------------
# Output separation (run-versioned Gold paths)
# ---------------------------------------------------------------------------


class TestOutputSeparation:
    def test_run_gold_path_differs_per_run_id(self, tmp_path: Path) -> None:
        """Two different run_ids produce distinct paths."""
        from examen.output.paths import run_gold_dir

        p1 = run_gold_dir("2026-1", "anatomy", run_id="abc123", data_root=tmp_path)
        p2 = run_gold_dir("2026-1", "anatomy", run_id="def456", data_root=tmp_path)
        assert p1 != p2

    def test_run_gold_path_is_under_gold_dir(self, tmp_path: Path) -> None:
        """Run-versioned path is a subdirectory of the canonical Gold dir."""
        from examen.output.paths import gold_dir, run_gold_dir

        gold = gold_dir("2026-1", "anatomy", data_root=tmp_path)
        run_path = run_gold_dir("2026-1", "anatomy", run_id="abc123", data_root=tmp_path)
        # run_path should be inside the gold dir tree
        assert str(run_path).startswith(str(gold))

    def test_same_run_id_produces_same_path(self, tmp_path: Path) -> None:
        """Deterministic: same run_id always yields the same path."""
        from examen.output.paths import run_gold_dir

        p1 = run_gold_dir("2026-1", "anatomy", run_id="stable", data_root=tmp_path)
        p2 = run_gold_dir("2026-1", "anatomy", run_id="stable", data_root=tmp_path)
        assert p1 == p2

    def test_run_gold_does_not_equal_base_gold(self, tmp_path: Path) -> None:
        """Run-versioned path ≠ base Gold dir (a re-run never clobbers base)."""
        from examen.output.paths import gold_dir, run_gold_dir

        gold = gold_dir("2026-1", "anatomy", data_root=tmp_path)
        run_path = run_gold_dir("2026-1", "anatomy", run_id="abc", data_root=tmp_path)
        assert run_path != gold
