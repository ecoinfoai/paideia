"""LLM client wrapper around instructor + Anthropic (T025, FR-LLM-001/002).

Provides ``make_client`` and ``call_with_response_model`` so all needs-map LLM
sites (cluster naming T073, free-text T096, coaching T103, report tone T100)
go through one place. ``LLMCallOutcome`` is a needs-map-internal Pydantic model
(non-shared) carrying the success/failure_kind enum that the LLMCallTracker
later folds into ``NeedsMapManifest.llm_calls`` (FR-023).

T025 deliberately keeps the function signature explicit (no defaults on
``provider`` / ``model`` / ``timeout``) per Phase 2 design alignment §6
Stage-2 silent-skip mitigation: pipeline.py must always pass NeedsMapArgs
fields by name so a missing CLI flag never silently becomes a hard-coded
default.
"""

from __future__ import annotations

from typing import Literal

import instructor
from pydantic import BaseModel, ConfigDict


class LLMCallOutcome(BaseModel):
    """Single-call result enum carrier for LLMCallTracker accounting."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    succeeded: bool
    failure_kind: Literal["timeout", "rate_limit", "auth", "pii_block", "other"] | None = None


def make_client(provider: str, model: str, timeout: float) -> instructor.Instructor:
    """Construct an instructor-wrapped LLM client.

    Args:
        provider: Provider identifier. Only ``"anthropic"`` is implemented in
            v0.1.0 (cli.md). ``"openai"`` raises NotImplementedError so the
            CLI argument surface remains forward-compatible without silent
            misroute (qa Stage-2 candidate 1).
        model: Model identifier (e.g. ``"claude-sonnet-4-6"``).
        timeout: Per-call timeout in seconds (FR-LLM-002 default 30 lives at
            CLI default; this signature has no default to force explicit
            propagation).

    Returns:
        instructor-wrapped client suitable for ``call_with_response_model``.

    Raises:
        NotImplementedError: For non-anthropic providers in v0.1.0.
        ValueError: For empty model id or non-positive timeout.
    """
    if not isinstance(provider, str) or not provider:
        raise ValueError(f"make_client: empty/invalid provider={provider!r}.")
    if not isinstance(model, str) or not model:
        raise ValueError(f"make_client: empty/invalid model={model!r}.")
    if not isinstance(timeout, int | float) or timeout <= 0:
        raise ValueError(f"make_client: timeout must be > 0, got {timeout!r}.")

    if provider != "anthropic":
        raise NotImplementedError(
            f"make_client: provider={provider!r} not implemented in v0.1.0; "
            f"only 'anthropic' is supported."
        )

    import anthropic
    import instructor

    raw_client = anthropic.Anthropic(timeout=timeout)
    return instructor.from_anthropic(raw_client)


def call_with_response_model(
    client: instructor.Instructor,
    response_model: type[BaseModel],
    messages: list[dict],
    retries: int,
    *,
    model: str,
    max_tokens: int = 1024,
) -> tuple[BaseModel | None, LLMCallOutcome]:
    """Invoke the LLM expecting a Pydantic-shaped response.

    Args:
        client: instructor-wrapped client returned by :func:`make_client`.
        response_model: Pydantic ``BaseModel`` subclass that the call must
            populate (instructor enforces structured output).
        messages: Anthropic-style chat ``messages`` payload. Caller MUST have
            already passed every text body through :func:`pii.redact`
            (FR-PII-002) — this function does not re-redact.
        retries: Maximum retries on transient failure (FR-LLM-002 default 1
            lives at the CLI; required-for here so caller is explicit per
            qa Stage-2 candidate 3).
        model: Model id (kept as keyword-only so caller never accidentally
            mixes it into positional args).
        max_tokens: Upper bound on output tokens.

    Returns:
        ``(parsed_model_or_None, LLMCallOutcome)``. On any failure the parsed
        value is ``None`` and ``LLMCallOutcome.failure_kind`` carries the
        category for manifest accounting; the caller invokes its rule/template
        fallback path.
    """
    if not isinstance(retries, int) or retries < 0:
        raise ValueError(f"call_with_response_model: retries must be ≥ 0, got {retries!r}.")
    if not messages:
        raise ValueError("call_with_response_model: messages must be non-empty.")

    import anthropic
    import httpx

    try:
        result = client.chat.completions.create(
            model=model,
            response_model=response_model,
            messages=messages,
            max_retries=retries,
            max_tokens=max_tokens,
        )
        return result, LLMCallOutcome(succeeded=True, failure_kind=None)
    except httpx.TimeoutException:
        return None, LLMCallOutcome(succeeded=False, failure_kind="timeout")
    except anthropic.AuthenticationError:
        return None, LLMCallOutcome(succeeded=False, failure_kind="auth")
    except anthropic.RateLimitError:
        return None, LLMCallOutcome(succeeded=False, failure_kind="rate_limit")
    except Exception:
        # Catch-all is intentional and *not* silent — the LLMCallOutcome
        # carries failure_kind="other" into the manifest so operators can
        # see that an uncategorized exception occurred (adversary H-4).
        return None, LLMCallOutcome(succeeded=False, failure_kind="other")
