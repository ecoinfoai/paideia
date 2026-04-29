"""TDD tests for ``combine.joiner.join_silver_phase3`` (T016).

Verifies the 60-column left-join (FR-016) produces:
- ``CombinedAnalysisRow`` schema-compliant rows
- R-10 unmatched audit counts (4 fields: factor_scores / cluster_assignment /
  student_metrics / off-roster respondents)
- deterministic row ordering by ``student_id`` ascending (research §R13
  determinism vector #6)
- cluster_label lookup via SPEC-GAP-001 sidecar dict
- 진단응답 / 시험응시 flag derivation per FR-014

Inputs come from the ``silver_phase3_minimal`` fixture (T014) plus
in-line synthesised dataframes for the off-roster and unmatched scenarios
that the minimal fixture does not exercise on its own.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from types import ModuleType
from typing import Any

import pandas as pd
import pyarrow.parquet as pq
import pytest

from immersio.combine.joiner import UnmatchedCounts, join_silver_phase3
from paideia_shared.schemas import CombinedAnalysisRow


# ---------------------------------------------------------------------------
# Fixture loaders
# ---------------------------------------------------------------------------


_FIXTURE_ROOT = (
    Path(__file__).resolve().parents[2] / "fixtures" / "silver_phase3_minimal"
)


def _load_builder() -> ModuleType:
    here = Path(__file__).resolve()
    builder_path = here.parents[2] / "fixtures" / "build_silver_phase3.py"
    spec = importlib.util.spec_from_file_location(
        "build_silver_phase3", builder_path
    )
    if spec is None or spec.loader is None:
        raise RuntimeError(f"could not load builder from {builder_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def minimal_silver(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Build the minimal fixture into a fresh tmp dir for hermetic tests."""
    out = tmp_path_factory.mktemp("silver_phase3_minimal")
    builder = _load_builder()
    builder.build_silver_phase3_minimal(out)
    return out


def _read(path: Path) -> pd.DataFrame:
    return pq.read_table(path).to_pandas()


def _load_inputs(root: Path) -> dict[str, Any]:
    nm = root / "silver" / "needs-map" / "2026-1-anatomy"
    im = root / "silver" / "immersio" / "2026-1-anatomy"
    cluster_names_raw = json.loads(
        (nm / "cluster_names.json").read_text(encoding="utf-8")
    )
    cluster_names = {int(k): v for k, v in cluster_names_raw.items()}
    return {
        "student_master": _read(im / "student_master.parquet"),
        "factor_scores": _read(nm / "factor_scores.parquet"),
        "cluster_assignment": _read(nm / "cluster_assignment.parquet"),
        "cluster_names": cluster_names,
        "student_metrics": _read(im / "학생지표.parquet"),
        "diagnostic_response": _read(im / "diagnostic_response.parquet"),
    }


# ---------------------------------------------------------------------------
# Happy path — minimal fixture
# ---------------------------------------------------------------------------


def test_joiner_produces_60_column_dataframe(minimal_silver: Path) -> None:
    """T016 core: 5-source left-join → 60-column output, fixed order."""
    inputs = _load_inputs(minimal_silver)
    df, _counts = join_silver_phase3(**inputs)

    assert len(df) == 30, f"minimal fixture has 30 students, got {len(df)}"
    assert len(df.columns) == 60, (
        f"contract requires 60 columns, got {len(df.columns)}"
    )

    # First 6 columns = identity group.
    assert list(df.columns[:6]) == [
        "student_id",
        "name_kr",
        "on_roster",
        "section",
        "semester",
        "course_slug",
    ]
    # Last 4 columns = combined metadata group.
    assert list(df.columns[-4:]) == [
        "진단응답",
        "시험응시",
        "needs_map_schema_version",
        "immersio_phase2_schema_version",
    ]


def test_joiner_row_order_student_id_ascending(minimal_silver: Path) -> None:
    """Determinism vector #6: rows sorted by student_id ascending."""
    inputs = _load_inputs(minimal_silver)
    df, _ = join_silver_phase3(**inputs)
    sids = df["student_id"].tolist()
    assert sids == sorted(sids), "row order must be student_id ascending"


def test_joiner_rows_validate_against_combined_analysis_row(
    minimal_silver: Path,
) -> None:
    """Every row must satisfy CombinedAnalysisRow Pydantic V1-V6."""
    inputs = _load_inputs(minimal_silver)
    df, _ = join_silver_phase3(**inputs)

    for record in df.to_dict("records"):
        # dict columns are JSON-encoded strings on parquet round-trip; the
        # joiner returns them as native dicts so Pydantic can validate.
        CombinedAnalysisRow.model_validate(record)


def test_joiner_minimal_has_zero_unmatched(minimal_silver: Path) -> None:
    """T014 fixture has 0 off-roster + every roster student covered."""
    inputs = _load_inputs(minimal_silver)
    _, counts = join_silver_phase3(**inputs)

    assert counts.unmatched_factor_scores == 0
    assert counts.unmatched_cluster_assignment == 0
    assert counts.unmatched_student_metrics == 0
    assert counts.off_roster_respondents == 0


def test_joiner_diagnostic_and_exam_flags(minimal_silver: Path) -> None:
    """진단응답 = True iff any axis raw is not None; 시험응시 == exam_taken."""
    inputs = _load_inputs(minimal_silver)
    df, _ = join_silver_phase3(**inputs)

    # Minimal: 22 응답+응시 + 5 응시-only + 3 응답-only = 25 진단응답 / 27 시험응시.
    assert int(df["진단응답"].sum()) == 25
    assert int(df["시험응시"].sum()) == 27
    # 시험응시 mirrors exam_taken.
    assert df["시험응시"].equals(df["exam_taken"])


def test_joiner_cluster_label_lookup_via_sidecar(minimal_silver: Path) -> None:
    """cluster_id ↔ cluster_label V4 consistency uses sidecar dict."""
    inputs = _load_inputs(minimal_silver)
    df, _ = join_silver_phase3(**inputs)

    labelled = df[df["cluster_id"].notna()].copy()
    labels = sorted(labelled["cluster_label"].dropna().unique().tolist())
    # Minimal fixture k=3 names — alphabetic sort.
    assert labels == sorted(
        ["성장 잠재형", "안정 학습형", "고성취 자기주도형"]
    )

    # When cluster_id is None, the other two cluster columns must also be None.
    no_cluster = df[df["cluster_id"].isna()]
    assert no_cluster["cluster_label"].isna().all()
    assert no_cluster["cluster_distance"].isna().all()


def test_joiner_schema_version_columns_filled(minimal_silver: Path) -> None:
    inputs = _load_inputs(minimal_silver)
    df, _ = join_silver_phase3(**inputs)
    assert (df["needs_map_schema_version"] == "1.1.0").all()
    assert (df["immersio_phase2_schema_version"] == "0.1.0").all()


def test_joiner_byte_deterministic(minimal_silver: Path) -> None:
    """Calling join_silver_phase3 twice on identical inputs returns equal frames."""
    inputs = _load_inputs(minimal_silver)
    df1, c1 = join_silver_phase3(**inputs)
    df2, c2 = join_silver_phase3(**inputs)
    pd.testing.assert_frame_equal(df1, df2)
    assert c1 == c2


# ---------------------------------------------------------------------------
# R-10 unmatched audit scenarios — synthesised in-test
# ---------------------------------------------------------------------------


def _drop_student(df: pd.DataFrame, sid: str) -> pd.DataFrame:
    return df[df["student_id"] != sid].reset_index(drop=True)


def test_unmatched_factor_scores_counted(minimal_silver: Path) -> None:
    """Removing a respondent's row from factor_scores ⇒ unmatched_factor_scores=1."""
    inputs = _load_inputs(minimal_silver)
    # 2026000000 is an 응답+응시 student in the fixture.
    inputs["factor_scores"] = _drop_student(inputs["factor_scores"], "2026000000")
    _, counts = join_silver_phase3(**inputs)
    assert counts.unmatched_factor_scores == 1


def test_unmatched_cluster_assignment_counted(minimal_silver: Path) -> None:
    inputs = _load_inputs(minimal_silver)
    # cluster_assignment has 25 rows (responders only); pick any.
    sid = inputs["cluster_assignment"]["student_id"].iloc[0]
    inputs["cluster_assignment"] = _drop_student(inputs["cluster_assignment"], sid)
    _, counts = join_silver_phase3(**inputs)
    assert counts.unmatched_cluster_assignment == 1


def test_unmatched_student_metrics_counted(minimal_silver: Path) -> None:
    inputs = _load_inputs(minimal_silver)
    inputs["student_metrics"] = _drop_student(
        inputs["student_metrics"], "2026000000"
    )
    _, counts = join_silver_phase3(**inputs)
    assert counts.unmatched_student_metrics == 1


def test_off_roster_respondent_counted(minimal_silver: Path) -> None:
    """factor_scores carries a respondent who is NOT in student_master."""
    inputs = _load_inputs(minimal_silver)
    fs = inputs["factor_scores"].copy()
    new_row = fs.iloc[0].to_dict()
    new_row["student_id"] = "2026099999"  # not in student_master
    new_row["on_roster"] = False
    inputs["factor_scores"] = pd.concat(
        [fs, pd.DataFrame([new_row])], ignore_index=True
    )
    _, counts = join_silver_phase3(**inputs)
    assert counts.off_roster_respondents == 1
    # Off-roster respondents must NOT appear in the joined silver (left-join
    # is anchored on student_master — FR-016).
    df, _ = join_silver_phase3(**inputs)
    assert "2026099999" not in df["student_id"].values


# ---------------------------------------------------------------------------
# Fail-Fast on missing cluster_names key
# ---------------------------------------------------------------------------


def test_missing_cluster_name_for_used_cluster_id_raises(
    minimal_silver: Path,
) -> None:
    """If cluster_names dict lacks an id present in cluster_assignment ⇒ ValueError."""
    inputs = _load_inputs(minimal_silver)
    # Drop the label for cluster_id=2.
    inputs["cluster_names"] = {
        cid: name for cid, name in inputs["cluster_names"].items() if cid != 2
    }
    with pytest.raises(ValueError, match="cluster_names"):
        join_silver_phase3(**inputs)


def test_unmatched_counts_immutable() -> None:
    """UnmatchedCounts is a frozen dataclass — counters cannot drift post-return."""
    counts = UnmatchedCounts(
        unmatched_factor_scores=1,
        unmatched_cluster_assignment=2,
        unmatched_student_metrics=3,
        off_roster_respondents=4,
    )
    with pytest.raises((AttributeError, TypeError)):
        counts.unmatched_factor_scores = 99  # type: ignore[misc]
