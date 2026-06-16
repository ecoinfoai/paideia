"""Silver-tier writers (T053, FR-018).

Persist ``StudentExamMetrics`` rows to ``data/silver/immersio/{key}/학생지표.parquet``
with snappy compression and 학번-ascending row order. The xlsx 학생성적
sheet shares the same source list (T052), guaranteeing round-trip
equivalence per FR-018.

Determinism (FR-023):
* Rows sorted by ``student_id`` ascending → stable physical order.
* dict columns (``chapter_correct_rates`` etc.) JSON-encoded with
  ``sort_keys=True`` so two callers serialise identical bytes.
* pyarrow's parquet writer uses fixed page sizes + snappy compression
  → byte-identical for identical input.
"""

from __future__ import annotations

import json
from collections.abc import Iterable
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq
from paideia_shared.schemas import StudentExamMetrics

_SCHEMA_VERSION = "1.0.0"


def _encode_dict(value: dict) -> str:
    """Serialise a dict into a deterministic JSON string."""
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def _to_record(m: StudentExamMetrics) -> dict[str, object]:
    return {
        "student_id": m.student_id,
        "name_kr": m.name_kr,
        "section": m.section,
        "semester": m.semester,
        "course_slug": m.course_slug,
        "exam_taken": m.exam_taken,
        "total_score": m.total_score,
        "score_percent": m.score_percent,
        "section_percentile": m.section_percentile,
        "cohort_percentile": m.cohort_percentile,
        "z_score": m.z_score,
        "chapter_correct_rates": _encode_dict(m.chapter_correct_rates),
        "source_correct_rates": _encode_dict(m.source_correct_rates),
        "difficulty_correct_rates": _encode_dict(m.difficulty_correct_rates),
        "expected_difficulty_correct_rates": _encode_dict(m.expected_difficulty_correct_rates),
        "item_type_correct_rates": _encode_dict(m.item_type_correct_rates),
        "interest_chapters_correct_rate": m.interest_chapters_correct_rate,
        "aversion_chapters_correct_rate": m.aversion_chapters_correct_rate,
    }


def write_student_metrics_parquet(
    *,
    rows: Iterable[StudentExamMetrics],
    output_path: Path,
) -> None:
    """Persist StudentExamMetrics rows to ``output_path`` as snappy parquet.

    Args:
        rows: Iterable of ``StudentExamMetrics``. Sorted by
            ``student_id`` ascending before writing.
        output_path: Target ``.parquet`` path. Parent directory must
            exist; the function does NOT mkdir (fail-fast).

    Raises:
        ValueError: When ``rows`` is empty.
        FileNotFoundError: When ``output_path.parent`` does not exist.
    """
    materialised = list(rows)
    if not materialised:
        raise ValueError("write_student_metrics_parquet: rows is empty")
    output_path = Path(output_path)
    if not output_path.parent.is_dir():
        raise FileNotFoundError(
            f"write_student_metrics_parquet: parent directory missing: {output_path.parent}"
        )

    materialised.sort(key=lambda m: m.student_id)
    records = [_to_record(m) for m in materialised]
    table = pa.Table.from_pylist(records)
    table = table.replace_schema_metadata(
        {
            b"schema_version": _SCHEMA_VERSION.encode(),
            b"producer": b"paideia/immersio/0.1.0",
        }
    )
    pq.write_table(
        table,
        str(output_path),
        compression="snappy",
        use_dictionary=False,
        write_statistics=False,
    )


__all__ = ["write_student_metrics_parquet"]
