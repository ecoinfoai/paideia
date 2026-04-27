"""Contract tests for needs-map IO loaders (T030, FR-001 / FR-AXIS-001)."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest
import yaml
from needs_map.io.keywords import compute_match_rate, load_keywords
from needs_map.io.mapping import load_mapping
from needs_map.io.silver import (
    load_diagnostic_response,
    load_student_master,
)
from pydantic import ValidationError


def _good_student_master_row() -> dict:
    return {
        "student_id": "2026194042",
        "semester": "2026-1",
        "course_slug": "anatomy",
        "on_roster": True,
        "section": "A",
        "name_kr": "홍길동",
        "diagnostic_responded": True,
        "exam_taken": True,
        "exam_absent": False,
        "attendance_recorded": True,
        "exam_total_score": None,
        "exam_max_score": None,
        "attendance_present_count": None,
        "attendance_absent_count": None,
        "attendance_late_count": None,
        "attendance_excused_count": None,
        "axis_scores": {"motivation": 5.0},
    }


def _good_diagnostic_response_row() -> dict:
    return {
        "student_id": "2026194042",
        "semester": "2026-1",
        "course_slug": "anatomy",
        "axis": "motivation",
        "axis_kind": "likert",
        "value_int": 5,
        "value_bool": None,
        "value_text": None,
        "option_key": None,
        "source_column": "Q01_motivation_a",
    }


def _good_mapping_yaml() -> dict:
    return {
        "metadata": {
            "semester": "2026-1",
            "course_slug": "anatomy",
            "course_name_kr": "인체구조와기능",
            "mapping_version": 1,
        },
        "columns": [
            {"source": "학번", "kind": "identity"},
            {
                "source": "Q01_motivation_a",
                "kind": "likert",
                "axis": "motivation",
                "aggregate": "mean",
            },
        ],
        "axes": {"required": ["motivation"], "optional": []},
    }


# --- silver.py ---


def test_silver_loader_missing_file_raises_with_path(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError, match="diagnostic_response.parquet"):
        load_diagnostic_response(tmp_path, "2026-1", "anatomy")
    with pytest.raises(FileNotFoundError, match="student_master.parquet"):
        load_student_master(tmp_path, "2026-1", "anatomy")


def test_silver_loader_empty_parquet_returns_empty_df(tmp_path: Path) -> None:
    silver = tmp_path / "silver" / "immersio" / "2026-1-anatomy"
    silver.mkdir(parents=True)
    pd.DataFrame().to_parquet(silver / "diagnostic_response.parquet")
    pd.DataFrame().to_parquet(silver / "student_master.parquet")

    df_resp = load_diagnostic_response(tmp_path, "2026-1", "anatomy")
    df_master = load_student_master(tmp_path, "2026-1", "anatomy")
    assert df_resp.empty
    assert df_master.empty


def test_silver_loader_valid_rows_pass(tmp_path: Path) -> None:
    silver = tmp_path / "silver" / "immersio" / "2026-1-anatomy"
    silver.mkdir(parents=True)
    pd.DataFrame([_good_student_master_row()]).to_parquet(silver / "student_master.parquet")
    pd.DataFrame([_good_diagnostic_response_row()]).to_parquet(silver / "diagnostic_response.parquet")

    df_master = load_student_master(tmp_path, "2026-1", "anatomy")
    df_resp = load_diagnostic_response(tmp_path, "2026-1", "anatomy")
    assert df_master.iloc[0]["student_id"] == "2026194042"
    assert df_resp.iloc[0]["axis_kind"] == "likert"


def test_silver_loader_contract_violation_includes_path(tmp_path: Path) -> None:
    silver = tmp_path / "silver" / "immersio" / "2026-1-anatomy"
    silver.mkdir(parents=True)
    bad_row = _good_student_master_row()
    bad_row["student_id"] = "X"  # not 10-digit
    pd.DataFrame([bad_row]).to_parquet(silver / "student_master.parquet")

    with pytest.raises(ValueError, match="StudentMaster contract violation"):
        load_student_master(tmp_path, "2026-1", "anatomy")


# --- mapping.py ---


def test_mapping_loader_happy(tmp_path: Path) -> None:
    p = tmp_path / "anatomy.diagnostic.yaml"
    p.write_text(yaml.safe_dump(_good_mapping_yaml()), encoding="utf-8")
    cfg = load_mapping(p)
    assert cfg.metadata.course_slug == "anatomy"
    assert cfg.axes.required == ["motivation"]


def test_mapping_loader_missing_file_raises(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError, match="Mapping YAML not found"):
        load_mapping(tmp_path / "absent.yaml")


def test_mapping_loader_top_level_must_be_mapping(tmp_path: Path) -> None:
    p = tmp_path / "list.yaml"
    p.write_text(yaml.safe_dump([1, 2, 3]), encoding="utf-8")
    with pytest.raises(ValueError, match="expected top-level mapping"):
        load_mapping(p)


def test_mapping_loader_v6_violation_surfaced(tmp_path: Path) -> None:
    """Non-standard axis key must raise ValidationError mentioning V6."""
    bad = _good_mapping_yaml()
    bad["axes"]["required"] = ["self_regulation"]
    bad["columns"][1]["axis"] = "self_regulation"
    p = tmp_path / "bad.yaml"
    p.write_text(yaml.safe_dump(bad), encoding="utf-8")
    with pytest.raises(ValidationError) as exc:
        load_mapping(p)
    assert "V6" in str(exc.value)
    assert "self_regulation" in str(exc.value)


def test_mapping_loader_v5_violation_surfaced(tmp_path: Path) -> None:
    """partition_axis=True on freetext must raise ValidationError mentioning V5."""
    bad = _good_mapping_yaml()
    bad["columns"].append(
        {
            "source": "Q62_anxiety_freetext",
            "kind": "freetext",
            "axis": "anxiety",
            "partition_axis": True,
        }
    )
    bad["axes"]["required"] = ["motivation", "anxiety"]
    p = tmp_path / "bad.yaml"
    p.write_text(yaml.safe_dump(bad), encoding="utf-8")
    with pytest.raises(ValidationError) as exc:
        load_mapping(p)
    assert "V5" in str(exc.value)


def test_mapping_loader_rejects_non_path() -> None:
    with pytest.raises(TypeError):
        load_mapping("string-path.yaml")  # type: ignore[arg-type]


# --- keywords.py ---


def test_load_keywords_returns_default_dictionary() -> None:
    d = load_keywords("ko")
    assert d.language == "ko"
    assert len(d.entries) >= 5


def test_compute_match_rate_substantive_only() -> None:
    d = load_keywords("ko")
    rate = compute_match_rate(d, ["암기가 너무 많아요", "시간이 부족합니다", "잘 모르겠어요"])
    assert rate == pytest.approx(2 / 3)


def test_compute_match_rate_excludes_empty() -> None:
    d = load_keywords("ko")
    rate = compute_match_rate(d, ["", "  ", "\t"])
    assert rate == 0.0  # zero substantive responses


def test_compute_match_rate_all_uncategorized() -> None:
    d = load_keywords("ko")
    rate = compute_match_rate(d, ["random unrelated text", "another"])
    assert rate == 0.0


def test_compute_match_rate_all_match() -> None:
    d = load_keywords("ko")
    rate = compute_match_rate(d, ["외우기 힘듦", "시간 없음"])
    assert rate == 1.0
