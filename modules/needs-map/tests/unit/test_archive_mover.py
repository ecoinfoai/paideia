"""Tests for archive_previous_run atomicity (T027, FR-002, adversary H-7)."""

from __future__ import annotations

import os
import stat
from pathlib import Path

import pytest
from needs_map.archive.mover import ArchivalError, archive_previous_run


def _seed(direct: Path, names: list[str]) -> None:
    direct.mkdir(parents=True, exist_ok=True)
    for n in names:
        (direct / n).write_text(f"content of {n}\n", encoding="utf-8")


def test_first_run_no_archive(tmp_path: Path) -> None:
    direct = tmp_path / "data" / "silver" / "needs-map" / "2026-1-anatomy"
    direct.mkdir(parents=True)  # exists but empty
    result = archive_previous_run(direct)
    assert result is None
    assert not (direct / "_archive").exists()


def test_missing_direct_path_returns_none(tmp_path: Path) -> None:
    direct = tmp_path / "never_exists"
    assert archive_previous_run(direct) is None


def test_second_run_moves_contents_into_timestamp_dir(tmp_path: Path) -> None:
    direct = tmp_path / "out"
    _seed(direct, ["a.parquet", "manifest.json"])

    label = archive_previous_run(direct)
    assert label is not None
    assert label.startswith("_archive/")

    archive_subdir = direct / label
    assert archive_subdir.is_dir()
    assert (archive_subdir / "a.parquet").read_text(encoding="utf-8") == "content of a.parquet\n"
    assert (archive_subdir / "manifest.json").read_text(
        encoding="utf-8"
    ) == "content of manifest.json\n"

    # direct path now contains only _archive (entries moved)
    remaining = [p.name for p in direct.iterdir() if p.name != "_archive"]
    assert remaining == []


def test_third_run_creates_second_archive_entry(tmp_path: Path) -> None:
    direct = tmp_path / "out"
    _seed(direct, ["v1.parquet"])
    first = archive_previous_run(direct)
    assert first is not None

    # populate again
    _seed(direct, ["v2.parquet"])
    second = archive_previous_run(direct)
    assert second is not None
    assert second != first

    archive_root = direct / "_archive"
    archives = sorted(p.name for p in archive_root.iterdir())
    # _archive itself contains TWO timestamp dirs and nothing else
    assert len(archives) == 2
    assert (archive_root / archives[0] / "v1.parquet").is_file()
    assert (archive_root / archives[1] / "v2.parquet").is_file()


def test_direct_path_is_file_raises(tmp_path: Path) -> None:
    direct = tmp_path / "f.parquet"
    direct.write_text("not a directory")
    with pytest.raises(ArchivalError, match="not a directory"):
        archive_previous_run(direct)


def test_type_error_on_non_path_input() -> None:
    with pytest.raises(TypeError):
        archive_previous_run("string-not-path")  # type: ignore[arg-type]


@pytest.mark.skipif(os.geteuid() == 0, reason="root bypasses chmod 0o500 protection")
def test_readonly_target_raises_archival_error(tmp_path: Path) -> None:
    """Closure of adversary H-7 + P-3: permission denied during mkdir → ArchivalError, not silent.

    We make the direct path itself read-only so creating ``_archive/`` underneath fails.
    """
    direct = tmp_path / "out"
    _seed(direct, ["v1.parquet"])
    direct.chmod(stat.S_IRUSR | stat.S_IXUSR)  # 0o500: no write
    try:
        with pytest.raises(ArchivalError):
            archive_previous_run(direct)
    finally:
        direct.chmod(0o700)  # restore so tmp_path cleanup succeeds


def test_existing_archive_dir_is_preserved(tmp_path: Path) -> None:
    """A pre-existing _archive/ from a prior run does NOT get re-archived."""
    direct = tmp_path / "out"
    direct.mkdir()
    pre_existing = direct / "_archive" / "2024-01-01T00-00-00Z" / "old.parquet"
    pre_existing.parent.mkdir(parents=True)
    pre_existing.write_text("legacy")

    _seed(direct, ["v_new.parquet"])  # one new entry alongside _archive

    label = archive_previous_run(direct)
    assert label is not None

    # pre-existing archive subdir untouched
    assert pre_existing.read_text() == "legacy"
    # new entry moved into a NEW timestamp subdir
    assert (direct / label / "v_new.parquet").is_file()
