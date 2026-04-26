"""Apply a DiagnosticMappingConfig to a parsed diagnostic DataFrame."""

from __future__ import annotations

from collections import OrderedDict, defaultdict
from collections.abc import Iterable

import pandas as pd
from paideia_shared.schemas import (
    CourseSlug,
    DiagnosticMappingConfig,
    DiagnosticResponse,
    SemesterCode,
)

from ..normalize import expand_multiselect, normalize_likert


def _column_summary_aggregate(values: Iterable[float], aggregate: str) -> float:
    materialized = [v for v in values if v is not None]
    if not materialized:
        return float("nan")
    if aggregate == "mean":
        return sum(materialized) / len(materialized)
    if aggregate == "sum":
        return sum(materialized)
    raise ValueError(f"apply_mapping: unsupported aggregate={aggregate!r}.")


def _likert_value(text: str | None) -> int | None:
    if text is None or text == "":
        return None
    return normalize_likert(text)


def apply_mapping(
    diagnostic_df: pd.DataFrame,
    mapping: DiagnosticMappingConfig,
    semester: SemesterCode,
    course_slug: CourseSlug,
) -> tuple[
    dict[str, dict[str, float | None]],
    list[DiagnosticResponse],
    dict[str, list[str]],
]:
    """Apply mapping to a diagnostic DataFrame.

    Args:
        diagnostic_df: DataFrame indexed by canonical student_id, with columns
            equal to mapping.columns sources (excluding identity).
        mapping: Validated DiagnosticMappingConfig.
        semester: SemesterCode for emitted DiagnosticResponse rows.
        course_slug: CourseSlug for emitted DiagnosticResponse rows.

    Returns:
        Tuple ``(axis_scores, responses, new_options_by_axis)`` where:
            - axis_scores: ``{student_id: {axis_key: scalar | None}}`` for likert axes
              after the mapping's aggregate function (mean/sum).
            - responses: list[DiagnosticResponse] in long form.
            - new_options_by_axis: multiselect axis → list of option keys observed
              that were not declared in the mapping (empty for v0.1 since options
              are inferred dynamically; preserved for spec Edge Case visibility).

    Raises:
        ValueError: If unrecognized aggregate or unmapped column appears.
        TypeError: If diagnostic_df is not a pd.DataFrame.
    """
    if not isinstance(diagnostic_df, pd.DataFrame):
        raise TypeError(
            f"apply_mapping: expected pd.DataFrame, got {type(diagnostic_df).__name__}."
        )

    likert_axes: dict[str, dict[str, list[float | None]]] = defaultdict(
        lambda: defaultdict(list)
    )
    likert_aggregate_by_axis: dict[str, str] = {}
    multiselect_options: dict[str, list[str]] = defaultdict(list)
    new_options_by_axis: dict[str, list[str]] = defaultdict(list)

    responses: list[DiagnosticResponse] = []

    for column in mapping.columns:
        if column.kind == "identity":
            continue
        if column.source not in diagnostic_df.columns:
            raise ValueError(
                f"apply_mapping: mapping references column {column.source!r} "
                f"absent from diagnostic dataframe."
            )
        axis = column.axis
        if axis is None:
            # MappingColumn V1 already enforces this; keep an explicit raise.
            raise ValueError(
                f"apply_mapping: non-identity column {column.source!r} has axis=None."
            )
        if column.kind == "likert":
            if column.aggregate is not None:
                likert_aggregate_by_axis.setdefault(axis, column.aggregate)
            for student_id, raw_value in diagnostic_df[column.source].items():
                value = _likert_value(raw_value)
                likert_axes[student_id][axis].append(value)
                if value is not None:
                    responses.append(
                        DiagnosticResponse(
                            student_id=str(student_id),
                            semester=semester,
                            course_slug=course_slug,
                            axis=axis,
                            axis_kind="likert",
                            value_int=value,
                            source_column=column.source,
                        )
                    )
        elif column.kind == "multiselect":
            # v0.1: options discovered from data; record all observed options
            # under new_options_by_axis since the mapping does not enumerate them
            # (spec Edge Case: dynamic option growth is preserved in manifest).
            seen_options: list[str] = list(multiselect_options[axis])
            for _student_id, raw_value in diagnostic_df[column.source].items():
                if raw_value is None or raw_value == "":
                    continue
                options = expand_multiselect(str(raw_value))
                for option in options:
                    if option not in seen_options:
                        seen_options.append(option)
                        new_options_by_axis[axis].append(option)
            multiselect_options[axis] = seen_options
            # second pass: emit one-hot rows for each (student, option)
            for student_id, raw_value in diagnostic_df[column.source].items():
                if raw_value is None or raw_value == "":
                    selected: set[str] = set()
                else:
                    selected = set(expand_multiselect(str(raw_value)))
                for option in seen_options:
                    responses.append(
                        DiagnosticResponse(
                            student_id=str(student_id),
                            semester=semester,
                            course_slug=course_slug,
                            axis=axis,
                            axis_kind="multiselect_onehot",
                            option_key=option,
                            value_bool=(option in selected),
                            source_column=column.source,
                        )
                    )
        elif column.kind == "freetext":
            for student_id, raw_value in diagnostic_df[column.source].items():
                text_value = "" if raw_value is None else str(raw_value)
                responses.append(
                    DiagnosticResponse(
                        student_id=str(student_id),
                        semester=semester,
                        course_slug=course_slug,
                        axis=axis,
                        axis_kind="freetext",
                        value_text=text_value,
                        source_column=column.source,
                    )
                )

    # Aggregate likert axes per student
    axis_scores: dict[str, dict[str, float | None]] = {}
    for student_id, axis_values in likert_axes.items():
        per_student: dict[str, float | None] = {}
        for axis, values in axis_values.items():
            non_null = [v for v in values if v is not None]
            if not non_null:
                per_student[axis] = None
                continue
            aggregate = likert_aggregate_by_axis.get(axis)
            if aggregate is None:
                # single-column axis: simple identity (mean of one)
                per_student[axis] = float(non_null[0]) if len(non_null) == 1 else float(
                    sum(non_null) / len(non_null)
                )
            else:
                per_student[axis] = float(_column_summary_aggregate(non_null, aggregate))
        axis_scores[str(student_id)] = per_student

    # Stable, sorted, plain-dict output
    new_options_sorted = OrderedDict(
        (axis, list(options)) for axis, options in new_options_by_axis.items()
    )
    responses_sorted = sorted(
        responses,
        key=lambda r: (
            r.student_id,
            r.axis,
            r.option_key or "",
            r.source_column,
        ),
    )
    axis_scores_sorted = {sid: dict(scores) for sid, scores in sorted(axis_scores.items())}
    return axis_scores_sorted, responses_sorted, dict(new_options_sorted)
