"""Missing-value policy (T054, FR-007, M4 V2 invariant).

Two policies, both deterministic:

* ``drop`` — preserve NaN, set missing flag True for those entries.
* ``mean_impute`` — fill NaN with the column mean computed from substantive
  rows; the resulting filled value records ``missing=False`` because the score
  is now substantive (data-model.md M4 V2). When *all* rows are NaN (no mean
  computable) we fall back to leaving NaN in place AND keeping ``missing=True``
  so the M4 V2 invariant (missing=True ⇒ score=None) still holds.

Provenance of the per-axis policy is captured in
``NeedsMapInput.missing_policy_source`` by the pipeline (Phase 2 §3.5).
"""

from __future__ import annotations

from typing import Literal

import pandas as pd

MissingPolicy = Literal["drop", "mean_impute"]


def apply_missing_policy(
    values: pd.Series, policy: MissingPolicy
) -> tuple[pd.Series, pd.Series]:
    """Apply the per-axis missing-value policy and return (resolved, missing_flags).

    Args:
        values: Per-student aggregated axis values (output of ``aggregate_axis``).
            Index MUST be canonical student_id.
        policy: ``"drop"`` keeps NaN as-is and flags True. ``"mean_impute"``
            fills NaN with the substantive mean and flags False. ``"mean_impute"``
            with all-NaN input falls back to drop semantics (NaN + flag True)
            so M4 V2 (missing=True ⇒ score=None) holds.

    Returns:
        ``(resolved_values, missing_flags)`` — both Series share ``values``'s
        index; ``missing_flags`` is bool dtype.

    Raises:
        ValueError: If ``policy`` is not in {"drop", "mean_impute"}.
    """
    if policy not in ("drop", "mean_impute"):
        raise ValueError(
            f"apply_missing_policy: policy={policy!r} not in {{'drop','mean_impute'}}."
        )

    is_missing = values.isna()

    if policy == "drop":
        resolved = values.copy()
        return resolved, is_missing.astype(bool)

    # mean_impute
    substantive = values.dropna()
    if substantive.empty:
        # No mean to impute from — keep NaN, mark missing True (M4 V2 holds).
        resolved = values.copy()
        return resolved, is_missing.astype(bool)
    mean_value = float(substantive.mean())
    resolved = values.fillna(mean_value)
    # Imputed slots become missing=False (M4 V2 invariant: imputed values are scores).
    flags = pd.Series(False, index=values.index, dtype=bool)
    return resolved, flags
