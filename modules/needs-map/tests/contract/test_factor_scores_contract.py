"""Contract tests for FactorScoreRow round-trip parquet write/read (T048)."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
from paideia_shared.schemas import FactorScoreRow

_AXES = (
    "digital_efficacy",
    "motivation",
    "time_availability",
    "material_preference",
    "study_strategy",
    "study_environment",
    "social_learning",
    "feedback_seeking",
)


def _make_rows(n: int = 50) -> list[dict]:
    """Synthesize n FactorScoreRow-shaped dicts that pass V1 + V2."""
    rows: list[dict] = []
    for i in range(n):
        row: dict = {
            "student_id": f"20261940{i:02d}" if i < 100 else f"202619{i:04d}",
            "on_roster": True,
            "responded": True,
            "section": "A" if i % 2 == 0 else "B",
        }
        for ax in _AXES:
            row[ax] = float(i % 7) + 1.0
            row[f"{ax}_z"] = (float(i % 7) - 3.0) / 2.0
            row[f"{ax}_missing"] = False
        rows.append(row)
    return rows


def test_factor_score_rows_round_trip_through_parquet(tmp_path: Path) -> None:
    rows = _make_rows(50)
    df = pd.DataFrame(rows)
    parquet_path = tmp_path / "factor_scores.parquet"
    df.to_parquet(parquet_path, index=False)

    # Read back and validate every row through Pydantic
    df_back = pd.read_parquet(parquet_path)
    assert len(df_back) == 50
    for raw in df_back.to_dict(orient="records"):
        FactorScoreRow.model_validate(raw)


def test_factor_score_drop_row_round_trip(tmp_path: Path) -> None:
    """Drop policy: score=None ↔ z=None ↔ missing=True must survive parquet round-trip."""
    row: dict = {
        "student_id": "2026194042",
        "on_roster": True,
        "responded": True,
        "section": "A",
    }
    for ax in _AXES:
        row[ax] = None
        row[f"{ax}_z"] = None
        row[f"{ax}_missing"] = True
    df = pd.DataFrame([row])
    parquet_path = tmp_path / "factor_scores.parquet"
    df.to_parquet(parquet_path, index=False)
    df_back = pd.read_parquet(parquet_path)
    raw = df_back.iloc[0].to_dict()
    # parquet reads None in float columns as NaN; convert back to None for Pydantic
    cleaned: dict = {}
    for key, value in raw.items():
        if isinstance(value, float) and pd.isna(value):
            cleaned[key] = None
        else:
            cleaned[key] = value
    FactorScoreRow.model_validate(cleaned)
