"""AxisSummaryRow — axis-level summary export (M8 in v0.1.1 data-model).

Single Pydantic model whose ``row_kind`` discriminator picks one of three
shapes:

- ``quantitative`` — one row per quantitative axis (8 rows total). Carries
  ``n / n_items / mean_raw / std_raw / p25 / p50 / p75 / cronbach_alpha /
  reliability_label``.
- ``auxiliary_distribution`` — one row per (auxiliary group, source column,
  option) tuple. Carries ``source_col / option / count / percentage /
  n_responded / n_cohort`` per FR-010 (response-rate base).
- ``freetext_summary`` — one row per freetext area (Q61, Q62). Carries
  ``n_responses / n_categorized / dictionary_match_rate / mean_negativity /
  top_emotion_distribution``.

CSV serialisation leaves unrelated fields blank; YAML serialisation can
re-fold by row_kind into separate sub-trees if operator-friendlier output
is needed.

Spec: 003-needs-map-v0-1-1/data-model.md §8.
"""

from __future__ import annotations

from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, model_validator

ReliabilityLabel = Literal["high", "medium", "low", "N/A — single/double item"]
RowKind = Literal["quantitative", "auxiliary_distribution", "freetext_summary"]


class AxisSummaryRow(BaseModel):
    """Discriminator-driven axis-level summary row."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    row_kind: RowKind
    axis_key: str  # 8 quant key OR auxiliary group key OR freetext area key

    # quantitative-only fields
    n: int | None = None
    n_items: int | None = None
    mean_raw: float | None = None
    std_raw: float | None = None
    p25: float | None = None
    p50: float | None = None
    p75: float | None = None
    cronbach_alpha: float | None = None
    reliability_label: ReliabilityLabel | None = None

    # auxiliary_distribution-only fields (FR-010 response-rate base)
    source_col: str | None = None
    option: str | None = None
    count: int | None = None
    percentage: float | None = None
    n_responded: int | None = None
    n_cohort: int | None = None

    # freetext_summary-only fields
    n_responses: int | None = None
    n_categorized: int | None = None
    dictionary_match_rate: float | None = None
    mean_negativity: float | None = None
    top_emotion_distribution: dict[str, int] | None = None

    @model_validator(mode="after")
    def _row_kind_field_consistency(self) -> Self:
        """Each row_kind requires its own field block; cross-block fields must be None.

        Quantitative rows MUST have all of ``n / n_items / mean_raw / std_raw /
        p25 / p50 / p75``; ``cronbach_alpha`` may be None when n_items < 3 but
        ``reliability_label`` MUST be set.

        Auxiliary distribution rows MUST have ``source_col / option / count /
        percentage / n_responded / n_cohort``.

        Freetext summary rows MUST have ``n_responses`` (all other freetext-
        only fields are optional but at least n_responses must be set).
        """
        kind = self.row_kind
        quant_required = (
            "n",
            "n_items",
            "mean_raw",
            "std_raw",
            "p25",
            "p50",
            "p75",
            "reliability_label",
        )
        aux_required = (
            "source_col",
            "option",
            "count",
            "percentage",
            "n_responded",
            "n_cohort",
        )
        freetext_required = ("n_responses",)

        all_typed_fields = (
            quant_required,
            aux_required,
            freetext_required,
        )

        if kind == "quantitative":
            missing = [f for f in quant_required if getattr(self, f) is None]
            if missing:
                raise ValueError(
                    f"AxisSummaryRow: row_kind='quantitative' requires fields "
                    f"{list(quant_required)}; missing: {missing}."
                )
            forbidden = [
                f for f in aux_required + freetext_required if getattr(self, f) is not None
            ]
            # ``top_emotion_distribution`` is freetext-only too
            if self.top_emotion_distribution is not None:
                forbidden.append("top_emotion_distribution")
            if forbidden:
                raise ValueError(
                    f"AxisSummaryRow: row_kind='quantitative' must not populate "
                    f"non-quantitative fields: {forbidden}."
                )
        elif kind == "auxiliary_distribution":
            missing = [f for f in aux_required if getattr(self, f) is None]
            if missing:
                raise ValueError(
                    f"AxisSummaryRow: row_kind='auxiliary_distribution' requires "
                    f"fields {list(aux_required)}; missing: {missing}."
                )
            forbidden = [
                f for f in quant_required + freetext_required if getattr(self, f) is not None
            ]
            if self.top_emotion_distribution is not None:
                forbidden.append("top_emotion_distribution")
            if forbidden:
                raise ValueError(
                    f"AxisSummaryRow: row_kind='auxiliary_distribution' must not "
                    f"populate non-distribution fields: {forbidden}."
                )
            # percentage [0, 100], counts ≥ 0 (allow zero options for stable headers)
            if self.percentage is not None and not (0.0 <= self.percentage <= 100.0):
                raise ValueError(f"AxisSummaryRow: percentage={self.percentage} out of [0, 100].")
            if (
                self.n_responded is not None
                and self.n_cohort is not None
                and self.n_responded > self.n_cohort
            ):
                raise ValueError(
                    f"AxisSummaryRow: n_responded={self.n_responded} > n_cohort={self.n_cohort}."
                )
        elif kind == "freetext_summary":
            missing = [f for f in freetext_required if getattr(self, f) is None]
            if missing:
                raise ValueError(
                    f"AxisSummaryRow: row_kind='freetext_summary' requires fields "
                    f"{list(freetext_required)}; missing: {missing}."
                )
            forbidden = [f for f in quant_required + aux_required if getattr(self, f) is not None]
            if forbidden:
                raise ValueError(
                    f"AxisSummaryRow: row_kind='freetext_summary' must not populate "
                    f"non-freetext fields: {forbidden}."
                )
        else:  # pragma: no cover — Literal guards this branch
            raise AssertionError(f"unhandled row_kind={kind!r}")

        # silence the unused tuple — keeps the audit list visible to readers
        _ = all_typed_fields
        return self
