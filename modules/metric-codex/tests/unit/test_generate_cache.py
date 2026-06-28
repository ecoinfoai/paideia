"""T037/T043/T060 RED — InputHashCache determinism, LLM backend conformance, prompt-from-file.

DET-03: a second generate() with an identical request returns cache_hit=True
WITHOUT calling the wrapped backend and yields a byte-identical raw_text.

T043 (US6): LLM backend conformance —
- ApiBackend must NOT send temperature (removed for SDK conformance).
- BadRequestError/AuthenticationError/PermissionDeniedError → LocatedInputError
  (exit-2 territory), not BackendUnreachableError (exit-4).
- APIConnectionError/ConnectionError → BackendUnreachableError (exit-4, unchanged).
- Refusal / empty-content response → located error (not IndexError/crash).
- Two requests differing only in max_tokens → distinct cache keys (no stale hit).
- Malformed SubscriptionBackend response (missing slot_id/raw_text) → located
  exit-2 error (not a bare KeyError).

T060 (FR-025 / C2): _run_generate must load the LLM polish prompt from
templates/prompt_narrative.txt, NOT an inline hardcoded string.  The prompt
passed to the backend must contain the distinctive template line
"학습 근거 요약입니다" (present in the file, absent from the old inline string
"다음은 한 학생의 가명화된 학습 근거 요약이다. ").
"""

from __future__ import annotations

from pathlib import Path

import anthropic
import httpx
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


def _make_request(slot_id: str = "S001", max_tokens: int = 2048) -> GenerationRequest:
    return GenerationRequest(
        slot_id=slot_id,
        prompt="지도교수용 요약을 다듬어라.",
        facts="- score_total: 85 (출처: grades.xlsx, minimal)",
        model="claude-sonnet-4-6",
        mode="api",
        max_tokens=max_tokens,
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


def _fake_client_factory(raiser=None, message_obj=None):
    """Build a monkeypatch-ready fake Anthropic client.

    Args:
        raiser: If provided, calling create() raises this exception.
        message_obj: If provided, calling create() returns this object.
    """

    class _FakeMessages:
        def create(self, **_kwargs: object):
            if raiser is not None:
                raise raiser
            return message_obj

    class _FakeClient:
        messages = _FakeMessages()

    return _FakeClient


def _make_fake_text_message(text: str, stop_reason: str = "end_turn"):
    """Return a minimal fake Message-like object with a single TextBlock."""
    block = type("TextBlock", (), {"type": "text", "text": text})()

    class _FakeMessage:
        content = [block]

    _FakeMessage.stop_reason = stop_reason
    return _FakeMessage()


def _make_status_error(
    error_cls: type[anthropic.APIStatusError], status: int, msg: str
) -> anthropic.APIStatusError:
    """Build any ``APIStatusError`` subclass (BadRequest/Auth/PermissionDenied)."""
    req = httpx.Request("POST", "https://api.anthropic.com/v1/messages")
    resp = httpx.Response(status, request=req, text=msg)
    return error_cls(message=msg, response=resp, body={"error": {"type": "error"}})


def _make_bad_request_error(msg: str = "temperature not supported") -> anthropic.BadRequestError:
    return _make_status_error(anthropic.BadRequestError, 400, msg)


def _make_api_connection_error(msg: str = "cannot connect") -> anthropic.APIConnectionError:
    req = httpx.Request("POST", "https://api.anthropic.com/v1/messages")
    return anthropic.APIConnectionError(request=req, message=msg)


class TestApiBackend:
    """ApiBackend monkeypatched — never hits the live API."""

    def test_omits_temperature(self, monkeypatch) -> None:
        """T043: ApiBackend must NOT send temperature in the API call.

        This intentionally UPDATES test_uses_temperature_zero which asserted
        the defective behavior (temperature=0). The SDK 0.97.0 rejects
        temperature on Opus/Fable models with a 400 BadRequestError; removing
        temperature is the correct fix. Determinism is provided by
        InputHashCache (cache-hit reproducibility), not sampling temperature.
        """
        from metric_codex.generate.backend import ApiBackend

        captured: list[dict] = []

        class _CapturingMessages:
            def create(self, **kwargs: object):
                captured.append(dict(kwargs))
                return _make_fake_text_message("다듬은 응답")

        class _FakeClient:
            messages = _CapturingMessages()

        monkeypatch.setattr(
            "metric_codex.generate.backend.anthropic.Anthropic", lambda **_: _FakeClient()
        )

        backend = ApiBackend(model="claude-haiku-4-5")
        resp = backend.generate(_make_request("S001"))

        assert len(captured) == 1
        assert "temperature" not in captured[0], (
            "temperature must NOT be sent — modern Opus/Fable models reject it with a 400"
        )
        assert resp.raw_text == "다듬은 응답"

    @pytest.mark.parametrize(
        ("error_cls", "status"),
        [
            (anthropic.BadRequestError, 400),
            (anthropic.AuthenticationError, 401),
            (anthropic.PermissionDeniedError, 403),
        ],
    )
    def test_config_error_raises_located_input_error(self, monkeypatch, error_cls, status) -> None:
        """T043: config-class SDK errors surface as LocatedInputError (exit 2).

        Pre-fix: the blanket except-Exception wrapped these as
        BackendUnreachableError (exit 4), misreporting a config error as
        'unreachable'.  Post-fix: BadRequestError / AuthenticationError /
        PermissionDeniedError are config/request errors and must map to exit 2.
        Parametrized so the three share-a-branch types stay pinned to exit 2.
        """
        from metric_codex.errors import LocatedInputError
        from metric_codex.generate.backend import ApiBackend

        exc = _make_status_error(error_cls, status, "config error")
        monkeypatch.setattr(
            "metric_codex.generate.backend.anthropic.Anthropic",
            lambda **_: _fake_client_factory(raiser=exc)(),
        )

        backend = ApiBackend(model="claude-haiku-4-5")
        with pytest.raises(LocatedInputError) as caught:
            backend.generate(_make_request("S001"))

        # LocatedInputError subclasses ValueError → app() maps it to exit 2.
        assert isinstance(caught.value, ValueError)

    def test_wraps_connection_error(self, monkeypatch) -> None:
        """ConnectionError → BackendUnreachableError (exit 4). Unchanged behavior."""
        from metric_codex.generate.backend import ApiBackend, BackendUnreachableError

        monkeypatch.setattr(
            "metric_codex.generate.backend.anthropic.Anthropic",
            lambda **_: _fake_client_factory(raiser=ConnectionError("cannot reach anthropic"))(),
        )

        backend = ApiBackend(model="claude-haiku-4-5")
        with pytest.raises(BackendUnreachableError):
            backend.generate(_make_request("S001"))

    def test_api_connection_error_raises_unreachable(self, monkeypatch) -> None:
        """T043: anthropic.APIConnectionError → BackendUnreachableError (exit 4)."""
        from metric_codex.generate.backend import ApiBackend, BackendUnreachableError

        exc = _make_api_connection_error()
        monkeypatch.setattr(
            "metric_codex.generate.backend.anthropic.Anthropic",
            lambda **_: _fake_client_factory(raiser=exc)(),
        )

        backend = ApiBackend(model="claude-haiku-4-5")
        with pytest.raises(BackendUnreachableError):
            backend.generate(_make_request("S001"))

    def test_refusal_stop_reason_raises_located_error(self, monkeypatch) -> None:
        """T043: A 'refusal' stop_reason must raise LocatedInputError (not silently return empty)."""
        from metric_codex.errors import LocatedInputError
        from metric_codex.generate.backend import ApiBackend

        fake_msg = _make_fake_text_message("I cannot help with this", stop_reason="refusal")

        monkeypatch.setattr(
            "metric_codex.generate.backend.anthropic.Anthropic",
            lambda **_: _fake_client_factory(message_obj=fake_msg)(),
        )

        backend = ApiBackend(model="claude-haiku-4-5")
        with pytest.raises(LocatedInputError):
            backend.generate(_make_request("S001"))

    def test_empty_content_raises_located_error(self, monkeypatch) -> None:
        """T043: Empty content list must raise LocatedInputError (not IndexError crash)."""
        from metric_codex.errors import LocatedInputError
        from metric_codex.generate.backend import ApiBackend

        class _EmptyContentMessage:
            content = []
            stop_reason = "end_turn"

        monkeypatch.setattr(
            "metric_codex.generate.backend.anthropic.Anthropic",
            lambda **_: _fake_client_factory(message_obj=_EmptyContentMessage())(),
        )

        backend = ApiBackend(model="claude-haiku-4-5")
        with pytest.raises(LocatedInputError):
            backend.generate(_make_request("S001"))

    def test_no_text_block_raises_located_error(self, monkeypatch) -> None:
        """T043: Content with no text block (only tool_use etc.) raises LocatedInputError."""
        from metric_codex.errors import LocatedInputError
        from metric_codex.generate.backend import ApiBackend

        tool_block = type("ToolBlock", (), {"type": "tool_use", "id": "x", "input": {}})()

        class _NonTextMessage:
            content = [tool_block]
            stop_reason = "tool_use"

        monkeypatch.setattr(
            "metric_codex.generate.backend.anthropic.Anthropic",
            lambda **_: _fake_client_factory(message_obj=_NonTextMessage())(),
        )

        backend = ApiBackend(model="claude-haiku-4-5")
        with pytest.raises(LocatedInputError):
            backend.generate(_make_request("S001"))


class TestCacheKeyMaxTokens:
    """T043: max_tokens must be included in the cache key (distinct keys for distinct max_tokens)."""

    def test_different_max_tokens_yield_different_cache_keys(self, tmp_path: Path) -> None:
        """Two requests identical except max_tokens must NOT collide on cache."""
        backend = _CountingBackend(response_text="첫 번째 응답")
        cache = InputHashCache(backend=backend, cache_dir=tmp_path)

        req_512 = _make_request("S001", max_tokens=512)
        req_4096 = _make_request("S001", max_tokens=4096)

        cache.generate(req_512)
        cache.generate(req_4096)

        # Both must hit the backend — no stale cache collision.
        assert backend.call_count == 2, (
            f"Expected 2 backend calls for distinct max_tokens, got {backend.call_count}. "
            "max_tokens is not included in the cache key!"
        )
        assert len(list(tmp_path.glob("*.json"))) == 2

    def test_same_max_tokens_still_hits_cache(self, tmp_path: Path) -> None:
        """Identical requests (same max_tokens) still get a cache hit."""
        backend = _CountingBackend(response_text="캐시 응답")
        cache = InputHashCache(backend=backend, cache_dir=tmp_path)

        req = _make_request("S001", max_tokens=2048)
        cache.generate(req)
        resp2 = cache.generate(req)

        assert backend.call_count == 1
        assert resp2.cache_hit is True


class TestSubscriptionBackendMalformedResponse:
    """T043: SubscriptionBackend must raise LocatedInputError on malformed response JSON."""

    def test_missing_slot_id_raises_located_error(self, tmp_path: Path) -> None:
        """A response file missing 'slot_id' must raise LocatedInputError, not KeyError."""
        from metric_codex.errors import LocatedInputError
        from metric_codex.generate.backend import SubscriptionBackend

        staging = tmp_path / "staging"
        responses = tmp_path / "responses"
        responses.mkdir(parents=True)

        # Malformed: missing slot_id
        malformed = {"raw_text": "some text", "model": "claude-sonnet-4-6"}
        (responses / "S001.json").write_text(__import__("json").dumps(malformed), encoding="utf-8")

        backend = SubscriptionBackend(staging_dir=staging, responses_dir=responses)
        with pytest.raises(LocatedInputError):
            backend.generate(_make_request("S001"))

    def test_missing_raw_text_raises_located_error(self, tmp_path: Path) -> None:
        """A response file missing 'raw_text' must raise LocatedInputError, not KeyError."""
        from metric_codex.errors import LocatedInputError
        from metric_codex.generate.backend import SubscriptionBackend

        staging = tmp_path / "staging"
        responses = tmp_path / "responses"
        responses.mkdir(parents=True)

        # Malformed: missing raw_text
        malformed = {"slot_id": "S001", "model": "claude-sonnet-4-6"}
        (responses / "S001.json").write_text(__import__("json").dumps(malformed), encoding="utf-8")

        backend = SubscriptionBackend(staging_dir=staging, responses_dir=responses)
        with pytest.raises(LocatedInputError):
            backend.generate(_make_request("S001"))


# ---------------------------------------------------------------------------
# T060 RED — prompt must come from templates/prompt_narrative.txt, not inline
# ---------------------------------------------------------------------------


class _CapturingBackend(LLMBackend):
    """Records every GenerationRequest passed to it."""

    def __init__(self) -> None:
        self.requests: list[GenerationRequest] = []

    def generate(self, request: GenerationRequest) -> GenerationResponse:
        self.requests.append(request)
        return GenerationResponse(
            slot_id=request.slot_id,
            raw_text="polished by capturing backend",
            model="fake-model",
            cache_hit=False,
        )


def _ingest_one_student(tmp_path: Path) -> tuple[Path, str, str]:
    """Ingest a single-student fixture and return (data_root, semester, course).

    Used by the call-site prompt test (M1): generate needs a populated Silver
    store + pseudonym map so _run_generate produces at least one bundle.
    """
    import textwrap

    import openpyxl
    from metric_codex.cli.main import app

    data_root = tmp_path / "data"
    sem, course = "2026-1", "anatomy"
    key = f"{sem}-{course}"
    bronze = data_root / "bronze" / "metric-codex" / key
    bronze.mkdir(parents=True)

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(["학번", "이름", "총점"])
    ws.append([2026000001, "김철수", 85])
    wb.save(bronze / "성적출석.xlsx")
    (bronze / "성적출석_map.yaml").write_text(
        textwrap.dedent(f"""\
            semester: {sem}
            course_slug: {course}
            columns:
              student_id: 학번
              name_kr: 이름
              score_total: 총점
        """),
        encoding="utf-8",
    )
    (bronze / "question_set.yaml").write_text(
        textwrap.dedent("""\
            questions:
              - id: q1
                text: 총점을 알려주세요.
                entry_kinds:
                  - score_total
                domain: null
        """),
        encoding="utf-8",
    )

    rc = app(
        [
            "ingest",
            "--semester",
            sem,
            "--course",
            course,
            "--data-root",
            str(data_root),
            "--now",
            "2026-06-19T00:00:00Z",
        ]
    )
    assert rc == 0, "ingest fixture must succeed"
    return data_root, sem, course


class TestPromptFromTemplateFile:
    """T060 (FR-025 / C2): _run_generate must load the polish prompt from the template file.

    The template file (templates/prompt_narrative.txt) holds ONLY the prompt body
    the model receives: the Korean polish instruction (distinctive phrase
    '학습 근거 요약입니다') + the no-hallucination rule ('근거에 없는 사실은 절대
    추가하지 마세요') + the {pseudonym}/{facts} fields.  Operator/dev documentation
    (titles, the 'loaded by cli/main.py' note, the PRIVACY RULE architecture note)
    was trimmed out (I1) so it is NOT shipped to the LLM.

    Tests:
    1. The module-level constant ``_PROMPT_TEMPLATE`` exists in cli.main and
       contains the polish instruction (loaded from the file at import time).
    2. The template file itself (sanity check) contains the expected phrase.
    3. (M1) The actual ``request.prompt`` produced by ``_run_generate`` contains
       the formatted polish body AND does NOT contain a doc-header marker — this
       pins both the call-site wiring and the I1 trim.
    """

    def test_cli_module_has_prompt_template_constant(self) -> None:
        """_PROMPT_TEMPLATE must be defined in cli.main and contain the template content.

        RED: before the fix, cli.main has no _PROMPT_TEMPLATE — importing the
        module succeeds but the attribute is absent (AttributeError).
        GREEN: cli.main loads prompt_narrative.txt at module level and exposes
        the result as _PROMPT_TEMPLATE; the attribute exists and contains the
        file's distinctive phrase.
        """
        import metric_codex.cli.main as main_mod

        assert hasattr(main_mod, "_PROMPT_TEMPLATE"), (
            "cli.main must define _PROMPT_TEMPLATE loaded from prompt_narrative.txt"
        )
        prompt = main_mod._PROMPT_TEMPLATE
        # Distinctive phrase in the template body but NOT in the old inline string
        # ('학습 근거 요약이다' without the '입니다' ending).
        assert "학습 근거 요약입니다" in prompt, (
            f"_PROMPT_TEMPLATE must contain '학습 근거 요약입니다' from the template file; "
            f"got: {prompt[:200]!r}"
        )

    def test_template_file_contains_distinctive_phrase(self) -> None:
        """Sanity-check: templates/prompt_narrative.txt has the body, not doc header.

        Confirms the template carries the polish instruction and is NOT emptied
        or renamed, and that the I1-trimmed doc header is gone.
        """
        from pathlib import Path

        template_path = Path(__file__).resolve().parents[2] / "templates" / "prompt_narrative.txt"
        assert template_path.is_file(), f"template file missing: {template_path}"
        content = template_path.read_text(encoding="utf-8")
        assert "학습 근거 요약입니다" in content, (
            f"templates/prompt_narrative.txt must contain '학습 근거 요약입니다'; "
            f"found: {content[:200]!r}"
        )
        # I1: doc/meta header must be gone — only the prompt body ships.
        assert "loaded by cli/main.py" not in content, (
            "template must not contain the dev plumbing note (I1 trim)"
        )
        assert "PRIVACY RULE" not in content, (
            "template must not contain the operator privacy-note header (I1 trim)"
        )

    def test_run_generate_prompt_is_trimmed_body(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """M1: the request.prompt _run_generate builds is the formatted body, no doc header.

        Drives the real generate path with a capturing backend (ApiBackend patched
        at its source module, since _run_generate imports it locally), then asserts:
          - request.prompt carries the formatted polish instruction (the model's
            actual task), and
          - request.prompt does NOT carry a doc-header marker ('loaded by
            cli/main.py') — proving the I1 trim reaches the wire, not just the file.
        """
        from metric_codex.cli.main import app

        data_root, sem, course = _ingest_one_student(tmp_path)

        captured = _CapturingBackend()
        # _run_generate does `from metric_codex.generate.backend import ApiBackend`
        # at call time, so patching the source-module attribute injects our backend.
        monkeypatch.setattr(
            "metric_codex.generate.backend.ApiBackend",
            lambda **_kw: captured,
        )

        rc = app(
            [
                "generate",
                "--semester",
                sem,
                "--course",
                course,
                "--data-root",
                str(data_root),
                "--backend",
                "api",
                "--model",
                "fake-model",
                "--now",
                "2026-06-19T01:00:00Z",
            ]
        )
        assert rc == 0, "generate must succeed"
        assert captured.requests, "the backend must have been invoked"

        prompt = captured.requests[0].prompt
        # The model receives the formatted polish instruction (its real task).
        assert "학습 근거 요약입니다" in prompt, (
            f"call-site prompt must contain the polish instruction; got: {prompt!r}"
        )
        assert "근거에" in prompt and "추가하지 마세요" in prompt, (
            f"call-site prompt must retain the no-hallucination rule; got: {prompt!r}"
        )
        # The per-student pseudonym field is substituted (S001 for the lone student).
        assert "S001" in prompt, f"pseudonym field must be substituted; got: {prompt!r}"
        # I1: NO operator/dev doc header reaches the LLM.
        assert "loaded by cli/main.py" not in prompt, (
            f"doc-header marker must NOT reach the LLM prompt (I1 trim); got: {prompt!r}"
        )
        assert "PRIVACY RULE" not in prompt, (
            f"privacy-note header must NOT reach the LLM prompt (I1 trim); got: {prompt!r}"
        )
