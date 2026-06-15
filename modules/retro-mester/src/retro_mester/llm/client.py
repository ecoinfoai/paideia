"""T053 — Thin LLM backend abstraction for retro-mester insight layer.

Provides a single public function ``generate(prompt, *, mode)`` that calls
either the Anthropic subscription (``claude -p`` wrapper) or the Anthropic
API, and returns ``(text_or_None, failure_kind_or_None)``.

Design constraints:
- ``anthropic`` and ``instructor`` imports are LAZY so the ``off`` path
  never drags in heavy dependencies.
- NEVER raises to the caller — returns ``(None, failure_kind)`` on any error.
- ``mode`` must be ``"subscription"`` or ``"api"``; anything else is an
  internal contract violation (callers must guard before reaching here).
"""

from __future__ import annotations

import subprocess
from typing import Literal

FailureKind = Literal["timeout", "rate_limit", "auth", "other"]

# Model used for retro-mester LLM insight (single constant so it is easy to
# update without touching call sites).
_MODEL = "claude-sonnet-4-6"
_TIMEOUT_SECONDS = 60
_MAX_TOKENS = 1024


def generate(
    prompt: str,
    *,
    mode: str,
) -> tuple[str | None, FailureKind | None]:
    """Call the LLM backend and return the response text.

    Args:
        prompt: Full prompt string to send to the model.
        mode: Backend mode — ``"subscription"`` (claude CLI ``-p``) or
            ``"api"`` (Anthropic SDK direct).

    Returns:
        ``(response_text, None)`` on success.
        ``(None, failure_kind)`` on any failure — NEVER raises.

    Raises:
        Nothing — all exceptions are caught and mapped to failure_kind.
    """
    if mode == "subscription":
        return _generate_subscription(prompt)
    if mode == "api":
        return _generate_api(prompt)
    # Internal contract violation — treat as other failure.
    return None, "other"


# ---------------------------------------------------------------------------
# Backend implementations
# ---------------------------------------------------------------------------


def _generate_subscription(prompt: str) -> tuple[str | None, FailureKind | None]:
    """Call the LLM via the ``claude -p`` subscription wrapper.

    Uses ``subprocess`` to invoke ``claude -p <prompt>`` with a timeout.
    Stdout is captured and returned as the response text.

    Args:
        prompt: Full prompt string.

    Returns:
        ``(text, None)`` on success, ``(None, failure_kind)`` on failure.
    """
    try:
        result = subprocess.run(  # noqa: S603 S607
            ["claude", "-p", prompt],  # noqa: S603 S607
            capture_output=True,
            text=True,
            timeout=_TIMEOUT_SECONDS,
            encoding="utf-8",
        )
        if result.returncode != 0:
            stderr_lower = result.stderr.lower() if result.stderr else ""
            if "auth" in stderr_lower or "unauthorized" in stderr_lower:
                return None, "auth"
            if "rate" in stderr_lower or "limit" in stderr_lower:
                return None, "rate_limit"
            return None, "other"
        text = result.stdout.strip()
        if not text:
            return None, "other"
        return text, None
    except subprocess.TimeoutExpired:
        return None, "timeout"
    except FileNotFoundError:
        # ``claude`` CLI not installed in this environment.
        return None, "other"
    except Exception:  # noqa: BLE001
        return None, "other"


def _generate_api(prompt: str) -> tuple[str | None, FailureKind | None]:
    """Call the LLM via the Anthropic API SDK (lazy import).

    Args:
        prompt: Full prompt string.

    Returns:
        ``(text, None)`` on success, ``(None, failure_kind)`` on failure.
    """
    try:
        import anthropic  # lazy — not imported on off path
    except ImportError:
        return None, "other"

    try:
        client = anthropic.Anthropic(timeout=_TIMEOUT_SECONDS)
        message = client.messages.create(
            model=_MODEL,
            max_tokens=_MAX_TOKENS,
            messages=[{"role": "user", "content": prompt}],
        )
        # Extract text from the first text block.
        text = ""
        for block in message.content:
            if hasattr(block, "text"):
                text = block.text.strip()
                break
        if not text:
            return None, "other"
        return text, None
    except Exception as exc:  # noqa: BLE001
        # Map known Anthropic exception types by name to avoid hard import.
        exc_type = type(exc).__name__
        if "Timeout" in exc_type or "timeout" in exc_type.lower():
            return None, "timeout"
        if "Authentication" in exc_type or "Auth" in exc_type:
            return None, "auth"
        if "RateLimit" in exc_type:
            return None, "rate_limit"
        return None, "other"


__all__ = ["generate", "FailureKind"]
