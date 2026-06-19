"""T037 RED — InputHashCache determinism for metric-codex generate stage.

DET-03: a second generate() with an identical request returns cache_hit=True
WITHOUT calling the wrapped backend and yields a byte-identical raw_text.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from metric_codex.generate.backend import (
    GenerationRequest,
    GenerationResponse,
    InputHashCache,
    LLMBackend,
)


class _CountingBackend(LLMBackend):
    """Canned backend that returns a fixed response and counts calls."""

    def __init__(self, response_text: str = "polished narrative") -> None:
        self._text = response_text
        self.call_count = 0

    def generate(self, request: GenerationRequest) -> GenerationResponse:
        self.call_count += 1
        return GenerationResponse(
            slot_id=request.slot_id,
            raw_text=self._text,
            model="fake-model",
            cache_hit=False,
        )


def _make_request(slot_id: str = "S001") -> GenerationRequest:
    return GenerationRequest(
        slot_id=slot_id,
        prompt="지도교수용 요약을 다듬어라.",
        facts="- score_total: 85 (출처: grades.xlsx, minimal)",
        model="claude-sonnet-4-6",
        mode="api",
    )


class TestInputHashCacheDeterminism:
    def test_miss_then_hit_skips_backend(self, tmp_path: Path) -> None:
        backend = _CountingBackend()
        cache = InputHashCache(backend=backend, cache_dir=tmp_path)
        req = _make_request()

        resp1 = cache.generate(req)
        assert backend.call_count == 1
        assert resp1.cache_hit is False

        resp2 = cache.generate(req)
        # DET-03: the backend is NOT called again on a hit.
        assert backend.call_count == 1, "backend was called on cache hit!"
        assert resp2.cache_hit is True

    def test_hit_is_byte_identical(self, tmp_path: Path) -> None:
        backend = _CountingBackend("고유한 다듬은 본문 abc123")
        cache = InputHashCache(backend=backend, cache_dir=tmp_path)
        req = _make_request("S042")

        resp1 = cache.generate(req)
        resp2 = cache.generate(req)

        assert resp1.raw_text == resp2.raw_text
        assert resp2.raw_text == "고유한 다듬은 본문 abc123"

    def test_cache_writes_one_file_per_distinct_request(self, tmp_path: Path) -> None:
        backend = _CountingBackend()
        cache = InputHashCache(backend=backend, cache_dir=tmp_path)

        cache.generate(_make_request("S001"))
        cache.generate(_make_request("S002"))

        assert backend.call_count == 2
        assert len(list(tmp_path.glob("*.json"))) == 2

    def test_cache_hit_rate(self, tmp_path: Path) -> None:
        backend = _CountingBackend()
        cache = InputHashCache(backend=backend, cache_dir=tmp_path)
        assert cache.cache_hit_rate() == 0.0

        req = _make_request()
        cache.generate(req)  # miss
        cache.generate(req)  # hit
        assert cache.cache_hit_rate() == 0.5


class TestApiBackend:
    """ApiBackend monkeypatched — never hits the live API."""

    def test_uses_temperature_zero(self, monkeypatch) -> None:
        from metric_codex.generate.backend import ApiBackend

        captured: list[dict] = []

        class _FakeMessage:
            content = [type("Block", (), {"text": "다듬은 응답"})()]

        class _FakeMessages:
            def create(self, **kwargs: object) -> _FakeMessage:
                captured.append(dict(kwargs))
                return _FakeMessage()

        class _FakeClient:
            messages = _FakeMessages()

        monkeypatch.setattr(
            "metric_codex.generate.backend.anthropic.Anthropic", lambda **_: _FakeClient()
        )

        backend = ApiBackend(model="claude-haiku-4-5")
        resp = backend.generate(_make_request("S001"))

        assert len(captured) == 1
        assert captured[0].get("temperature") == 0
        assert resp.raw_text == "다듬은 응답"

    def test_wraps_connection_error(self, monkeypatch) -> None:
        from metric_codex.generate.backend import ApiBackend, BackendUnreachableError

        class _BrokenMessages:
            def create(self, **kwargs: object) -> None:
                raise ConnectionError("cannot reach anthropic")

        class _BrokenClient:
            messages = _BrokenMessages()

        monkeypatch.setattr(
            "metric_codex.generate.backend.anthropic.Anthropic", lambda **_: _BrokenClient()
        )

        backend = ApiBackend(model="claude-haiku-4-5")
        with pytest.raises(BackendUnreachableError):
            backend.generate(_make_request("S001"))
