"""Phase C sample-too-small fallback: k=1 when sample/k < 10 across all candidates (T063)."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
import yaml


def _tiny_silver(tmp_path: Path) -> Path:
    """Build a 5-responder Silver — sample/k < 10 holds for every k in [2..6]."""
    silver_dir = tmp_path / "silver" / "immersio" / "2026-1-anatomy"
    silver_dir.mkdir(parents=True)

    sm_rows = [
        {
            "student_id": f"20261940{i:02d}",
            "semester": "2026-1",
            "course_slug": "anatomy",
            "on_roster": True,
            "section": "A",
            "name_kr": f"학생{i:02d}",
            "diagnostic_responded": True,
            "exam_taken": False,
            "exam_absent": True,
            "attendance_recorded": False,
            "exam_total_score": None,
            "exam_max_score": None,
            "attendance_present_count": None,
            "attendance_absent_count": None,
            "attendance_late_count": None,
            "attendance_excused_count": None,
            "axis_scores": {"placeholder": None},
        }
        for i in range(5)
    ]
    pq.write_table(pa.Table.from_pandas(pd.DataFrame(sm_rows)), silver_dir / "student_master.parquet")

    # v0.1.1 V6 strict requires axes.required = full 8-key set. Each
    # responder contributes one likert response per axis so factor_scores
    # has substantive cluster input for the sample-too-small branch.
    axes_8 = (
        "digital_efficacy",
        "motivation",
        "time_availability",
        "material_preference",
        "study_strategy",
        "study_environment",
        "social_learning",
        "feedback_seeking",
    )
    source_for = {axis: f"Q_{axis}_1" for axis in axes_8}
    dr_rows: list[dict] = []
    for i in range(5):
        sid = f"20261940{i:02d}"
        for axis in axes_8:
            dr_rows.append(
                {
                    "student_id": sid,
                    "semester": "2026-1",
                    "course_slug": "anatomy",
                    "axis": axis,
                    "axis_kind": "likert",
                    "value_int": (i + 3) % 7 + 1,
                    "value_bool": None,
                    "value_text": None,
                    "option_key": None,
                    "source_column": source_for[axis],
                }
            )
    pq.write_table(pa.Table.from_pandas(pd.DataFrame(dr_rows)), silver_dir / "diagnostic_response.parquet")

    mapping = {
        "metadata": {
            "semester": "2026-1",
            "course_slug": "anatomy",
            "course_name_kr": "인체구조와기능",
            "mapping_version": 2,
        },
        "axes": {"required": list(axes_8), "optional": []},
        "columns": [
            {"source": "학번", "kind": "identity"},
            *[
                {
                    "source": source_for[axis],
                    "kind": "likert",
                    "axis": axis,
                    "aggregate": "mean",
                }
                for axis in axes_8
            ],
        ],
    }
    mapping_dir = tmp_path / "bronze" / "매핑"
    mapping_dir.mkdir(parents=True)
    (mapping_dir / "anatomy.diagnostic.yaml").write_text(
        yaml.safe_dump(mapping), encoding="utf-8"
    )
    return tmp_path


def test_sample_too_small_falls_back_to_k_one(tmp_path: Path) -> None:
    from needs_map.pipeline import NeedsMapArgs, run_needs_map

    args = NeedsMapArgs(
        semester="2026-1",
        course_slug="anatomy",
        phases=frozenset({"A", "B", "C"}),
        input_root=_tiny_silver(tmp_path / "in"),
        output_root=tmp_path / "out",
        seed=42,
        llm_enabled=False,
        llm_provider="anthropic",
        llm_model="claude-sonnet-4-6",
    )
    manifest = run_needs_map(args)
    # 5 responders → sample/k < 10 for every k≥2 → auto-fallback to k=1
    assert manifest.cluster_k_used == 1
    assert manifest.cluster_silhouette_used is None
