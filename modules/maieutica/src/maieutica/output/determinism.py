"""T015 — Determinism utilities for Gold-layer outputs.

Provides byte-identical output guarantees for:
- ``finalize_xlsx(path, when)`` — strips openpyxl's runtime-stamped
  ``<dcterms:modified>`` and ``<dcterms:created>`` by repacking the xlsx zip
  with pinned values and fixed ZipInfo date_time.  Ported from
  ``modules/examen/src/examen/output/determinism.py``.
- ``dump_yaml(obj) -> str`` — sort_keys, allow_unicode=True, normalised newlines.
  Ported from examen.
- ``gate_xls_deterministic(writer, work_dir)`` — NEW (R1): writes twice via the
  supplied callable and asserts byte-identical; used by the quiz .xls writer test
  (T032).  Cleans up temp files on both success and failure.

None of these functions contain business logic or LLM calls.

xlsx pinning technique (identical to examen + immersio)
-------------------------------------------------------
1. Read all zip entries into memory.
2. Replace ``docProps/core.xml``'s ``<dcterms:modified>`` and
   ``<dcterms:created>`` text with the pinned ISO8601 UTC string.
3. Repack the archive with ``ZipInfo(date_time=(1980,1,1,0,0,0))`` for every
   entry (openpyxl's own pin value) and a fixed compresslevel.
4. Overwrite ``path`` with the new bytes.

This avoids monkey-patching openpyxl's internal datetime module, which bleeds
across pytest fixtures.
"""

from __future__ import annotations

import contextlib
import datetime
import io
import os as _os
import re
import tempfile
import zipfile
from collections.abc import Callable
from pathlib import Path
from typing import Any

import yaml

# ---------------------------------------------------------------------------
# xlsx determinism
# ---------------------------------------------------------------------------

_CORE_XML_PATH = "docProps/core.xml"
_MODIFIED_RE = re.compile(
    r"(<dcterms:modified[^>]*>)([^<]+)(</dcterms:modified>)",
    re.DOTALL,
)
# openpyxl stamps <dcterms:created> with datetime.now() too — pin both so that
# two runs straddling a wall-clock second boundary produce identical bytes.
_CREATED_RE = re.compile(
    r"(<dcterms:created[^>]*>)([^<]+)(</dcterms:created>)",
    re.DOTALL,
)
# openpyxl uses (1980,1,1,0,0,0) for all ZipInfo date_times; match that.
_FIXED_ZIP_DATE = (1980, 1, 1, 0, 0, 0)
# Fixed compression level so zlib output is platform/version invariant.
_FIXED_COMPRESSLEVEL = 6


def finalize_xlsx(path: Path, when: datetime.datetime) -> None:
    """Repack ``path`` with pinned ``<dcterms:modified>`` and ``<dcterms:created>``.

    openpyxl's ``save()`` stamps BOTH ``<dcterms:modified>`` and
    ``<dcterms:created>`` with ``datetime.now()``, causing byte-level
    non-determinism across runs.  This function rewrites both values to
    ``when`` formatted as ISO8601 UTC after ``save()`` has landed.

    All zip entries are repacked with ``ZipInfo(date_time=(1980,1,1,0,0,0))``
    and a fixed ``compresslevel`` so the archive is byte-identical for
    identical inputs regardless of host filesystem mtime precision or platform
    zlib default level.

    Technique mirrors ``rewrite_modified_in_zip`` in
    ``modules/immersio/src/immersio/report/xlsx_writer.py`` and is identical
    to ``modules/examen/src/examen/output/determinism.py``.

    Args:
        path: Path to the xlsx file to finalise (modified in-place).
        when: The datetime to embed as ``<dcterms:modified>`` and
            ``<dcterms:created>`` (treated as UTC).
    """
    iso = when.strftime("%Y-%m-%dT%H:%M:%SZ")

    with zipfile.ZipFile(path, "r") as src:
        members: list[tuple[str, bytes, int]] = []
        for info in src.infolist():
            data = src.read(info.filename)
            if info.filename == _CORE_XML_PATH:
                text = data.decode("utf-8")
                text = _MODIFIED_RE.sub(rf"\g<1>{iso}\g<3>", text, count=1)
                text = _CREATED_RE.sub(rf"\g<1>{iso}\g<3>", text, count=1)
                data = text.encode("utf-8")
            members.append((info.filename, data, info.compress_type))

    buf = io.BytesIO()
    with zipfile.ZipFile(
        buf, "w", zipfile.ZIP_DEFLATED, compresslevel=_FIXED_COMPRESSLEVEL
    ) as dst:
        for name, data, compress_type in members:
            zi = zipfile.ZipInfo(filename=name, date_time=_FIXED_ZIP_DATE)
            zi.compress_type = compress_type or zipfile.ZIP_DEFLATED
            dst.writestr(zi, data)

    path.write_bytes(buf.getvalue())


# ---------------------------------------------------------------------------
# yaml determinism
# ---------------------------------------------------------------------------


def dump_yaml(obj: Any) -> str:  # noqa: ANN401
    """Dump ``obj`` to a deterministic YAML string.

    Properties:
    - ``sort_keys=True`` — alphabetical key order regardless of insertion order.
    - ``allow_unicode=True`` — Korean/Unicode characters written as-is, not
      escaped (``\\uXXXX``).
    - Output always ends with exactly one newline.
    - Two calls with equal ``obj`` always return the identical string.

    Args:
        obj: Any PyYAML-serialisable Python object.

    Returns:
        Deterministic YAML string.
    """
    result: str = yaml.dump(
        obj,
        allow_unicode=True,
        sort_keys=True,
        default_flow_style=False,
        Dumper=yaml.SafeDumper,
    )
    return result if result.endswith("\n") else result + "\n"


# ---------------------------------------------------------------------------
# .xls byte-determinism gate (NEW — maieutica-specific, R1)
# ---------------------------------------------------------------------------


def gate_xls_deterministic(
    writer: Callable[[Path], None],
    *,
    work_dir: Path | None = None,
) -> None:
    """Assert that ``writer`` produces byte-identical ``.xls`` output on two runs.

    Calls ``writer(path)`` twice with distinct temporary paths, then asserts the
    two resulting files are byte-identical.  Both temp files are deleted
    regardless of outcome (success or failure).

    This gate is intended to be run once during test/CI as an invariant check
    for the quiz ``.xls`` writer (T032, research R1).  It is NOT a production
    hot-path function.

    Args:
        writer: A callable ``(path: Path) -> None`` that writes a ``.xls`` file
            to the given path.  Must be purely deterministic (same output for
            same logical inputs on every call).
        work_dir: Directory for temp files.  Uses ``tempfile.gettempdir()`` when
            ``None``.

    Raises:
        AssertionError: If the two writes produce different bytes, with a message
            reporting the file sizes of the two outputs for diagnosis.
    """
    base = work_dir if work_dir is not None else Path(tempfile.gettempdir())

    tmp1_fd, tmp1_name = tempfile.mkstemp(dir=base, suffix=".xls", prefix="_gate_")
    tmp2_fd, tmp2_name = tempfile.mkstemp(dir=base, suffix=".xls", prefix="_gate_")
    _os.close(tmp1_fd)
    _os.close(tmp2_fd)
    path1, path2 = Path(tmp1_name), Path(tmp2_name)
    try:
        writer(path1)
        writer(path2)
        bytes1 = path1.read_bytes()
        bytes2 = path2.read_bytes()
        if bytes1 != bytes2:
            raise AssertionError(
                f".xls writer is non-deterministic: "
                f"run1={len(bytes1)} bytes, run2={len(bytes2)} bytes differ"
            )
    finally:
        with contextlib.suppress(OSError):
            path1.unlink(missing_ok=True)
        with contextlib.suppress(OSError):
            path2.unlink(missing_ok=True)


__all__ = ["finalize_xlsx", "dump_yaml", "gate_xls_deterministic"]
