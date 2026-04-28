"""Fallback wrapper around ``analyze_sentiment`` [T055].

US6 fallback policy (FR-026 + spec L114): RoBERTa unavailability is a
first-class operational mode, not an error. ``analyze_with_fallback``
runs the analyzer when ``enabled=True`` and the runtime is intact;
otherwise it returns missing ``SentimentResult`` instances and a
structured ``FallbackReport`` so the caller can populate
``manifest.sentiment.fallback_reason``.

Three failure modes (research §R-12):
- ``torch-unavailable`` — torch / transformers ImportError.
- ``model-unavailable`` — torch present but the kote weights are not
  reachable (offline + cache miss).
- ``cli-disabled`` — operator passed ``--no-roberta``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from .sentiment import RobertaUnavailableError, SentimentResult, analyze_sentiment

FallbackReason = Literal[
    "torch-unavailable",
    "model-unavailable",
    "cli-disabled",
]


@dataclass(frozen=True)
class FallbackReport:
    """Per-run sentiment status threaded into ``manifest.sentiment``.

    ``enabled`` mirrors the CLI/--no-roberta flag; ``fallback_reason``
    carries the categorical cause when ``enabled=False`` or when the
    primary path raised. ``n_attempted/n_succeeded/n_fallback`` are
    counters the caller surfaces in the manifest.
    """

    enabled: bool
    model_id: str | None
    fallback_reason: FallbackReason | None
    n_attempted: int
    n_succeeded: int
    n_fallback: int


def analyze_with_fallback(
    texts: list[str],
    *,
    enabled: bool,
    model_id: str = "searle-j/kote_for_easygoing_people",
) -> tuple[list[SentimentResult], FallbackReport]:
    """Run sentiment analysis with categorical fallback on RoBERTa errors.

    Args:
        texts: Redacted Korean strings. Empty strings are excluded from
            ``n_attempted`` (the analyzer never sees them) — only
            non-empty texts count as a sentiment "attempt".
        enabled: ``False`` short-circuits to ``cli-disabled`` fallback.
            Even on the disabled branch ``n_attempted`` matches the
            non-empty input count so ``SentimentRunInfo`` V1
            (``n_succeeded + n_fallback ≤ n_attempted``) holds.
        model_id: Hugging Face hub identifier.

    Returns:
        ``(results, report)`` — ``results`` is aligned to ``texts``;
        ``report.enabled`` and ``report.fallback_reason`` describe what
        actually happened.
    """
    non_empty = [t for t in texts if t and t.strip()]
    n_attempted = len(non_empty)

    if not enabled:
        return _all_missing(texts), FallbackReport(
            enabled=False,
            model_id=None,
            fallback_reason="cli-disabled",
            n_attempted=n_attempted,
            n_succeeded=0,
            n_fallback=n_attempted,
        )

    try:
        results = analyze_sentiment(texts, model_id=model_id)
    except RobertaUnavailableError as exc:
        reason: FallbackReason = (
            "torch-unavailable"
            if "torch / transformers not installed" in str(exc)
            else "model-unavailable"
        )
        return _all_missing(texts), FallbackReport(
            enabled=False,
            model_id=None,
            fallback_reason=reason,
            n_attempted=n_attempted,
            n_succeeded=0,
            n_fallback=n_attempted,
        )

    n_succeeded = sum(1 for r in results if r.negativity is not None)
    return results, FallbackReport(
        enabled=True,
        model_id=model_id,
        fallback_reason=None,
        n_attempted=n_attempted,
        n_succeeded=n_succeeded,
        n_fallback=n_attempted - n_succeeded,
    )


def _all_missing(texts: list[str]) -> list[SentimentResult]:
    """Build a list of empty ``SentimentResult`` aligned to ``texts``."""
    return [SentimentResult() for _ in texts]


__all__ = [
    "FallbackReason",
    "FallbackReport",
    "analyze_with_fallback",
]
