"""Coaching message generation (T103, FR-020 (e), FR-PII-002).

Three-tier orchestrator:
  - select_template: pure rule-based template lookup.
  - polish_with_llm: optional LLM polish (preserves structure / numbers).
  - compose_coaching: orchestrator that returns (text, source) where source
    is "template" or "llm".

PII safety: every LLM payload runs through redact() with student_id + name.
validation_flag=False blocks the call (LLMCallTracker.record_pii_validation
+ failure_kind="pii_block").
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Literal

from pydantic import BaseModel, ConfigDict, Field

from ..llm.client import LLMCallOutcome, call_with_response_model
from ..llm.fallback import LLMCallTracker
from ..llm.pii import redact

if TYPE_CHECKING:
    import instructor

CoachingSource = Literal["template", "llm"]


class CoachingMessageOut(BaseModel):
    """instructor response_model for the LLM coaching-polish hook."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    text: str = Field(min_length=1, max_length=400)


def select_template(
    cluster_label: str | None,
    weak_axis: str | None,
    responded: bool,
    on_roster: bool,
) -> str:
    """Rule-based coaching template selector.

    Returns a 2-3 line message tailored to the (cluster, weak_axis,
    responded, on_roster) tuple. Never raises; always produces a
    non-empty template.
    """
    if not responded:
        return (
            "이번 학기 진단평가에 응답하지 않았습니다.\n"
            "교수자와 면담을 통해 학습 출발선을 점검해 보세요.\n"
            "(진단 미응답)"
        )
    if not on_roster:
        return (
            "명단외 응답자로 자료가 집계되었습니다.\n"
            f"본인의 학습 군집은 '{cluster_label or '미분류'}'입니다.\n"
            "정식 수강 등록을 확인하고 학습 계획을 점검하세요."
        )
    if cluster_label and weak_axis:
        return (
            f"본인은 '{cluster_label}' 군집에 속합니다.\n"
            f"'{weak_axis}' 영역이 상대적으로 약하니 이번 학기 보완 계획을 세워 보세요.\n"
            "주차별 학습 진도를 미리 점검하면 효과적입니다."
        )
    return (
        "이번 학기 학습 출발선을 확인했습니다.\n"
        "강점은 살리고 약점 영역은 우선순위로 보완하세요.\n"
        "교수자 면담을 적극 활용해 보세요."
    )


def polish_with_llm(
    template_text: str,
    *,
    student_id: str,
    student_name: str,
    llm_client: instructor.Instructor,
    llm_tracker: LLMCallTracker,
    llm_model: str,
    llm_retries: int,
) -> tuple[str | None, LLMCallOutcome]:
    """Polish the template text via LLM. Redacts PII before the call (FR-PII-002).

    Returns ``(polished_text_or_None, outcome)``. Caller decides whether to
    swap the returned text into the card.
    """
    redacted, validation_ok = redact(template_text, names=[student_name, student_id])
    llm_tracker.record_pii_validation(validation_ok)
    if not validation_ok:
        return None, LLMCallOutcome(succeeded=False, failure_kind="pii_block")

    prompt = (
        "다음 코칭 멘트의 어조를 더 자연스럽게 다듬으세요. "
        "수치·구조는 변경하지 마세요. 2-3줄로 작성하세요.\n\n" + redacted
    )
    result, outcome = call_with_response_model(
        llm_client,
        CoachingMessageOut,
        [{"role": "user", "content": prompt}],
        retries=llm_retries,
        model=llm_model,
    )
    if outcome.succeeded and isinstance(result, CoachingMessageOut):
        return result.text, outcome
    return None, outcome


def compose_coaching(
    *,
    cluster_label: str | None,
    weak_axis: str | None,
    responded: bool,
    on_roster: bool,
    student_id: str,
    student_name: str,
    llm_client: instructor.Instructor | None,
    llm_tracker: LLMCallTracker,
    llm_model: str = "claude-sonnet-4-6",
    llm_retries: int = 1,
) -> tuple[str, CoachingSource]:
    """Three-tier orchestrator: template → optional LLM polish → fallback.

    Returns ``(text, source)`` where ``source`` is ``"template"`` or
    ``"llm"``. LLM failure routes back to the template (no mixed-source).
    """
    template = select_template(
        cluster_label=cluster_label,
        weak_axis=weak_axis,
        responded=responded,
        on_roster=on_roster,
    )
    if llm_client is None or not responded:
        # Template path (also forced for non-responders since LLM cannot improve
        # the canned "진단 미응답" message).
        return template, "template"

    polished, outcome = polish_with_llm(
        template,
        student_id=student_id,
        student_name=student_name,
        llm_client=llm_client,
        llm_tracker=llm_tracker,
        llm_model=llm_model,
        llm_retries=llm_retries,
    )
    llm_tracker.record("coaching", outcome, student_id=student_id)
    if outcome.succeeded and polished is not None:
        return polished, "llm"
    return template, "template"
