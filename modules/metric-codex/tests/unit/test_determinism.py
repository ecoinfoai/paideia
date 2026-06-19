"""T013 — Unit tests for metric_codex.output.determinism.

Tests (RED first, per TDD mandate):
- parquet_write_options: returns the expected dict.
- parquet byte-identical roundtrip: two writes of the same DataFrame yield
  byte-identical on-disk files AND round-trip back to an equal DataFrame.
- dump_yaml: sorted keys, stable across two calls, Unicode preserved, exactly
  one trailing newline.
- atomic_write: success path leaves a valid file at the target path; failure
  path leaves no partial file and re-raises the exception.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
import pytest

# ---------------------------------------------------------------------------
# parquet_write_options
# ---------------------------------------------------------------------------


def test_parquet_write_options_keys() -> None:
    """parquet_write_options returns use_dictionary, write_statistics, compression."""
    from metric_codex.output.determinism import parquet_write_options

    opts: dict[str, Any] = parquet_write_options()
    assert opts["use_dictionary"] is False
    assert opts["write_statistics"] is False
    assert opts["compression"] == "snappy"


def test_parquet_write_options_immutable_between_calls() -> None:
    """Two calls return equal dicts; mutating one must not affect the next."""
    from metric_codex.output.determinism import parquet_write_options

    a = parquet_write_options()
    b = parquet_write_options()
    assert a == b

    # Mutate the first dict — a fresh call must be unaffected (no shared state).
    a["use_dictionary"] = True
    c = parquet_write_options()
    assert c["use_dictionary"] is False


# ---------------------------------------------------------------------------
# Byte-identical parquet roundtrip
# ---------------------------------------------------------------------------


def _sample_df() -> pd.DataFrame:
    """Return a small DataFrame with Korean string data for roundtrip testing."""
    return pd.DataFrame(
        {
            "student_id": ["S001", "S002", "S003"],
            "name": ["홍길동", "이순신", "김철수"],
            "score": [85.0, 92.5, 78.0],
            "passed": [True, True, False],
        }
    )


def test_parquet_byte_identical_roundtrip(tmp_path: Path) -> None:
    """Two writes of the same DataFrame yield byte-identical parquet files."""
    from metric_codex.output.determinism import parquet_write_options

    df = _sample_df()
    table = pa.Table.from_pandas(df, preserve_index=False)
    opts = parquet_write_options()

    path_a = tmp_path / "a.parquet"
    path_b = tmp_path / "b.parquet"

    pq.write_table(table, path_a, **opts)
    pq.write_table(table, path_b, **opts)

    assert path_a.read_bytes() == path_b.read_bytes(), (
        "Two parquet writes of the same DataFrame must be byte-identical."
    )


def test_parquet_roundtrip_data_equal(tmp_path: Path) -> None:
    """DataFrame written and read back equals the original."""
    from metric_codex.output.determinism import parquet_write_options

    df = _sample_df()
    table = pa.Table.from_pandas(df, preserve_index=False)
    opts = parquet_write_options()

    path = tmp_path / "roundtrip.parquet"
    pq.write_table(table, path, **opts)

    read_back = pq.read_table(path).to_pandas()
    pd.testing.assert_frame_equal(df, read_back, check_like=False)


# ---------------------------------------------------------------------------
# dump_yaml
# ---------------------------------------------------------------------------


def test_dump_yaml_sorted_keys() -> None:
    """dump_yaml serialises dict keys in alphabetical order."""
    from metric_codex.output.determinism import dump_yaml

    result = dump_yaml({"z": 1, "a": 2, "m": 3})
    lines = [ln for ln in result.splitlines() if ":" in ln]
    keys = [ln.split(":")[0].strip() for ln in lines]
    assert keys == sorted(keys), f"Keys not sorted: {keys}"


def test_dump_yaml_stable() -> None:
    """Two dump_yaml calls with equal input return identical strings."""
    from metric_codex.output.determinism import dump_yaml

    obj = {"semester": "2026-1", "course": "anatomy", "count": 42}
    assert dump_yaml(obj) == dump_yaml(obj)


def test_dump_yaml_unicode_preserved() -> None:
    """Korean characters are written as-is, not escaped."""
    from metric_codex.output.determinism import dump_yaml

    result = dump_yaml({"이름": "홍길동"})
    assert "홍길동" in result
    assert "\\u" not in result


def test_dump_yaml_single_trailing_newline() -> None:
    """Output ends with exactly one newline."""
    from metric_codex.output.determinism import dump_yaml

    result = dump_yaml({"key": "value"})
    assert result.endswith("\n")
    assert not result.endswith("\n\n")


def test_dump_yaml_empty_dict() -> None:
    """dump_yaml handles empty dict without error; output ends with newline."""
    from metric_codex.output.determinism import dump_yaml

    result = dump_yaml({})
    assert isinstance(result, str)
    assert result.endswith("\n")


# ---------------------------------------------------------------------------
# atomic_write
# ---------------------------------------------------------------------------


def test_atomic_write_success(tmp_path: Path) -> None:
    """atomic_write creates the target file with the expected content."""
    from metric_codex.output.determinism import atomic_write

    target = tmp_path / "output.txt"

    def _write(p: Path) -> None:
        p.write_text("hello metric-codex", encoding="utf-8")

    atomic_write(target, _write)

    assert target.exists()
    assert target.read_text(encoding="utf-8") == "hello metric-codex"


def test_atomic_write_no_partial_file_on_failure(tmp_path: Path) -> None:
    """atomic_write leaves no file at target path when write_fn raises."""
    from metric_codex.output.determinism import atomic_write

    target = tmp_path / "output.txt"

    def _failing_write(p: Path) -> None:
        p.write_text("partial content", encoding="utf-8")
        raise RuntimeError("simulated write failure")

    with pytest.raises(RuntimeError, match="simulated write failure"):
        atomic_write(target, _failing_write)

    # Target must not exist (no partial file).
    assert not target.exists()
    # No temp files left behind in the directory.
    leftover = [f for f in tmp_path.iterdir() if f.name.startswith(".tmp_")]
    assert leftover == [], f"Temp files leaked: {leftover}"


def test_atomic_write_reraises_exception(tmp_path: Path) -> None:
    """atomic_write re-raises the exception from write_fn."""
    from metric_codex.output.determinism import atomic_write

    target = tmp_path / "output.txt"

    class _CustomError(Exception):
        pass

    def _raise(p: Path) -> None:
        raise _CustomError("custom")

    with pytest.raises(_CustomError):
        atomic_write(target, _raise)


def test_atomic_write_does_not_clobber_existing_on_failure(tmp_path: Path) -> None:
    """When write_fn fails, an existing target file is not modified."""
    from metric_codex.output.determinism import atomic_write

    target = tmp_path / "output.txt"
    target.write_text("original content", encoding="utf-8")

    def _failing_write(p: Path) -> None:
        raise ValueError("fail before writing")

    with pytest.raises(ValueError):
        atomic_write(target, _failing_write)

    assert target.read_text(encoding="utf-8") == "original content"
