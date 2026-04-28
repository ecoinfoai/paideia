"""Fallback path coverage for the v0.1.1 RoBERTa sentiment helper [T052].

Three operational scenarios from FR-026 + research §R-12:

(a) ``torch`` import raises ``ImportError`` (operator missing the
    optional ``roberta`` extra) → results carry no scores +
    ``FallbackReport.fallback_reason == 'torch-unavailable'``.
(b) Model load raises ``OSError`` (kote weights cache missing while
    offline) → fallback reason ``'model-unavailable'``.
(c) Operator passes ``--no-roberta`` → ``analyze_with_fallback`` is
    called with ``enabled=False`` → fallback reason ``'cli-disabled'``;
    no torch import attempted.

Tests do NOT need the kote cache; ``ImportError`` / ``OSError`` are
synthesised via monkeypatch. The mark ``roberta`` is intentionally NOT
applied so they run by default (they are *fallback* coverage, not
positive-path inference).

Spec: 003-needs-map-v0-1-1/tasks.md T052; FR-026.
"""

from __future__ import annotations

import sys

import pytest


def test_cli_disabled_short_circuits_without_torch_import(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``enabled=False`` MUST NOT trigger any torch import (silent disable防御)."""
    from needs_map.free_text.roberta_fallback import analyze_with_fallback

    # Sentinel: if analyze_sentiment ever runs, this raise will surface.
    def _boom(*_args: object, **_kwargs: object) -> object:
        raise AssertionError("analyze_sentiment must not run when enabled=False")

    monkeypatch.setattr(
        "needs_map.free_text.roberta_fallback.analyze_sentiment", _boom
    )

    results, report = analyze_with_fallback(
        ["수업이 막막해요", "기대돼요"],
        enabled=False,
    )
    assert len(results) == 2
    assert all(r.negativity is None for r in results)
    assert report.enabled is False
    assert report.model_id is None
    assert report.fallback_reason == "cli-disabled"
    # Fallback paths still set n_attempted = #non-empty texts so
    # SentimentRunInfo V1 (n_succeeded + n_fallback ≤ n_attempted) holds.
    assert report.n_attempted == 2
    assert report.n_succeeded == 0
    assert report.n_fallback == 2


def test_torch_unavailable_reports_fallback_reason(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """ImportError on torch → ``fallback_reason='torch-unavailable'``."""
    from needs_map.free_text.roberta_fallback import analyze_with_fallback
    from needs_map.free_text.sentiment import RobertaUnavailableError

    def _raise_torch_unavailable(*_args: object, **_kwargs: object) -> object:
        raise RobertaUnavailableError(
            "torch / transformers not installed — install via `uv sync ...`."
        )

    monkeypatch.setattr(
        "needs_map.free_text.roberta_fallback.analyze_sentiment",
        _raise_torch_unavailable,
    )

    results, report = analyze_with_fallback(
        ["수업이 막막해요"], enabled=True
    )
    assert len(results) == 1
    assert results[0].negativity is None
    assert report.fallback_reason == "torch-unavailable"
    assert report.enabled is False  # disabled in the report after fallback


def test_model_unavailable_reports_fallback_reason(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """RobertaUnavailableError without 'torch / transformers' substring →
    ``fallback_reason='model-unavailable'``."""
    from needs_map.free_text.roberta_fallback import analyze_with_fallback
    from needs_map.free_text.sentiment import RobertaUnavailableError

    def _raise_model_unavailable(*_args: object, **_kwargs: object) -> object:
        raise RobertaUnavailableError(
            "could not load model_id — model cache missing and offline."
        )

    monkeypatch.setattr(
        "needs_map.free_text.roberta_fallback.analyze_sentiment",
        _raise_model_unavailable,
    )

    results, report = analyze_with_fallback(
        ["수업이 막막해요"], enabled=True
    )
    assert report.fallback_reason == "model-unavailable"
    assert report.enabled is False
    # Single non-empty text → n_attempted=1; n_fallback=1 (V1 holds).
    assert report.n_attempted == 1
    assert report.n_fallback == 1


def test_torch_import_error_synthesised_via_sys_modules(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """End-to-end fallback when the actual torch import fails.

    Uses ``sys.modules`` injection to make ``import torch`` raise
    ImportError inside ``analyze_sentiment``. This exercises the real
    path (no monkeypatched analyze_sentiment) so the wiring between
    ``analyze_with_fallback`` and ``analyze_sentiment`` is verified.
    """
    from needs_map.free_text.roberta_fallback import analyze_with_fallback

    # Force ``import torch`` to fail. Reset cached module first.
    monkeypatch.setitem(sys.modules, "torch", None)

    results, report = analyze_with_fallback(["테스트"], enabled=True)
    assert results[0].negativity is None
    assert report.fallback_reason == "torch-unavailable"
    assert report.enabled is False


def test_negative_label_subset_sha256_is_stable() -> None:
    """``negative_label_subset_sha256`` MUST be deterministic across calls."""
    from needs_map.free_text.sentiment import negative_label_subset_sha256

    a = negative_label_subset_sha256()
    b = negative_label_subset_sha256()
    assert a == b
    assert len(a) == 64  # hex sha256


def test_negative_labels_has_sixteen_entries() -> None:
    """Spec FR-026: ``NEGATIVE_LABELS`` MUST be exactly 16 strings (research §R-02)."""
    from needs_map.free_text.sentiment import NEGATIVE_LABELS

    assert isinstance(NEGATIVE_LABELS, tuple)
    assert len(NEGATIVE_LABELS) == 16
    assert len(set(NEGATIVE_LABELS)) == 16  # no dupes
