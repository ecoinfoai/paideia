"""T014 — Determinism utilities for Gold-layer outputs.

Provides byte-identical output guarantees for:
- ``finalize_xlsx(path, when)`` — strips openpyxl's runtime-stamped
  ``<dcterms:modified>`` by repacking the xlsx zip with a pinned value
  and fixed ZipInfo date_time.  Mirrors immersio's ``rewrite_modified_in_zip``
  technique (modules/immersio/src/immersio/report/xlsx_writer.py).
- ``dump_yaml(obj) -> str`` — sort_keys, allow_unicode, normalised newlines.
- ``parquet_write_options() -> dict`` — ``use_dictionary=False``,
  ``write_statistics=False``, ``compression='snappy'``.

None of these functions contain business logic or LLM calls.

Immersio reference
------------------
The xlsx pinning technique is deliberately identical to immersio's
``rewrite_modified_in_zip``:

  1. Read all zip entries into memory.
  2. Replace ``docProps/core.xml``'s ``<dcterms:modified>`` text with the
     pinned ISO8601 UTC string.
  3. Repack the archive with ``ZipInfo(date_time=(1980,1,1,0,0,0))`` for
     every entry (openpyxl's own pin value).
  4. Overwrite ``path`` with the new bytes.

This avoids monkey-patching openpyxl's internal datetime module, which
bleeds across pytest fixtures (see immersio module docstring for the
full history).
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
# openpyxl 은 ``<dcterms:created>`` 도 datetime.now() 로 스탬프한다.
# ``<dcterms:modified>`` 만 핀하면 두 빌드가 wall-clock 초 경계를 넘을 때
# ``created`` 값이 갈려 xlsx 바이트가 비결정적이 된다 → 둘 다 핀한다.
_CREATED_RE = re.compile(
    r"(<dcterms:created[^>]*>)([^<]+)(</dcterms:created>)",
    re.DOTALL,
)
# openpyxl이 내부적으로 사용하는 고정 mtime — 여기에도 동일하게 적용
_FIXED_ZIP_DATE = (1980, 1, 1, 0, 0, 0)
# zip 압축 레벨 고정 — zlib 기본값이 플랫폼/버전 따라 달라질 수 있어 명시한다.
_FIXED_COMPRESSLEVEL = 6


def finalize_xlsx(path: Path, when: datetime.datetime) -> None:
    """Repack ``path`` with pinned ``<dcterms:modified>`` and ``<dcterms:created>``.

    openpyxl's ``save()`` stamps BOTH ``<dcterms:modified>`` and
    ``<dcterms:created>`` with ``datetime.now()``, causing byte-level
    non-determinism across runs.  This function rewrites both values to
    ``when`` formatted as ISO8601 UTC after ``save()`` has landed.

    Why both: two ``build_exam`` runs separated by enough work to cross a
    wall-clock SECOND boundary would otherwise produce different
    ``<dcterms:created>`` strings → divergent xlsx bytes (the intermittent
    full-suite ``test_rerun_xlsx_byte_identical`` flake).

    All zip entries are repacked with ``ZipInfo(date_time=(1980,1,1,0,0,0))``
    and a FIXED ``compresslevel`` so the resulting archive is byte-identical
    for identical inputs regardless of the host filesystem's mtime precision
    or the platform zlib default level.

    Technique mirrors ``rewrite_modified_in_zip`` in
    ``modules/immersio/src/immersio/report/xlsx_writer.py``.

    Args:
        path: Path to the xlsx file to finalise (modified in-place).
        when: The datetime to embed as ``<dcterms:modified>`` and
            ``<dcterms:created>`` (treated as UTC).
    """
    iso = when.strftime("%Y-%m-%dT%H:%M:%SZ")

    # openpyxl 이 생성한 xlsx 를 가정한다. 두 dcterms 요소가 없으면 regex 가
    # 매치 0개로 조용히 통과(no-op) — immersio 와 동일 동작.
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
            # 원본 압축 방식 유지 (openpyxl 선택 압축 호환)
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
        # YAML 1.1 호환 — 불린 값 True/False 그대로 직렬화
        Dumper=yaml.SafeDumper,
    )
    # 빈 문서라도 개행 1개로 정규화 (yaml.dump는 이미 개행으로 끝나나 명시적으로 보장)
    return result if result.endswith("\n") else result + "\n"


# ---------------------------------------------------------------------------
# parquet determinism
# ---------------------------------------------------------------------------

def parquet_write_options() -> dict[str, Any]:
    """Return PyArrow parquet write options for byte-identical output.

    Returns::

        {
            "use_dictionary": False,    # dictionary 페이지 제거 → 크기 안정
            "write_statistics": False,  # row-group min/max 메타 제거
            "compression": "snappy",    # immersio 패턴 그대로 유지
        }

    Pass as ``**parquet_write_options()`` to ``pyarrow.parquet.write_table``.
    """
    return {
        "use_dictionary": False,
        "write_statistics": False,
        "compression": "snappy",
    }


__all__ = ["finalize_xlsx", "dump_yaml", "parquet_write_options"]
