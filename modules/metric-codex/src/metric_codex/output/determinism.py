"""T014 — Determinism utilities for metric-codex Gold-layer outputs.

metric-codex Gold is markdown/yaml only (no xlsx).  This module therefore
provides parquet, yaml, and atomic-write helpers but deliberately omits any
xlsx / dcterms helpers present in the examen equivalents.

Provides:
- ``parquet_write_options() -> dict`` — ``use_dictionary=False``,
  ``write_statistics=False``, ``compression='snappy'`` (byte-identical parquet).
- ``dump_yaml(obj) -> str`` — sort_keys, allow_unicode, normalised newlines,
  SafeDumper.
- ``atomic_write(path, write_fn)`` — temp→rename atomicity; on exception
  cleans up temp and re-raises (no partial file, constitution V).
"""

from __future__ import annotations

import contextlib
import os
import tempfile
from collections.abc import Callable
from pathlib import Path
from typing import Any

import yaml

# ---------------------------------------------------------------------------
# parquet determinism
# ---------------------------------------------------------------------------


def parquet_write_options() -> dict[str, Any]:
    """Return PyArrow parquet write options for byte-identical output.

    Returns::

        {
            "use_dictionary": False,    # eliminates dictionary encoding variance
            "write_statistics": False,  # strips row-group min/max metadata
            "compression": "snappy",    # deterministic compressor
        }

    Pass as ``**parquet_write_options()`` to ``pyarrow.parquet.write_table``.

    Returns:
        Dict of keyword arguments suitable for ``pyarrow.parquet.write_table``.
    """
    return {
        "use_dictionary": False,
        "write_statistics": False,
        "compression": "snappy",
    }


# ---------------------------------------------------------------------------
# yaml determinism
# ---------------------------------------------------------------------------


def dump_yaml(obj: Any) -> str:  # noqa: ANN401
    """Dump ``obj`` to a deterministic YAML string.

    Properties:
    - ``sort_keys=True`` — alphabetical key order regardless of insertion order.
    - ``allow_unicode=True`` — Korean/Unicode characters written as-is, not
      escaped (``\\uXXXX``).
    - ``default_flow_style=False`` — block-style output (readable).
    - SafeDumper — no Python-specific tags; output is portable YAML 1.1.
    - Output always ends with exactly one newline.
    - Two calls with equal ``obj`` always return the identical string.

    Args:
        obj: Any PyYAML-serialisable Python object.

    Returns:
        Deterministic YAML string ending with exactly one newline.
    """
    result: str = yaml.dump(
        obj,
        allow_unicode=True,
        sort_keys=True,
        default_flow_style=False,
        Dumper=yaml.SafeDumper,
    )
    # yaml.dump already appends a newline for non-empty docs; normalise
    # to exactly one trailing newline for both empty and non-empty cases.
    return result if result.endswith("\n") else result + "\n"


# ---------------------------------------------------------------------------
# atomic write
# ---------------------------------------------------------------------------


def atomic_write(path: Path, write_fn: Callable[[Path], None]) -> None:
    """Write a file atomically using a temp-file then ``os.replace``.

    ``write_fn`` is called with a temporary ``Path`` in the same directory
    as ``path``.  On success the temp file is renamed to ``path``
    (``os.replace`` is atomic on POSIX).  On any exception the temp file
    is cleaned up and the exception is re-raised — ``path`` is left
    untouched (constitution V: no partial output).

    The temp file is placed in the same directory as ``path`` to guarantee
    the rename is a same-device operation (required for POSIX atomicity).

    Args:
        path: Final destination path.  The parent directory must exist.
        write_fn: Callable that receives the temp ``Path`` and writes to it.

    Raises:
        Exception: Any exception raised by ``write_fn`` (after cleanup).
    """
    parent = path.parent
    tmp_fd, tmp_name = tempfile.mkstemp(dir=parent, prefix=".tmp_")
    tmp_path = Path(tmp_name)
    # Close the fd immediately — write_fn opens the file itself.
    os.close(tmp_fd)
    try:
        write_fn(tmp_path)
        os.replace(tmp_path, path)  # POSIX-atomic rename
    except Exception:
        with contextlib.suppress(OSError):
            tmp_path.unlink(missing_ok=True)
        raise


__all__ = ["dump_yaml", "parquet_write_options", "atomic_write"]
