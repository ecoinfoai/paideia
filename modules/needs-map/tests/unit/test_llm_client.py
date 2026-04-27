"""Tests for LLM client + LLMCallOutcome (T029, FR-LLM-001/002).

Anthropic SDK calls are monkeypatched — no live network. Verifies that each
of the 4 documented failure paths (timeout / auth / rate_limit / other) maps
to the correct LLMCallOutcome.failure_kind so manifest accounting is precise.
"""

from __future__ import annotations

import pytest
from needs_map.llm.client import (
    LLMCallOutcome,
    call_with_response_model,
    make_client,
)
from pydantic import BaseModel


class _Out(BaseModel):
    label: str


class _FakeChatCompletions:
    def __init__(self, behavior: str) -> None:
        self.behavior = behavior

    def create(self, **kwargs: object) -> _Out:  # noqa: ARG002
        import anthropic
        import httpx

        if self.behavior == "ok":
            return _Out(label="rule-based name")
        if self.behavior == "timeout":
            raise httpx.TimeoutException("timeout")
        if self.behavior == "auth":
            raise anthropic.AuthenticationError(
                message="bad key",
                response=httpx.Response(401, request=httpx.Request("POST", "http://x")),
                body=None,
            )
        if self.behavior == "rate_limit":
            raise anthropic.RateLimitError(
                message="rate",
                response=httpx.Response(429, request=httpx.Request("POST", "http://x")),
                body=None,
            )
        if self.behavior == "other":
            raise RuntimeError("unexpected")
        raise AssertionError(f"unknown behavior {self.behavior!r}")


class _FakeChat:
    def __init__(self, behavior: str) -> None:
        self.completions = _FakeChatCompletions(behavior)


class _FakeClient:
    def __init__(self, behavior: str) -> None:
        self.chat = _FakeChat(behavior)


_MSG = [{"role": "user", "content": "name this cluster"}]


# --- LLMCallOutcome contract ---


def test_outcome_succeeded_no_failure_kind() -> None:
    o = LLMCallOutcome(succeeded=True)
    assert o.failure_kind is None


def test_outcome_failure_with_kind() -> None:
    o = LLMCallOutcome(succeeded=False, failure_kind="timeout")
    assert o.succeeded is False
    assert o.failure_kind == "timeout"


# --- call_with_response_model failure routing ---


def test_call_succeeds() -> None:
    client = _FakeClient("ok")
    result, outcome = call_with_response_model(
        client, _Out, _MSG, retries=0, model="claude-sonnet-4-6"
    )
    assert isinstance(result, _Out)
    assert outcome.succeeded is True
    assert outcome.failure_kind is None


def test_call_timeout_returns_timeout_outcome() -> None:
    client = _FakeClient("timeout")
    result, outcome = call_with_response_model(
        client, _Out, _MSG, retries=0, model="claude-sonnet-4-6"
    )
    assert result is None
    assert outcome.succeeded is False
    assert outcome.failure_kind == "timeout"


def test_call_auth_returns_auth_outcome() -> None:
    client = _FakeClient("auth")
    result, outcome = call_with_response_model(
        client, _Out, _MSG, retries=0, model="claude-sonnet-4-6"
    )
    assert result is None
    assert outcome.failure_kind == "auth"


def test_call_rate_limit_returns_rate_limit_outcome() -> None:
    client = _FakeClient("rate_limit")
    result, outcome = call_with_response_model(
        client, _Out, _MSG, retries=0, model="claude-sonnet-4-6"
    )
    assert result is None
    assert outcome.failure_kind == "rate_limit"


def test_call_unexpected_exception_categorized_as_other() -> None:
    """Catch-all is intentional + recorded — adversary H-4 mitigation."""
    client = _FakeClient("other")
    result, outcome = call_with_response_model(
        client, _Out, _MSG, retries=0, model="claude-sonnet-4-6"
    )
    assert result is None
    assert outcome.failure_kind == "other"


def test_call_rejects_negative_retries() -> None:
    with pytest.raises(ValueError, match="retries must be ≥ 0"):
        call_with_response_model(
            _FakeClient("ok"),
            _Out,
            _MSG,
            retries=-1,
            model="claude-sonnet-4-6",
        )


def test_call_rejects_empty_messages() -> None:
    with pytest.raises(ValueError, match="messages must be non-empty"):
        call_with_response_model(
            _FakeClient("ok"),
            _Out,
            messages=[],
            retries=0,
            model="claude-sonnet-4-6",
        )


# --- make_client guard rails ---


def test_make_client_rejects_openai_in_v0_1_0() -> None:
    with pytest.raises(NotImplementedError, match="anthropic"):
        make_client(provider="openai", model="gpt-4", timeout=30.0)


def test_make_client_rejects_empty_model() -> None:
    with pytest.raises(ValueError, match="model"):
        make_client(provider="anthropic", model="", timeout=30.0)


def test_make_client_rejects_zero_timeout() -> None:
    with pytest.raises(ValueError, match="timeout"):
        make_client(provider="anthropic", model="claude-sonnet-4-6", timeout=0)
