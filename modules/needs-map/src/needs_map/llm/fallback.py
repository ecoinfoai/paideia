"""LLM call accounting + fallback decorator (T026, FR-LLM-002 / FR-023).

``LLMCallTracker`` accumulates per-site counters and failure_kind histograms
that pipeline.py later folds into ``NeedsMapManifest.llm_calls``. It also
records ``pii_redaction_validated`` so the manifest can carry a single
boolean attesting that every LLM payload passed PII validation
(adversary H-8 mitigation: silent True is never possible — any one False
flips the running flag to False permanently).
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Literal

from paideia_shared.schemas import LLMCallStat

from .client import LLMCallOutcome

LLMSite = Literal["cluster_naming", "free_text", "coaching", "report_tone"]


@dataclass
class _SiteCounters:
    attempted: int = 0
    succeeded: int = 0
    fallback: int = 0
    failure_kinds: dict[str, int] = field(default_factory=dict)
    failure_student_ids: list[str] = field(default_factory=list)


class LLMCallTracker:
    """Per-pipeline-run accounting context for every LLM call.

    Use one instance per ``run_needs_map`` invocation; each phase that calls
    LLM threads the same tracker through and invokes :meth:`record` after the
    call returns. :meth:`to_stats` produces the
    ``NeedsMapManifest.llm_calls`` payload at manifest-write time.
    """

    def __init__(self) -> None:
        self._sites: dict[str, _SiteCounters] = {}
        self._pii_all_validated: bool = True

    def record(
        self,
        site: LLMSite,
        outcome: LLMCallOutcome,
        student_id: str | None = None,
    ) -> None:
        """Record a single LLM call's outcome.

        Args:
            site: One of the four allowed LLM sites.
            outcome: ``LLMCallOutcome`` returned by
                :func:`needs_map.llm.client.call_with_response_model`.
            student_id: Optional 10-digit student id for sites whose failures
                are tied to a specific learner (free_text, coaching).
        """
        counters = self._sites.setdefault(site, _SiteCounters())
        counters.attempted += 1
        if outcome.succeeded:
            counters.succeeded += 1
            return
        counters.fallback += 1
        kind = outcome.failure_kind or "other"
        counters.failure_kinds[kind] = counters.failure_kinds.get(kind, 0) + 1
        if student_id is not None:
            counters.failure_student_ids.append(student_id)
        if kind == "pii_block":
            self._pii_all_validated = False

    def record_pii_validation(self, validated: bool) -> None:
        """Fold a PII redaction validation result into the running AND.

        Call this for *every* redaction performed (whether the call proceeded
        or was blocked). Once any False arrives the manifest field stays False
        for the remainder of the run.
        """
        if not validated:
            self._pii_all_validated = False

    @property
    def pii_redaction_validated(self) -> bool:
        return self._pii_all_validated

    def to_stats(self) -> list[LLMCallStat]:
        """Convert accumulated counters to the manifest payload.

        Sites with zero attempts are omitted (no noise in the manifest).
        Counter ordering is fixed by LLMSite Literal order for reproducibility.
        """
        ordered: list[LLMCallStat] = []
        for site_name in ("cluster_naming", "free_text", "coaching", "report_tone"):
            counters = self._sites.get(site_name)
            if counters is None or counters.attempted == 0:
                continue
            ordered.append(
                LLMCallStat(
                    site=site_name,  # type: ignore[arg-type]
                    attempted=counters.attempted,
                    succeeded=counters.succeeded,
                    fallback=counters.fallback,
                    failure_kinds=dict(counters.failure_kinds),  # type: ignore[arg-type]
                    failure_student_ids=list(counters.failure_student_ids),
                )
            )
        return ordered


def with_fallback(
    fallback_fn: Callable[..., object],
) -> Callable[[Callable[..., object]], Callable[..., object]]:
    """Decorator: on LLM failure, return ``fallback_fn(*args, **kwargs)`` instead.

    Wrapped function is expected to return ``(result_or_None, LLMCallOutcome)``.
    The decorator inspects the outcome — on ``succeeded=False`` it invokes the
    fallback and returns its result. Caller still sees the outcome via the
    ``LLMCallTracker`` it threaded through (the tracker records BEFORE this
    decorator chooses the return value).

    Args:
        fallback_fn: Pure function with the same positional/keyword signature
            as the wrapped function except it returns the fallback value
            directly (no outcome tuple).
    """

    def decorator(
        primary: Callable[..., object],
    ) -> Callable[..., object]:
        def wrapper(*args: object, **kwargs: object) -> object:
            value, outcome = primary(*args, **kwargs)  # type: ignore[misc]
            if isinstance(outcome, LLMCallOutcome) and outcome.succeeded:
                return value
            return fallback_fn(*args, **kwargs)

        return wrapper

    return decorator
