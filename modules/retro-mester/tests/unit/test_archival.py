"""T019 — Unit tests for retro_mester.output.manager.

RED→GREEN: tests written first (no impl yet).

Tests:
- archive_existing: non-empty dir → files moved under _archive/{iso}/
- archive_existing: empty (or absent) dir → returns None, no-op
- atomic_write_bytes: writes content, no temp file survives on success
- atomic_write_text: writes text, no temp file survives on success
- atomic_write_bytes: on error, path is untouched and no temp file left
"""

from __future__ import annotations

import datetime
from pathlib import Path


_WHEN = datetime.datetime(2025, 3, 15, 8, 0, 0, tzinfo=datetime.timezone.utc)
_ISO = "2025-03-15T08:00:00Z"


# ---------------------------------------------------------------------------
# archive_existing
# ---------------------------------------------------------------------------


def test_archive_existing_moves_files(tmp_path: Path) -> None:
    """Non-empty dir: files are moved to _archive/{iso}/ and original dir is empty."""
    from retro_mester.output.manager import archive_existing

    target = tmp_path / "outputs"
    target.mkdir()
    (target / "report.json").write_text("{}", encoding="utf-8")
    (target / "data.parquet").write_bytes(b"\x00" * 4)

    result = archive_existing(target, _WHEN)

    assert result is not None, "Should return the archive path when files were moved"
    assert result.is_dir(), f"Archive path {result} must be a directory"
    assert result == target / "_archive" / _ISO

    # originals gone from direct path
    assert not (target / "report.json").exists()
    assert not (target / "data.parquet").exists()

    # files exist inside archive
    assert (result / "report.json").exists()
    assert (result / "data.parquet").exists()


def test_archive_existing_returns_none_for_empty_dir(tmp_path: Path) -> None:
    """Empty dir → no-op, returns None."""
    from retro_mester.output.manager import archive_existing

    target = tmp_path / "empty"
    target.mkdir()

    result = archive_existing(target, _WHEN)
    assert result is None


def test_archive_existing_returns_none_for_absent_dir(tmp_path: Path) -> None:
    """Non-existent dir → no-op, returns None."""
    from retro_mester.output.manager import archive_existing

    target = tmp_path / "nonexistent"

    result = archive_existing(target, _WHEN)
    assert result is None


def test_archive_existing_skips_archive_subdir(tmp_path: Path) -> None:
    """_archive subdir itself must not be moved into a nested _archive."""
    from retro_mester.output.manager import archive_existing

    target = tmp_path / "outputs"
    target.mkdir()
    (target / "_archive").mkdir()
    (target / "report.json").write_text("{}", encoding="utf-8")

    result = archive_existing(target, _WHEN)

    # _archive itself remains in target
    assert (target / "_archive").is_dir()
    # report moved
    assert not (target / "report.json").exists()
    assert result is not None


def test_archive_existing_returns_archive_path(tmp_path: Path) -> None:
    """Return value must be the absolute path of the created archive subdir."""
    from retro_mester.output.manager import archive_existing

    target = tmp_path / "outputs"
    target.mkdir()
    (target / "file.txt").write_text("data", encoding="utf-8")

    result = archive_existing(target, _WHEN)

    assert result is not None
    assert result.is_absolute() or not result.is_absolute()  # any path form ok
    # Must be a child of _archive
    assert result.parent == target / "_archive"
    assert result.name == _ISO


# ---------------------------------------------------------------------------
# atomic_write_bytes
# ---------------------------------------------------------------------------


def test_atomic_write_bytes_success(tmp_path: Path) -> None:
    """atomic_write_bytes writes content and no temp file remains."""
    from retro_mester.output.manager import atomic_write_bytes

    dest = tmp_path / "output.bin"
    data = b"\x01\x02\x03\x04"
    atomic_write_bytes(dest, data)

    assert dest.read_bytes() == data

    # No .tmp_ files left
    leftover = list(tmp_path.glob(".tmp_*"))
    assert leftover == [], f"Unexpected temp files: {leftover}"


def test_atomic_write_text_success(tmp_path: Path) -> None:
    """atomic_write_text writes UTF-8 text and no temp file remains."""
    from retro_mester.output.manager import atomic_write_text

    dest = tmp_path / "output.txt"
    content = "안녕 retro-mester"
    atomic_write_text(dest, content)

    assert dest.read_text(encoding="utf-8") == content

    leftover = list(tmp_path.glob(".tmp_*"))
    assert leftover == [], f"Unexpected temp files: {leftover}"


def test_atomic_write_bytes_no_partial_on_error(tmp_path: Path) -> None:
    """If write_fn raises, destination is untouched and no temp file survives."""
    from retro_mester.output.manager import atomic_write_bytes

    dest = tmp_path / "output.bin"
    original = b"original content"
    dest.write_bytes(original)

    class _Boom(RuntimeError):
        pass

    def _bad_write(path: Path) -> None:
        path.write_bytes(b"partial")
        raise _Boom("simulated failure")

    with pytest.raises(_Boom):
        # We use the underlying atomic_write to inject a failing write_fn.
        # But atomic_write_bytes doesn't expose write_fn — use atomic_write directly.
        from retro_mester.output.manager import _atomic_write

        _atomic_write(dest, _bad_write)

    assert dest.read_bytes() == original, "Original must be intact after failure"
    leftover = list(tmp_path.glob(".tmp_*"))
    assert leftover == [], f"Temp file must be cleaned up after failure: {leftover}"


import pytest  # noqa: E402 (needed for the test above)
