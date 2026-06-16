"""Cluster naming — rule-based + optional LLM polish (T073, FR-013, research D6).

Three-way orchestrator (research D6, Phase 2 §4.1 PII safety):
  - rule (default): name_clusters_rule produces "고{topAxisKR}·저{bottomAxisKR}형"
  - llm: when ``llm_client`` is provided AND every per-cluster call succeeds,
    the LLM-suggested label replaces the rule label.
  - llm_fallback: any LLM call failure flips the *entire* cluster set back to
    the rule labels (adversary P-6 — no mixed naming_source within a single
    report; manifest carries failure_kind counts).

Spec FR-013: rule by default; LLM activates only when client is given AND
every call succeeds; failure routes to fallback with manifest record.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Literal

import pandas as pd
from pydantic import BaseModel, ConfigDict, Field

from ..llm.client import LLMCallOutcome, call_with_response_model
from ..llm.fallback import LLMCallTracker

if TYPE_CHECKING:
    import instructor


class ClusterNameOut(BaseModel):
    """instructor response model for the LLM cluster-naming hook (research D6)."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    label: str = Field(min_length=1, max_length=20)


def name_clusters_rule(centroids: pd.DataFrame, axis_labels_kr: dict[str, str]) -> dict[int, str]:
    """Rule-based cluster names — "고{maxAxisKR}·저{minAxisKR}형".

    Args:
        centroids: One row per cluster_id (0..k-1), columns are axis names.
            Must be non-empty.
        axis_labels_kr: Mapping ``axis_name -> Korean label`` (e.g.
            ``{"motivation": "동기"}``). Missing axes raise KeyError because
            the naming policy depends on consistent vocabulary.

    Returns:
        ``{cluster_id: rule_label}`` covering every cluster_id in centroids.

    Raises:
        ValueError: If centroids is empty.
        KeyError: If centroid columns lack Korean labels in axis_labels_kr.
    """
    if centroids.empty:
        raise ValueError("name_clusters_rule: centroid frame must be non-empty.")

    names: dict[int, str] = {}
    for cluster_id, row in centroids.iterrows():
        # idxmax / idxmin yield axis names; convert to Korean via dict.
        top_axis = row.idxmax()
        bottom_axis = row.idxmin()
        top_kr = axis_labels_kr[top_axis]
        bottom_kr = axis_labels_kr[bottom_axis]
        names[int(cluster_id)] = f"고{top_kr}·저{bottom_kr}형"
    return names


def _llm_label_for_cluster(
    centroid_row: pd.Series,
    axis_labels_kr: dict[str, str],
    llm_client: instructor.Instructor,
    llm_tracker: LLMCallTracker,
    llm_model: str,
    llm_retries: int,
) -> tuple[str | None, LLMCallOutcome]:
    """Single-cluster LLM call. Returns (label_or_None, outcome)."""
    summary_lines = [
        f"- {axis_labels_kr.get(axis, axis)}: {value:+.2f}" for axis, value in centroid_row.items()
    ]
    prompt = (
        "다음은 한 학생 군집의 표준화된 의미축 평균 점수입니다 (z-score). "
        "이 군집을 한국어로 짧게(2~6자) 라벨링하세요. "
        "예: '고동기·저자습형'.\n\n" + "\n".join(summary_lines)
    )
    messages = [{"role": "user", "content": prompt}]
    result, outcome = call_with_response_model(
        llm_client,
        ClusterNameOut,
        messages,
        retries=llm_retries,
        model=llm_model,
    )
    if isinstance(result, ClusterNameOut):
        return result.label, outcome
    return None, outcome


def name_clusters(
    centroids: pd.DataFrame,
    axis_labels_kr: dict[str, str],
    llm_client: instructor.Instructor | None,
    llm_tracker: LLMCallTracker,
    *,
    llm_model: str = "claude-sonnet-4-6",
    llm_retries: int = 1,
) -> tuple[dict[int, str], Literal["rule", "llm", "llm_fallback"]]:
    """Orchestrate rule → optional LLM → fallback (FR-013).

    Args:
        centroids: One row per cluster_id, columns = axis names.
        axis_labels_kr: Per-axis Korean label map.
        llm_client: instructor client or None. None → rule path only.
        llm_tracker: per-run accountancy threaded by pipeline.py.
        llm_model: model id to pass through to call_with_response_model.
        llm_retries: per-call retry count (FR-LLM-002 default 1).

    Returns:
        ``(names, naming_source)`` where naming_source is one of
        ``"rule"``, ``"llm"``, ``"llm_fallback"``.
    """
    rule_names = name_clusters_rule(centroids, axis_labels_kr)
    if llm_client is None:
        return rule_names, "rule"

    llm_names: dict[int, str] = {}
    any_failure = False
    for cluster_id, row in centroids.iterrows():
        cid_int = int(cluster_id)
        label, outcome = _llm_label_for_cluster(
            row,
            axis_labels_kr=axis_labels_kr,
            llm_client=llm_client,
            llm_tracker=llm_tracker,
            llm_model=llm_model,
            llm_retries=llm_retries,
        )
        llm_tracker.record("cluster_naming", outcome)
        if outcome.succeeded and label is not None:
            llm_names[cid_int] = label
        else:
            any_failure = True

    if any_failure:
        # Mixed-source naming forbidden (adversary P-6). Fall back to rule labels.
        return rule_names, "llm_fallback"
    return llm_names, "llm"
