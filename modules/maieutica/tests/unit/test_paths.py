"""Unit tests for maieutica.output.paths — T014.

TDD: tests written BEFORE implementation (RED→GREEN).
"""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Path convention helpers
# ---------------------------------------------------------------------------


class TestDataPaths:
    def test_bronze_dir_convention(self, tmp_path: Path) -> None:
        from maieutica.output.paths import bronze_dir

        b = bronze_dir("2026-1", "anatomy", data_root=tmp_path)
        assert b == tmp_path / "bronze" / "maieutica" / "2026-1-anatomy"

    def test_silver_dir_convention(self, tmp_path: Path) -> None:
        from maieutica.output.paths import silver_dir

        s = silver_dir("2026-1", "anatomy", data_root=tmp_path)
        assert s == tmp_path / "silver" / "maieutica" / "2026-1-anatomy"

    def test_gold_dir_convention(self, tmp_path: Path) -> None:
        from maieutica.output.paths import gold_dir

        g = gold_dir("2026-1", "anatomy", data_root=tmp_path)
        assert g == tmp_path / "gold" / "maieutica" / "2026-1-anatomy"

    def test_paths_follow_module_convention(self, tmp_path: Path) -> None:
        """All three tiers use /maieutica/ subdirectory."""
        from maieutica.output.paths import bronze_dir, gold_dir, silver_dir

        for fn in (bronze_dir, silver_dir, gold_dir):
            p = fn("2026-1", "anatomy", data_root=tmp_path)
            assert "maieutica" in p.parts


# ---------------------------------------------------------------------------
# run_id computation
# ---------------------------------------------------------------------------


class TestRunId:
    def test_run_id_deterministic_same_inputs(self) -> None:
        """Same bytes always produces the same run_id."""
        from maieutica.output.paths import compute_run_id

        spec = b"spec content"
        curriculum = b"curriculum content"
        chapter = b"chapter text"

        r1 = compute_run_id(spec, curriculum, chapter)
        r2 = compute_run_id(spec, curriculum, chapter)
        assert r1 == r2

    def test_run_id_differs_when_spec_changes(self) -> None:
        """Changing generation_spec bytes changes the run_id."""
        from maieutica.output.paths import compute_run_id

        curriculum = b"curriculum"
        chapter = b"chapter"
        r1 = compute_run_id(b"spec-v1", curriculum, chapter)
        r2 = compute_run_id(b"spec-v2", curriculum, chapter)
        assert r1 != r2

    def test_run_id_differs_when_curriculum_changes(self) -> None:
        """Changing curriculum_map bytes changes the run_id."""
        from maieutica.output.paths import compute_run_id

        spec = b"spec"
        chapter = b"chapter"
        r1 = compute_run_id(spec, b"curr-v1", chapter)
        r2 = compute_run_id(spec, b"curr-v2", chapter)
        assert r1 != r2

    def test_run_id_differs_when_chapter_changes(self) -> None:
        """Changing chapter_txt bytes changes the run_id."""
        from maieutica.output.paths import compute_run_id

        spec = b"spec"
        curriculum = b"curriculum"
        r1 = compute_run_id(spec, curriculum, b"ch-v1")
        r2 = compute_run_id(spec, curriculum, b"ch-v2")
        assert r1 != r2

    def test_run_id_length_is_16(self) -> None:
        """run_id is the first 16 hex chars of SHA-256."""
        from maieutica.output.paths import compute_run_id

        r = compute_run_id(b"a", b"b", b"c")
        assert len(r) == 16
        # Must be hex chars
        int(r, 16)

    def test_run_id_matches_expected_sha256_prefix(self) -> None:
        """run_id = sha256(spec + curriculum + chapter)[:16]."""
        from maieutica.output.paths import compute_run_id

        spec = b"spec"
        curriculum = b"curriculum"
        chapter = b"chapter"
        expected = hashlib.sha256(spec + curriculum + chapter).hexdigest()[:16]
        assert compute_run_id(spec, curriculum, chapter) == expected

    def test_run_id_empty_inputs_raises(self) -> None:
        """Any empty input bytes raises ValueError (fail-fast)."""
        from maieutica.output.paths import compute_run_id

        with pytest.raises(ValueError):
            compute_run_id(b"", b"curr", b"ch")
        with pytest.raises(ValueError):
            compute_run_id(b"spec", b"", b"ch")
        with pytest.raises(ValueError):
            compute_run_id(b"spec", b"curr", b"")


# ---------------------------------------------------------------------------
# atomic_write
# ---------------------------------------------------------------------------


class TestAtomicWrite:
    def test_successful_write_produces_file(self, tmp_path: Path) -> None:
        from maieutica.output.paths import atomic_write

        target = tmp_path / "sub" / "out.txt"
        target.parent.mkdir(parents=True)

        def writer(p: Path) -> None:
            p.write_text("hello", encoding="utf-8")

        atomic_write(target, writer)
        assert target.read_text(encoding="utf-8") == "hello"

    def test_no_partial_file_on_failure(self, tmp_path: Path) -> None:
        """If write_fn raises, the target file must NOT exist afterward."""
        from maieutica.output.paths import atomic_write

        target = tmp_path / "out.txt"

        def bad_writer(p: Path) -> None:
            p.write_text("partial content", encoding="utf-8")
            raise RuntimeError("simulated failure")

        with pytest.raises(RuntimeError, match="simulated failure"):
            atomic_write(target, bad_writer)

        assert not target.exists()
        # No orphaned temp file should remain
        assert not list(tmp_path.glob(".tmp_*"))

    def test_atomic_write_replaces_existing_file(self, tmp_path: Path) -> None:
        """Existing file is atomically replaced."""
        from maieutica.output.paths import atomic_write

        target = tmp_path / "out.txt"
        target.write_text("old", encoding="utf-8")

        def writer(p: Path) -> None:
            p.write_text("new", encoding="utf-8")

        atomic_write(target, writer)
        assert target.read_text(encoding="utf-8") == "new"

    def test_temp_file_in_same_directory(self, tmp_path: Path) -> None:
        """Temp file is placed in the same directory as target (same-device rename)."""
        from maieutica.output.paths import atomic_write

        target = tmp_path / "out.txt"
        seen_parent: list[Path] = []

        def writer(p: Path) -> None:
            seen_parent.append(p.parent)
            p.write_text("x", encoding="utf-8")

        atomic_write(target, writer)
        assert seen_parent[0] == tmp_path


# ---------------------------------------------------------------------------
# Output separation — run-versioned Gold paths
# ---------------------------------------------------------------------------


class TestOutputSeparation:
    def test_run_gold_path_differs_per_run_id(self, tmp_path: Path) -> None:
        """Two different run_ids produce distinct paths."""
        from maieutica.output.paths import run_gold_dir

        p1 = run_gold_dir("2026-1", "anatomy", run_id="abc123", data_root=tmp_path)
        p2 = run_gold_dir("2026-1", "anatomy", run_id="def456", data_root=tmp_path)
        assert p1 != p2

    def test_run_gold_path_is_under_gold_dir(self, tmp_path: Path) -> None:
        """Run-versioned path is a subdirectory of the canonical Gold dir."""
        from maieutica.output.paths import gold_dir, run_gold_dir

        gold = gold_dir("2026-1", "anatomy", data_root=tmp_path)
        run_path = run_gold_dir(
            "2026-1", "anatomy", run_id="abc123", data_root=tmp_path
        )
        assert str(run_path).startswith(str(gold))

    def test_same_run_id_produces_same_path(self, tmp_path: Path) -> None:
        """Deterministic: same run_id always yields the same path."""
        from maieutica.output.paths import run_gold_dir

        p1 = run_gold_dir("2026-1", "anatomy", run_id="stable", data_root=tmp_path)
        p2 = run_gold_dir("2026-1", "anatomy", run_id="stable", data_root=tmp_path)
        assert p1 == p2

    def test_run_gold_does_not_equal_base_gold(self, tmp_path: Path) -> None:
        """Run-versioned path != base Gold dir (a re-run never clobbers base)."""
        from maieutica.output.paths import gold_dir, run_gold_dir

        gold = gold_dir("2026-1", "anatomy", data_root=tmp_path)
        run_path = run_gold_dir(
            "2026-1", "anatomy", run_id="abc", data_root=tmp_path
        )
        assert run_path != gold
