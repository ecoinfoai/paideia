"""T017 — ingest_report.json writer.

Writes the ingest report as deterministic JSON (sort_keys, ensure_ascii=False)
using atomic temp→rename to prevent partial files (constitution V).

The ingest report shape follows contracts/manifest_examen.md §ingest_report::

    {
        "stt": {"expected": int, "found": int, "missing": [...], "filename_violations": [...]},
        "textbook": {"chapters_required": int, "chapters_found": int, "removed_span_counts": {...}},
        "formative": {"expected_total": int, "found": int},
        "quiz": {"weeks": [...], "rows": int}
    }

The caller constructs this dict; this module only handles deterministic I/O.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from examen.output.paths import atomic_write


def write_ingest_report(path: Path, report_dict: dict[str, Any]) -> None:
    """Write ``report_dict`` to ``path`` as deterministic UTF-8 JSON.

    Output properties:
    - ``sort_keys=True`` — key order is alphabetical, not insertion order.
    - ``ensure_ascii=False`` — Korean/Unicode characters written as-is.
    - ``indent=2`` — human-readable indentation.
    - Written atomically via temp→rename (no partial file on failure).
    - Parent directories are created if they do not exist.

    Args:
        path: Destination path for the JSON file.
        report_dict: The ingest report data.  Must be JSON-serialisable;
            any non-serialisable value raises ``TypeError`` without touching
            the destination.

    Raises:
        TypeError: If ``report_dict`` contains non-JSON-serialisable values.
            No partial file is written.
    """
    # 부모 디렉터리 생성 (없으면)
    path.parent.mkdir(parents=True, exist_ok=True)

    # JSON 직렬화를 먼저 시도 — 실패 시 파일을 건드리지 않음
    serialized = json.dumps(
        report_dict,
        sort_keys=True,
        ensure_ascii=False,
        indent=2,
    )
    # 개행 정규화: 마지막에 개행 1개 추가
    if not serialized.endswith("\n"):
        serialized += "\n"

    def _write(tmp: Path) -> None:
        tmp.write_text(serialized, encoding="utf-8")

    atomic_write(path, _write)


__all__ = ["write_ingest_report"]
