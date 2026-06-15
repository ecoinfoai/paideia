"""T017 — Determinism utilities for Gold-layer outputs.

Provides byte-identical output guarantees for:
- ``finalize_xlsx(path, when)`` — strips openpyxl's runtime-stamped
  ``<dcterms:modified>`` and ``<dcterms:created>`` by repacking the xlsx zip
  with pinned values and fixed ZipInfo date_time.
- ``dump_yaml(obj) -> str`` — sort_keys, allow_unicode, normalised newlines.
- ``parquet_write_options() -> dict`` — ``use_dictionary=False``,
  ``write_statistics=False``, ``compression='snappy'``.

Adapted from ``modules/examen/src/examen/output/determinism.py`` (T014).
Both ``<dcterms:modified>`` AND ``<dcterms:created>`` are pinned — the
examen version corrected the immersio bug where only ``modified`` was pinned,
causing byte-level divergence when two runs crossed a wall-clock second boundary.
"""

from __future__ import annotations

import datetime
import io
import re
import zipfile
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
# openpyxl stamps <dcterms:created> with datetime.now() too.
# Pin both so builds separated by a wall-clock second boundary are still identical.
_CREATED_RE = re.compile(
    r"(<dcterms:created[^>]*>)([^<]+)(</dcterms:created>)",
    re.DOTALL,
)
# openpyxl's own internal pin value for ZipInfo date_time
_FIXED_ZIP_DATE = (1980, 1, 1, 0, 0, 0)
# Fix zlib compression level — platform/version defaults can differ
_FIXED_COMPRESSLEVEL = 6


def finalize_xlsx(path: Path, when: datetime.datetime) -> None:
    """Repack ``path`` with pinned ``<dcterms:modified>`` and ``<dcterms:created>``.

    openpyxl's ``save()`` stamps BOTH ``<dcterms:modified>`` and
    ``<dcterms:created>`` with ``datetime.now()``, causing byte-level
    non-determinism across runs.  This function rewrites both values to
    ``when`` formatted as ISO8601 UTC after ``save()`` has landed.

    All zip entries are repacked with ``ZipInfo(date_time=(1980,1,1,0,0,0))``
    and a fixed ``compresslevel`` so the resulting archive is byte-identical
    for identical inputs regardless of host filesystem mtime precision or
    platform zlib default level.

    Technique mirrors examen's ``finalize_xlsx`` (T014) which corrected the
    immersio ``rewrite_modified_in_zip`` bug (only pinned ``modified``).

    Args:
        path: Path to the xlsx file to finalise (modified in-place).
        when: Datetime to embed as both ``<dcterms:modified>`` and
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
    - ``allow_unicode=True`` — Korean/Unicode characters written as-is.
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
# parquet determinism
# ---------------------------------------------------------------------------


def parquet_write_options() -> dict[str, Any]:
    """Return PyArrow parquet write options for byte-identical output.

    Returns::

        {
            "use_dictionary": False,    # removes dictionary page → stable size
            "write_statistics": False,  # removes row-group min/max metadata
            "compression": "snappy",    # matches immersio/examen convention
        }

    Pass as ``**parquet_write_options()`` to ``pyarrow.parquet.write_table``.
    """
    return {
        "use_dictionary": False,
        "write_statistics": False,
        "compression": "snappy",
    }


__all__ = ["finalize_xlsx", "dump_yaml", "parquet_write_options"]
