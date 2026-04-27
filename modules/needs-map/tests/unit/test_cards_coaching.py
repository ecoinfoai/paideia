"""Unit tests for coaching template selection (T092, FR-020 (e))."""

from __future__ import annotations


def test_select_template_for_responder_no_warnings() -> None:
    from needs_map.cards.coaching import select_template

    text = select_template(
        cluster_label="고동기·저흥미형",
        weak_axis="interest",
        responded=True,
        on_roster=True,
    )
    assert isinstance(text, str)
    assert len(text) > 10  # non-trivial coaching message


def test_select_template_for_no_response_student() -> None:
    """진단 미응답 학생: card body shows 진단 미응답 message (FR-021)."""
    from needs_map.cards.coaching import select_template

    text = select_template(
        cluster_label=None,
        weak_axis=None,
        responded=False,
        on_roster=True,
    )
    assert "진단 미응답" in text


def test_select_template_off_roster_responder() -> None:
    """명단외 응답자도 정상 카드 (FR-019 Edge case)."""
    from needs_map.cards.coaching import select_template

    text = select_template(
        cluster_label="고불안·저자기효능형",
        weak_axis="self_efficacy",
        responded=True,
        on_roster=False,
    )
    assert isinstance(text, str)
    assert "명단외" in text or len(text) > 10


def test_compose_coaching_no_llm_returns_template_source() -> None:
    """compose_coaching with llm_client=None → coaching_source='template'."""
    from needs_map.cards.coaching import compose_coaching
    from needs_map.llm.fallback import LLMCallTracker

    tracker = LLMCallTracker()
    text, source = compose_coaching(
        cluster_label="고동기·저흥미형",
        weak_axis="interest",
        responded=True,
        on_roster=True,
        student_id="2026194042",
        student_name="홍길동",
        llm_client=None,
        llm_tracker=tracker,
    )
    assert source == "template"
    assert isinstance(text, str)
    assert tracker.to_stats() == []  # no LLM calls attempted


def test_compose_coaching_llm_failure_falls_back() -> None:
    """LLM failure → source='template' + tracker records failure_kind."""
    from needs_map.cards.coaching import compose_coaching
    from needs_map.llm.fallback import LLMCallTracker

    class _FakeFail:
        class _Chat:
            class _Completions:
                def create(self, **_: object) -> object:
                    import httpx

                    raise httpx.TimeoutException("simulated")

            completions = _Completions()

        chat = _Chat()

    tracker = LLMCallTracker()
    text, source = compose_coaching(
        cluster_label="고불안형",
        weak_axis="anxiety",
        responded=True,
        on_roster=True,
        student_id="2026194042",
        student_name="홍길동",
        llm_client=_FakeFail(),
        llm_tracker=tracker,
        llm_model="claude-sonnet-4-6",
        llm_retries=0,
    )
    assert source == "template"  # fallback to template
    assert isinstance(text, str)
    stats = tracker.to_stats()
    assert len(stats) == 1
    assert stats[0].site == "coaching"
    assert stats[0].failure_kinds.get("timeout", 0) == 1


def test_compose_coaching_pii_redacted_before_llm() -> None:
    """The student_id and name MUST be stripped from the LLM payload (FR-PII-002)."""
    from needs_map.cards.coaching import compose_coaching
    from needs_map.llm.fallback import LLMCallTracker

    captured_payload: list[str] = []

    class _Capturer:
        class _Chat:
            class _Completions:
                def create(self, **kw: object) -> object:
                    msgs = kw.get("messages", [])
                    for m in msgs:  # type: ignore[union-attr]
                        captured_payload.append(m.get("content", ""))
                    raise RuntimeError("fail-after-capture")

            completions = _Completions()

        chat = _Chat()

    tracker = LLMCallTracker()
    compose_coaching(
        cluster_label="고동기형",
        weak_axis="motivation",
        responded=True,
        on_roster=True,
        student_id="2026194042",
        student_name="홍길동",
        llm_client=_Capturer(),
        llm_tracker=tracker,
        llm_model="claude-sonnet-4-6",
        llm_retries=0,
    )
    # Payload captured and PII checked
    full_payload = " ".join(captured_payload)
    assert "2026194042" not in full_payload  # student_id stripped
    assert "홍길동" not in full_payload  # name stripped
