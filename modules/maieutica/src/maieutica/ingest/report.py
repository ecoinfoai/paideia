"""T020 — ingest_report.json writer.

Writes the ingest report as deterministic JSON (sort_keys, ensure_ascii=False)
using atomic temp→rename to prevent partial files (constitution V).

The ingest report shape for maieutica follows FR-021 (anomalies recorded, not
silently dropped)::

    {
        "textbook": {
            "chapters_required": int,
            "chapters_found": int,
            "removed_span_counts": {...}
        },
        "anomalies": {
            "filename_violations": [...],
            "unexpected_files": [...]
        }
    }

The caller constructs this dict; this module only handles deterministic I/O.

Usage::

    from maieutica.ingest.report import write_ingest_report

    write_ingest_report(Path("data/silver/maieutica/2026-1-anatomy/ingest_report.json"), report)
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from maieutica.output.paths import atomic_write


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
            the destination (fail-fast boundary — FR-021).

    Raises:
        TypeError: If ``report_dict`` contains non-JSON-serialisable values.
            No partial file is written.
    """
    # Serialise first — fail fast before any filesystem side effects
    serialized = json.dumps(
        report_dict,
        sort_keys=True,
        ensure_ascii=False,
        indent=2,
    )
    # Normalise: ensure exactly one trailing newline
    if not serialized.endswith("\n"):
        serialized += "\n"

    # Create parent directories only after serialisation succeeds
    path.parent.mkdir(parents=True, exist_ok=True)

    def _write(tmp: Path) -> None:
        tmp.write_text(serialized, encoding="utf-8")

    atomic_write(path, _write)


__all__ = ["write_ingest_report"]
