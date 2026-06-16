"""Property tests for archive_previous_run (T110).

Hypothesis-driven: any nested file/directory contents under direct_path must
survive round-trip through _archive/{TS}/ — file count + names + content
preserved.
"""

from __future__ import annotations

from pathlib import Path

from hypothesis import given, settings
from hypothesis import strategies as st

_FILENAME_STRAT = st.text(alphabet="abcdefghijklmnop0123456789_-", min_size=1, max_size=12).map(
    lambda s: f"{s}.bin"
)


@given(
    files=st.lists(
        st.tuples(_FILENAME_STRAT, st.binary(min_size=1, max_size=64)),
        min_size=1,
        max_size=8,
        unique_by=lambda pair: pair[0],
    )
)
@settings(max_examples=15, deadline=None)
def test_archive_round_trip_preserves_files(
    tmp_path_factory, files: list[tuple[str, bytes]]
) -> None:  # type: ignore[no-untyped-def]
    """Whatever files exist in direct_path land verbatim in _archive/{TS}/."""
    from needs_map.archive.mover import archive_previous_run

    direct = tmp_path_factory.mktemp("direct")
    for name, blob in files:
        (direct / name).write_bytes(blob)

    archive_label = archive_previous_run(direct)
    assert archive_label is not None

    archive_dir = direct / archive_label
    assert archive_dir.is_dir()
    for name, blob in files:
        target = archive_dir / name
        assert target.is_file()
        assert target.read_bytes() == blob

    # direct path has only _archive/ now
    remaining = [p.name for p in direct.iterdir() if p.name != "_archive"]
    assert remaining == []


def test_archive_empty_dir_returns_none(tmp_path: Path) -> None:
    from needs_map.archive.mover import archive_previous_run

    direct = tmp_path / "empty"
    direct.mkdir()
    assert archive_previous_run(direct) is None


def test_archive_preserves_existing_archive_subdir(tmp_path: Path) -> None:
    """Pre-existing _archive/{TS}/ from prior run is not re-archived."""
    from needs_map.archive.mover import archive_previous_run

    direct = tmp_path / "out"
    direct.mkdir()
    pre_existing = direct / "_archive" / "2024-01-01T00-00-00-000000Z" / "old.bin"
    pre_existing.parent.mkdir(parents=True)
    pre_existing.write_bytes(b"legacy")
    (direct / "v_new.bin").write_bytes(b"new")

    label = archive_previous_run(direct)
    assert label is not None
    assert pre_existing.read_bytes() == b"legacy"
    assert (direct / label / "v_new.bin").read_bytes() == b"new"
