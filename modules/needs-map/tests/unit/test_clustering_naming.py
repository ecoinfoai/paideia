"""Unit tests for cluster naming (T068, FR-013)."""

from __future__ import annotations

import pandas as pd
import pytest


def _centroids() -> pd.DataFrame:
    """3 clusters × 6 axes; cluster 0 has highest motivation + lowest interest."""
    return pd.DataFrame(
        {
            "motivation": [6.0, 4.0, 2.0],
            "anxiety": [3.0, 5.5, 4.0],
            "self_efficacy": [5.0, 4.0, 3.0],
            "interest": [2.0, 4.0, 5.5],
            "prior_knowledge": [4.0, 3.0, 2.0],
            "life_context": [3.0, 4.0, 4.0],
        }
    )


_KOREAN_LABELS = {
    "motivation": "동기",
    "anxiety": "불안",
    "self_efficacy": "자기효능",
    "interest": "흥미",
    "prior_knowledge": "사전지식",
    "life_context": "생활맥락",
}


def test_name_clusters_rule_picks_highest_lowest_axis() -> None:
    from needs_map.clustering.naming import name_clusters_rule

    centroids = _centroids()
    names = name_clusters_rule(centroids, _KOREAN_LABELS)
    # cluster 0: highest motivation (6), lowest interest (2) → "고동기·저흥미형"
    assert "동기" in names[0]
    assert "흥미" in names[0]
    assert "고" in names[0]
    assert "저" in names[0]


def test_name_clusters_rule_returns_one_label_per_cluster() -> None:
    from needs_map.clustering.naming import name_clusters_rule

    centroids = _centroids()
    names = name_clusters_rule(centroids, _KOREAN_LABELS)
    assert set(names.keys()) == {0, 1, 2}
    assert all(isinstance(label, str) and label for label in names.values())


def test_name_clusters_orchestrator_returns_rule_when_no_llm_client() -> None:
    """compose_cluster_names with llm_client=None → naming_source='rule'."""
    from needs_map.clustering.naming import name_clusters
    from needs_map.llm.fallback import LLMCallTracker

    centroids = _centroids()
    tracker = LLMCallTracker()
    names, source = name_clusters(
        centroids,
        axis_labels_kr=_KOREAN_LABELS,
        llm_client=None,
        llm_tracker=tracker,
    )
    assert source == "rule"
    assert set(names.keys()) == {0, 1, 2}
    assert tracker.to_stats() == []  # no LLM calls attempted


def test_name_clusters_orchestrator_falls_back_on_llm_failure() -> None:
    """LLM client present but call fails → naming_source='llm_fallback' + tracker counts."""
    from needs_map.clustering.naming import name_clusters
    from needs_map.llm.fallback import LLMCallTracker

    class _FakeFailingClient:
        class _Chat:
            class _Completions:
                def create(self, **_: object) -> object:
                    import httpx

                    raise httpx.TimeoutException("simulated timeout")

            completions = _Completions()

        chat = _Chat()

    tracker = LLMCallTracker()
    names, source = name_clusters(
        _centroids(),
        axis_labels_kr=_KOREAN_LABELS,
        llm_client=_FakeFailingClient(),
        llm_tracker=tracker,
        llm_model="claude-sonnet-4-6",
        llm_retries=0,
    )
    assert source == "llm_fallback"
    # Rule labels still cover all cluster_ids
    assert set(names.keys()) == {0, 1, 2}
    # Tracker recorded the failure
    stats = tracker.to_stats()
    assert len(stats) == 1
    assert stats[0].site == "cluster_naming"
    assert stats[0].failure_kinds.get("timeout", 0) == 3  # 3 clusters → 3 failed calls


def test_name_clusters_orchestrator_succeeds_with_llm_client() -> None:
    """LLM client returns ClusterNameOut(label=...) → naming_source='llm'."""
    from needs_map.clustering.naming import ClusterNameOut, name_clusters
    from needs_map.llm.fallback import LLMCallTracker

    class _FakeOkClient:
        class _Chat:
            class _Completions:
                def __init__(self) -> None:
                    self.calls = 0

                def create(self, **_: object) -> ClusterNameOut:
                    self.calls += 1
                    return ClusterNameOut(label=f"LLM_label_{self.calls}")

            completions = _Completions()

        chat = _Chat()

    tracker = LLMCallTracker()
    names, source = name_clusters(
        _centroids(),
        axis_labels_kr=_KOREAN_LABELS,
        llm_client=_FakeOkClient(),
        llm_tracker=tracker,
        llm_model="claude-sonnet-4-6",
        llm_retries=0,
    )
    assert source == "llm"
    assert set(names.keys()) == {0, 1, 2}
    for label in names.values():
        assert label.startswith("LLM_label_")
    stats = tracker.to_stats()
    assert stats[0].succeeded == 3


def test_name_clusters_rejects_empty_centroids() -> None:
    from needs_map.clustering.naming import name_clusters_rule

    with pytest.raises(ValueError, match="centroid"):
        name_clusters_rule(pd.DataFrame(), _KOREAN_LABELS)
