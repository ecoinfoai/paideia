"""v0.1.1 student-level long CSV/YAML + axis summary CSV/YAML writers [T036].

Two writer functions ship the four operator-facing gold files documented in
``contracts/exports.md``:

- :func:`write_factor_scores_long` — one row per cohort responder, sorted
  by ``student_id`` ascending. Emits both CSV (UTF-8 with BOM, LF
  newlines, ``round(x, 4)`` on floats, missing → empty cell) and YAML
  (``students:`` top-level list).
- :func:`write_axis_summary` — discriminator-driven; emits CSV with the
  fixed unified column order from contracts/exports.md and YAML re-folded
  into ``quantitative_axes`` / ``auxiliary_distributions`` /
  ``freetext_summaries`` sub-trees.

Determinism (FR-035): both writers are pure functions of their input
``rows`` argument; LF newlines + sorted iteration + fixed float rounding
yield byte-equal output across two consecutive writes against the same
inputs. The aggregator (``build_axis_summary_rows``) lives in
``aggregation.py`` so this module only cares about *serialisation*.

Spec: 003-needs-map-v0-1-1/tasks.md T036; contracts/exports.md §1-§4.
"""

from __future__ import annotations

import json
from collections import defaultdict
from collections.abc import Iterable
from pathlib import Path

import pandas as pd
import yaml
from paideia_shared.schemas import AxisSummaryRow, FactorScoresLongRow

# Fixed CSV column order — must match contracts/exports.md L19-L37 exactly.
_LONG_COLUMNS: tuple[str, ...] = (
    "student_id",
    "semester",
    "course_slug",
    "on_roster",
    "section",
    "responded",
    "digital_efficacy_raw",
    "digital_efficacy_z",
    "digital_efficacy_missing",
    "motivation_raw",
    "motivation_z",
    "motivation_missing",
    "time_availability_raw",
    "time_availability_z",
    "time_availability_missing",
    "material_preference_raw",
    "material_preference_z",
    "material_preference_missing",
    "study_strategy_raw",
    "study_strategy_z",
    "study_strategy_missing",
    "study_environment_raw",
    "study_environment_z",
    "study_environment_missing",
    "social_learning_raw",
    "social_learning_z",
    "social_learning_missing",
    "feedback_seeking_raw",
    "feedback_seeking_z",
    "feedback_seeking_missing",
    "prior_readiness_q5",
    "prior_readiness_q6",
    "time_pattern_q21",
    "time_pattern_q23",
    "time_pattern_q22",
    "interest_topics_q9",
    "interest_topics_q10",
    "interest_topics_q11",
    "categorical_intent_q12",
    "categorical_intent_q13",
    "cluster_id",
    "cluster_label",
    "cluster_distance",
    "freetext_q61_categories",
    "freetext_q61_negativity",
    "freetext_q61_top_emotion",
    "freetext_q62_categories",
    "freetext_q62_negativity",
    "freetext_q62_top_emotion",
)

_AXIS_SUMMARY_COLUMNS: tuple[str, ...] = (
    "row_kind",
    "axis_key",
    "n",
    "n_items",
    "mean_raw",
    "std_raw",
    "p25",
    "p50",
    "p75",
    "cronbach_alpha",
    "reliability_label",
    "source_col",
    "option",
    "count",
    "percentage",
    "n_responded",
    "n_cohort",
    "n_responses",
    "n_categorized",
    "dictionary_match_rate",
    "mean_negativity",
    "top_emotion_distribution",
)

_FLOAT_PRECISION = 4
_LONG_FILENAME_CSV = "factor_scores_long.csv"
_LONG_FILENAME_YAML = "factor_scores_long.yaml"
_AXIS_SUMMARY_FILENAME_CSV = "axis_summary.csv"
_AXIS_SUMMARY_FILENAME_YAML = "axis_summary.yaml"


def write_factor_scores_long(
    rows: Iterable[FactorScoresLongRow], gold_dir: Path
) -> tuple[Path, Path]:
    """Write the v0.1.1 long-form CSV + YAML to ``gold_dir``.

    Args:
        rows: Iterable of validated ``FactorScoresLongRow`` instances. Order
            is normalised to ``student_id`` ascending before serialisation.
        gold_dir: Existing or creatable gold directory (e.g.
            ``data/gold/needs-map/2026-1-anatomy``).

    Returns:
        ``(csv_path, yaml_path)`` of the written files.
    """
    if not isinstance(gold_dir, Path):
        raise TypeError(f"write_factor_scores_long: expected Path, got {type(gold_dir).__name__}.")
    gold_dir.mkdir(parents=True, exist_ok=True)
    materialised = sorted(rows, key=lambda r: r.student_id)

    payloads = [_long_row_to_dict(row) for row in materialised]
    df = pd.DataFrame(payloads, columns=list(_LONG_COLUMNS))

    csv_path = gold_dir / _LONG_FILENAME_CSV
    df.to_csv(
        csv_path,
        encoding="utf-8-sig",
        index=False,
        lineterminator="\n",
        na_rep="",
    )

    yaml_path = gold_dir / _LONG_FILENAME_YAML
    yaml_doc = {"students": payloads}
    yaml_path.write_text(
        yaml.safe_dump(
            yaml_doc,
            sort_keys=False,
            allow_unicode=True,
            default_flow_style=False,
        ),
        encoding="utf-8",
    )
    return csv_path, yaml_path


def write_axis_summary(rows: Iterable[AxisSummaryRow], gold_dir: Path) -> tuple[Path, Path]:
    """Write the v0.1.1 axis_summary CSV + YAML to ``gold_dir``.

    Args:
        rows: Iterable of validated ``AxisSummaryRow`` instances. Order is
            normalised: quantitative rows first (in ``axis_key`` ascending),
            then auxiliary_distribution rows (sorted by axis_key, source_col,
            option), then freetext_summary rows (sorted by axis_key).
        gold_dir: Existing or creatable gold directory.

    Returns:
        ``(csv_path, yaml_path)`` of the written files.
    """
    if not isinstance(gold_dir, Path):
        raise TypeError(f"write_axis_summary: expected Path, got {type(gold_dir).__name__}.")
    gold_dir.mkdir(parents=True, exist_ok=True)
    sorted_rows = _sort_axis_summary_rows(rows)

    csv_records = [_axis_summary_row_to_csv_dict(row) for row in sorted_rows]
    df = pd.DataFrame(csv_records, columns=list(_AXIS_SUMMARY_COLUMNS))
    csv_path = gold_dir / _AXIS_SUMMARY_FILENAME_CSV
    df.to_csv(
        csv_path,
        encoding="utf-8-sig",
        index=False,
        lineterminator="\n",
        na_rep="",
    )

    yaml_path = gold_dir / _AXIS_SUMMARY_FILENAME_YAML
    yaml_doc = _axis_summary_yaml_doc(sorted_rows)
    yaml_path.write_text(
        yaml.safe_dump(
            yaml_doc,
            sort_keys=False,
            allow_unicode=True,
            default_flow_style=False,
        ),
        encoding="utf-8",
    )
    return csv_path, yaml_path


def _long_row_to_dict(row: FactorScoresLongRow) -> dict[str, object]:
    """Serialise a FactorScoresLongRow with ``round(x, 4)`` on floats."""
    raw = row.model_dump()
    out: dict[str, object] = {}
    for col in _LONG_COLUMNS:
        value = raw.get(col)
        if isinstance(value, float):
            out[col] = round(value, _FLOAT_PRECISION)
        else:
            out[col] = value
    return out


def _axis_summary_row_to_csv_dict(row: AxisSummaryRow) -> dict[str, object]:
    """Serialise an AxisSummaryRow with floats rounded + dict→JSON string."""
    raw = row.model_dump()
    out: dict[str, object] = {}
    for col in _AXIS_SUMMARY_COLUMNS:
        value = raw.get(col)
        if col == "top_emotion_distribution" and isinstance(value, dict):
            out[col] = json.dumps(value, ensure_ascii=False, sort_keys=True)
        elif isinstance(value, float):
            out[col] = round(value, _FLOAT_PRECISION)
        else:
            out[col] = value
    return out


def _sort_axis_summary_rows(rows: Iterable[AxisSummaryRow]) -> list[AxisSummaryRow]:
    """Stable order: quant → aux → freetext, with secondary sort within group."""
    quant: list[AxisSummaryRow] = []
    aux: list[AxisSummaryRow] = []
    freetext: list[AxisSummaryRow] = []
    for r in rows:
        if r.row_kind == "quantitative":
            quant.append(r)
        elif r.row_kind == "auxiliary_distribution":
            aux.append(r)
        else:
            freetext.append(r)
    quant.sort(key=lambda r: r.axis_key)
    aux.sort(key=lambda r: (r.axis_key, r.source_col or "", r.option or ""))
    freetext.sort(key=lambda r: r.axis_key)
    return quant + aux + freetext


def _axis_summary_yaml_doc(rows: list[AxisSummaryRow]) -> dict[str, object]:
    """Re-fold rows into the per-row_kind sub-tree structure."""
    quantitative: list[dict[str, object]] = []
    auxiliary: dict[str, dict[str, list[dict[str, object]]]] = defaultdict(
        lambda: defaultdict(list)
    )
    freetext_list: list[dict[str, object]] = []

    for row in rows:
        payload = row.model_dump()
        if row.row_kind == "quantitative":
            quantitative.append(_strip_none_floats(payload, _quant_yaml_keys()))
        elif row.row_kind == "auxiliary_distribution":
            # Schema validator (AxisSummaryRow._row_kind_field_consistency)
            # guarantees source_col + option are populated for this row_kind;
            # the extra check here is for type narrowing (mypy/pyright).
            if row.source_col is None or row.option is None:
                raise ValueError(
                    "AxisSummaryRow row_kind='auxiliary_distribution' requires "
                    f"source_col + option (axis_key={row.axis_key!r})."
                )
            auxiliary[row.axis_key][row.source_col].append(
                {
                    "option": row.option,
                    "count": row.count,
                    "percentage": (
                        round(row.percentage, _FLOAT_PRECISION)
                        if row.percentage is not None
                        else None
                    ),
                    "n_responded": row.n_responded,
                    "n_cohort": row.n_cohort,
                }
            )
        else:  # freetext_summary
            freetext_list.append(_strip_none_floats(payload, _freetext_yaml_keys()))

    aux_yaml: dict[str, list[dict[str, object]]] = {}
    for axis_key in sorted(auxiliary):
        aux_yaml[axis_key] = [
            {"source_col": source_col, "options": options}
            for source_col, options in sorted(auxiliary[axis_key].items())
        ]

    return {
        "quantitative_axes": quantitative,
        "auxiliary_distributions": aux_yaml,
        "freetext_summaries": freetext_list,
    }


def _quant_yaml_keys() -> tuple[str, ...]:
    return (
        "axis_key",
        "n",
        "n_items",
        "mean_raw",
        "std_raw",
        "p25",
        "p50",
        "p75",
        "cronbach_alpha",
        "reliability_label",
    )


def _freetext_yaml_keys() -> tuple[str, ...]:
    return (
        "axis_key",
        "n_responses",
        "n_categorized",
        "dictionary_match_rate",
        "mean_negativity",
        "top_emotion_distribution",
    )


def _strip_none_floats(payload: dict[str, object], keys: tuple[str, ...]) -> dict[str, object]:
    """Build a YAML-friendly dict with floats rounded + only the listed keys."""
    out: dict[str, object] = {}
    for k in keys:
        v = payload.get(k)
        if isinstance(v, float):
            out[k] = round(v, _FLOAT_PRECISION)
        else:
            out[k] = v
    return out


__all__ = [
    "write_axis_summary",
    "write_factor_scores_long",
]
