"""Unit tests for maieutica.verify.review_agent — T052.

Covers both layers of the auto 2nd-pass review agent:

Layer 1 (deterministic rule checks, always run, no LLM):
- option length violation, explanation length violation, duplicate_flag,
  item textbook_evidence 미확인, leap textbook_evidence 미확인, leap evidence
  NONE (ungrounded leap — the critical gap), formative evidence 미확인.
- Clean items keep review_note == "".

Layer 2 (optional LLM adversarial pass):
- A mock backend returning a finding → that item's review_note gets the
  [review_agent] finding appended (proves layer 2 + leap-text scan path).
- An empty finding leaves review_note untouched.

Degrade (Constitution I):
- A backend whose .generate raises BackendUnreachableError → review_candidates
  returns the layer-1 rule notes intact (no raise) with degrade_on_unreachable
  default True.
- With degrade_on_unreachable=False (CLI api mode), the same backend re-raises
  BackendUnreachableError so the CLI can map it to exit 4.
"""

from __future__ import annotations

import pytest
from maieutica.generate.backend import (
    BackendUnreachableError,
    GenerationRequest,
    GenerationResponse,
    LLMBackend,
)
from maieutica.verify.review_agent import review_candidates
from paideia_shared.schemas import (
    FormativeItemCandidate,
    LeapExplanation,
    MaieuticaTextbookEvidence,
    QuizItemCandidate,
)

_SEMESTER = "2026-1"
_COURSE = "anatomy"
_WEEK = 9
_CHAPTER_NO = 8
_CHAPTER = "8장 호흡계통"
_SOURCE_FILE = "ch08.txt"


# ---------------------------------------------------------------------------
# Mock backends
# ---------------------------------------------------------------------------


class FindingBackend(LLMBackend):
    """Backend that returns a fixed non-empty finding for every request."""

    def __init__(self, finding: str = "정답이 2개로 보입니다") -> None:
        self._finding = finding
        self.call_count = 0

    def generate(self, request: GenerationRequest) -> GenerationResponse:
        self.call_count += 1
        return GenerationResponse(
            slot_id=request.slot_id,
            raw_text=self._finding,
            model="mock-finding",
            cache_hit=False,
        )


class EmptyFindingBackend(LLMBackend):
    """Backend that returns an empty finding (reviewer found nothing)."""

    def generate(self, request: GenerationRequest) -> GenerationResponse:
        return GenerationResponse(
            slot_id=request.slot_id,
            raw_text="   ",
            model="mock-empty",
            cache_hit=False,
        )


class UnreachableBackend(LLMBackend):
    """Backend whose .generate always raises BackendUnreachableError."""

    def __init__(self) -> None:
        self.call_count = 0

    def generate(self, request: GenerationRequest) -> GenerationResponse:
        self.call_count += 1
        raise BackendUnreachableError("mock: api unreachable")


# ---------------------------------------------------------------------------
# Candidate builders
# ---------------------------------------------------------------------------


def _confirmed_evidence(term: str = "폐포") -> MaieuticaTextbookEvidence:
    return MaieuticaTextbookEvidence(
        source_file=_SOURCE_FILE,
        chunk_id="ch08-01",
        found_text=term,
        status="확인",
    )


def _unconfirmed_evidence() -> MaieuticaTextbookEvidence:
    return MaieuticaTextbookEvidence(source_file=_SOURCE_FILE, status="미확인")


def _make_quiz(
    *,
    item_no: int = 1,
    option_length_ok: bool = True,
    explanation_length_ok: bool = True,
    duplicate_flag: bool = False,
    item_evidence: MaieuticaTextbookEvidence | None = None,
    leap_evidence: MaieuticaTextbookEvidence | None = "DEFAULT",  # type: ignore[assignment]
) -> QuizItemCandidate:
    """Build a quiz candidate; ``leap_evidence='DEFAULT'`` → confirmed leap."""
    key = "폐포"
    options = [
        f"{m} {key} 관련 보기 {item_no}-{i} 충분한 길이를 가진 보기입니다 abcde"
        for i, m in enumerate("①②③④⑤", start=1)
    ]
    if leap_evidence == "DEFAULT":
        leap_ev: MaieuticaTextbookEvidence | None = _confirmed_evidence(key)
    else:
        leap_ev = leap_evidence  # type: ignore[assignment]
    leap = LeapExplanation(text=f"{key} 다음 개념으로의 도약.", textbook_evidence=leap_ev)
    wrong = f"{key} 관련 오답 설명입니다."
    combined = f"{wrong} ─ 도약 ─ {leap.text}"
    return QuizItemCandidate(
        semester=_SEMESTER,
        course_slug=_COURSE,
        item_no=item_no,
        week=_WEEK,
        chapter_no=_CHAPTER_NO,
        chapter=_CHAPTER,
        key_concept=key,
        question_type="지식축적",
        difficulty="중",
        stem_polarity="부정형",
        text=f"{item_no}번 문제: {key}에 대해 옳지 않은 것은?",
        options=options,
        answer_no=1,
        option_evidence=[f"{key} 근거 {i}" for i in range(1, 6)],
        wrong_explanation=wrong,
        leap=leap,
        textbook_evidence=item_evidence if item_evidence is not None else _confirmed_evidence(key),
        answer_explanation_combined=combined,
        option_length_ok=option_length_ok,
        explanation_length_ok=explanation_length_ok,
        duplicate_flag=duplicate_flag,
        review_note="",
    )


def _make_formative(
    *,
    no: int = 1,
    evidence: MaieuticaTextbookEvidence | None = None,
) -> FormativeItemCandidate:
    topic = "가스교환"
    return FormativeItemCandidate(
        semester=_SEMESTER,
        course_slug=_COURSE,
        no=no,
        chapter_no=_CHAPTER_NO,
        topic=topic,
        question=f"{no}번 형성문항: {topic} 원리를 서술하시오.",
        limit="200자 내외",
        model_answer=f"{topic}는 핵심.",
        purpose=f"{topic} 이해.",
        keywords=[topic],
        rubric_high=f"{topic} 전부.",
        rubric_mid=f"{topic} 일부.",
        rubric_low=f"{topic} 누락.",
        support_high=f"{topic} 도약.",
        support_mid=f"{topic} 복습.",
        support_low=f"{topic} 재학습.",
        textbook_evidence=evidence if evidence is not None else _confirmed_evidence(topic),
        review_note="",
    )


# ---------------------------------------------------------------------------
# Layer 1: deterministic rule checks
# ---------------------------------------------------------------------------


def test_clean_quiz_keeps_blank() -> None:
    """A fully valid quiz item keeps review_note == ''."""
    reviewed, _ = review_candidates([_make_quiz()], [], backend=None)
    assert reviewed[0].review_note == ""


def test_option_length_violation() -> None:
    """option_length_ok=False → review_note mentions length."""
    reviewed, _ = review_candidates([_make_quiz(option_length_ok=False)], [], backend=None)
    note = reviewed[0].review_note
    assert note != ""
    assert "length" in note.lower() or "길이" in note


def test_explanation_length_violation() -> None:
    """explanation_length_ok=False → review_note is non-empty."""
    reviewed, _ = review_candidates([_make_quiz(explanation_length_ok=False)], [], backend=None)
    assert reviewed[0].review_note != ""


def test_duplicate_flag() -> None:
    """duplicate_flag=True → review_note mentions duplicate (중복)."""
    reviewed, _ = review_candidates([_make_quiz(duplicate_flag=True)], [], backend=None)
    note = reviewed[0].review_note
    assert "중복" in note or "duplicate" in note.lower()


def test_item_evidence_unconfirmed() -> None:
    """textbook_evidence.status=='미확인' → review_note names evidence issue."""
    reviewed, _ = review_candidates(
        [_make_quiz(item_evidence=_unconfirmed_evidence())], [], backend=None
    )
    note = reviewed[0].review_note
    assert note != ""
    assert "교재근거" in note or "미확인" in note


def test_leap_evidence_unconfirmed() -> None:
    """leap.textbook_evidence.status=='미확인' → review_note mentions leap (도약)."""
    reviewed, _ = review_candidates(
        [_make_quiz(leap_evidence=_unconfirmed_evidence())], [], backend=None
    )
    note = reviewed[0].review_note
    assert note != ""
    assert "도약" in note
    assert "미확인" in note


def test_leap_evidence_none_is_flaw() -> None:
    """CRITICAL gap: leap.textbook_evidence is None → review_note flags it.

    An ungrounded leap (no evidence info at all) must NOT silently pass.
    """
    reviewed, _ = review_candidates([_make_quiz(leap_evidence=None)], [], backend=None)
    note = reviewed[0].review_note
    assert note != "", "Ungrounded leap (evidence=None) must be flagged, not silently passed"
    assert "도약" in note
    assert "없음" in note


def test_formative_evidence_unconfirmed() -> None:
    """Formative textbook_evidence.status=='미확인' → review_note non-empty."""
    _, reviewed = review_candidates(
        [], [_make_formative(evidence=_unconfirmed_evidence())], backend=None
    )
    assert reviewed[0].review_note != ""


def test_clean_formative_keeps_blank() -> None:
    """A confirmed formative item keeps review_note == ''."""
    _, reviewed = review_candidates([], [_make_formative()], backend=None)
    assert reviewed[0].review_note == ""


def test_multiple_violations_aggregated() -> None:
    """Multiple flags on one item are all recorded in review_note."""
    item = _make_quiz(
        option_length_ok=False,
        duplicate_flag=True,
        leap_evidence=_unconfirmed_evidence(),
    )
    reviewed, _ = review_candidates([item], [], backend=None)
    note = reviewed[0].review_note
    assert "중복" in note
    assert "도약" in note
    assert "length" in note.lower() or "길이" in note


# ---------------------------------------------------------------------------
# Layer 2: LLM adversarial pass
# ---------------------------------------------------------------------------


def test_adversarial_finding_appended() -> None:
    """A backend finding is appended to review_note, tagged [review_agent]."""
    backend = FindingBackend("정답이 2개로 보입니다")
    reviewed, _ = review_candidates([_make_quiz()], [], backend=backend)
    note = reviewed[0].review_note
    assert "[review_agent]" in note
    assert "정답이 2개로 보입니다" in note
    assert backend.call_count == 1


def test_adversarial_finding_appended_after_rule_note() -> None:
    """Layer 2 finding is appended after an existing layer-1 rule note."""
    backend = FindingBackend("교재밖 사실 의심")
    # leap_evidence=None triggers a layer-1 note first.
    reviewed, _ = review_candidates([_make_quiz(leap_evidence=None)], [], backend=backend)
    note = reviewed[0].review_note
    assert "도약" in note  # layer-1 note retained
    assert "[review_agent] 교재밖 사실 의심" in note  # layer-2 appended


def test_adversarial_empty_finding_leaves_note() -> None:
    """An empty LLM finding leaves the (clean) review_note untouched."""
    backend = EmptyFindingBackend()
    reviewed, _ = review_candidates([_make_quiz()], [], backend=backend)
    assert reviewed[0].review_note == ""


def test_adversarial_runs_per_quiz_item_only() -> None:
    """The adversarial backend is called once per quiz item (not formative)."""
    backend = FindingBackend("결함")
    quiz = [_make_quiz(item_no=1), _make_quiz(item_no=2)]
    formative = [_make_formative(no=1)]
    review_candidates(quiz, formative, backend=backend)
    assert backend.call_count == 2  # quiz only


# ---------------------------------------------------------------------------
# Degrade (Constitution I) — the real raising-backend path
# ---------------------------------------------------------------------------


def test_degrade_keeps_layer1_notes_intact() -> None:
    """Unreachable backend + degrade default True → layer-1 notes intact, no raise."""
    backend = UnreachableBackend()
    # Item carries a layer-1 violation (leap_evidence None).
    reviewed, _ = review_candidates([_make_quiz(leap_evidence=None)], [], backend=backend)
    # No raise; the layer-1 rule note survives the degrade.
    note = reviewed[0].review_note
    assert "도약" in note
    assert "없음" in note
    assert backend.call_count >= 1, "backend was actually invoked (then degraded)"


def test_degrade_clean_item_stays_blank() -> None:
    """Unreachable backend on a clean item → review_note stays '' (no raise)."""
    backend = UnreachableBackend()
    reviewed, _ = review_candidates([_make_quiz()], [], backend=backend)
    assert reviewed[0].review_note == ""


def test_no_degrade_propagates_for_api_mode() -> None:
    """degrade_on_unreachable=False → BackendUnreachableError propagates (exit 4)."""
    backend = UnreachableBackend()
    with pytest.raises(BackendUnreachableError):
        review_candidates([_make_quiz()], [], backend=backend, degrade_on_unreachable=False)
