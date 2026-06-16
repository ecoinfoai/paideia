"""T051 — Integration test: US5 auto 2nd-pass review (FR-018).

Verifies:
1. After ``build``, ALL candidates have ``review_note == ""`` (FR-018: blank at
   generation — the review pass must not pollute build output).
2. ``review_candidates(quiz_items, formative_items)`` — rules-only layer (no
   backend) — correctly identifies and annotates flawed candidates while keeping
   clean candidates blank.
3. A deliberately-flawed quiz item (``option_length_ok=False``) gets a non-empty
   ``review_note``; a clean item keeps ``review_note == ""``.
4. A deliberately-flawed formative item (``textbook_evidence.status=="미확인"``)
   gets a non-empty ``review_note``; a clean formative keeps blank.
5. Leap backstop: a quiz item whose ``leap.textbook_evidence.status=="미확인"``
   gets a ``review_note`` naming the leap evidence issue.
6. The ``verify`` CLI subcommand on a built run writes the updated yaml with
   flawed candidates annotated and exits 0.
7. ``read_candidate_yaml`` round-trips the written yaml back to typed models.
"""

from __future__ import annotations

import json
from pathlib import Path

import yaml
from maieutica.ingest.spec_load import load_curriculum_map, load_generation_spec
from maieutica.plan.slots import plan_slots
from paideia_shared.schemas import (
    FormativeItemCandidate,
    LeapExplanation,
    MaieuticaGenerationSpec,
    MaieuticaTextbookEvidence,
    QuizItemCandidate,
)

# ---------------------------------------------------------------------------
# Fixture constants
# ---------------------------------------------------------------------------

_SEMESTER = "2026-1"
_COURSE = "anatomy"
_WEEK = 9
_CHAPTER_NO = 8
_CHAPTER = "8장 호흡계통"
_QUIZ_COUNT = 2
_FORMATIVE_COUNT = 1

_KEY_CONCEPTS = ["폐포", "기관지"]
_FORMATIVE_TOPIC = "가스교환"

_CHAPTER_TXT = "\n".join(
    [
        "8장 호흡계통",
        "",
        "1. 호흡계통의 구조",
        "코는 후각과 공기 가습을 담당한다.",
        "폐포는 가스 교환이 일어나는 포상 구조이다.",
        "기관지는 공기를 폐로 전달하는 통로이다.",
        "허파꽈리에서 가스교환이 분압 차이로 일어난다.",
        "가로막은 수축하여 흉강 부피를 늘린다.",
        "",
    ]
)

# ---------------------------------------------------------------------------
# Bronze + canned-response helpers (reuse US2/US3 fixture pattern)
# ---------------------------------------------------------------------------


# Answer-anchored groundedness (US1): the correct option's evidence must be a
# verbatim chapter line in the slot's assigned subsection (single subsection
# here) so the item resolves to 확인.
_EVIDENCE_LINE = {
    "폐포": "폐포는 가스 교환이 일어나는 포상 구조이다.",
    "기관지": "기관지는 공기를 폐로 전달하는 통로이다.",
}


def _quiz_item_json(item_no: int, key_concept: str, answer_no: int) -> dict:
    options = [
        f"{marker} {key_concept} 관련 보기 {item_no}-{i} 충분한 길이를 가진 보기입니다 abcde"
        for i, marker in enumerate("①②③④⑤", start=1)
    ]
    option_evidence = [f"{key_concept} 근거 {i}" for i in range(1, 6)]
    option_evidence[answer_no - 1] = _EVIDENCE_LINE[key_concept]
    return {
        "question_type": "지식축적",
        "stem_polarity": "부정형",
        "text": f"{item_no}번 문제: {key_concept}에 대해 옳지 않은 것은?",
        "options": options,
        "answer_no": answer_no,
        "option_evidence": option_evidence,
        "wrong_explanation": f"{key_concept} 관련 오답 설명입니다.",
        "leap_explanation": f"{key_concept} 다음 개념으로의 도약 설명입니다.",
        "key_concept": key_concept,
        "section": "1. 호흡계통의 구조",
    }


def _formative_item_json(no: int, topic: str) -> dict:
    return {
        "no": no,
        "chapter_no": _CHAPTER_NO,
        "topic": topic,
        "question": f"{no}번 형성문항: {topic} 원리를 서술하시오.",
        "limit": "200자 내외",
        "model_answer": f"{topic}는 핵심 과정이다.",
        "purpose": f"{topic} 이해 확인.",
        "keywords": [topic, "분압"],
        "rubric_high": f"{topic} 핵심 전부.",
        "rubric_mid": f"{topic} 일부.",
        "rubric_low": f"{topic} 누락.",
        "support_high": f"{topic} 다음 심화로 도약.",
        "support_mid": f"{topic} 복습.",
        "support_low": f"{topic} 기본 재학습.",
    }


def _write_envelope(responses_dir: Path, slot_id: str, item_json: dict) -> None:
    envelope = {
        "slot_id": slot_id,
        "raw_text": json.dumps(item_json, ensure_ascii=False),
        "model": "canned-subscription",
    }
    (responses_dir / f"{slot_id}.json").write_text(
        json.dumps(envelope, ensure_ascii=False), encoding="utf-8"
    )


def _build_bronze(tmp_path: Path) -> tuple[Path, Path]:
    data_root = tmp_path / "data"
    bronze = data_root / "bronze" / "maieutica" / f"{_SEMESTER}-{_COURSE}"
    bronze.mkdir(parents=True, exist_ok=True)
    (bronze / f"{_CHAPTER} 호흡.txt").write_text(_CHAPTER_TXT, encoding="utf-8")
    spec = {
        "semester": _SEMESTER,
        "course_slug": _COURSE,
        "week": _WEEK,
        "chapter_no": _CHAPTER_NO,
        "chapter": _CHAPTER,
        "quiz_count": _QUIZ_COUNT,
        "formative_count": _FORMATIVE_COUNT,
    }
    (bronze / "generation_spec.yaml").write_text(
        json.dumps(spec, ensure_ascii=False), encoding="utf-8"
    )
    curriculum = {
        "semester": _SEMESTER,
        "course_slug": _COURSE,
        "entries": [
            {
                "week": _WEEK,
                "chapter": _CHAPTER,
                "chapter_no": _CHAPTER_NO,
                "sections": ["1. 호흡계통의 구조"],
            }
        ],
    }
    (bronze / "curriculum_map.yaml").write_text(
        json.dumps(curriculum, ensure_ascii=False), encoding="utf-8"
    )
    return bronze, data_root


def _write_canned_responses(responses_dir: Path) -> None:
    responses_dir.mkdir(parents=True, exist_ok=True)
    spec = MaieuticaGenerationSpec.model_validate(
        {
            "semester": _SEMESTER,
            "course_slug": _COURSE,
            "week": _WEEK,
            "chapter_no": _CHAPTER_NO,
            "chapter": _CHAPTER,
            "quiz_count": _QUIZ_COUNT,
            "formative_count": _FORMATIVE_COUNT,
        }
    )
    slots = plan_slots(spec)
    for idx, slot in enumerate(s for s in slots if s.kind == "quiz"):
        key_concept = _KEY_CONCEPTS[idx % len(_KEY_CONCEPTS)]
        answer_no = (idx % 5) + 1
        _write_envelope(
            responses_dir, slot.slot_id, _quiz_item_json(slot.ordinal, key_concept, answer_no)
        )
    for slot in (s for s in slots if s.kind == "formative"):
        _write_envelope(
            responses_dir, slot.slot_id, _formative_item_json(slot.ordinal, _FORMATIVE_TOPIC)
        )


# ---------------------------------------------------------------------------
# Minimal QuizItemCandidate builder (without going through the full pipeline)
# ---------------------------------------------------------------------------

_SOURCE_FILE = "ch08.txt"


def _make_clean_quiz_item(item_no: int = 1) -> QuizItemCandidate:
    """A fully valid quiz item with no flag violations."""
    key = "폐포"
    options = [
        f"① {key} 관련 보기 1번 충분한 길이를 가진 보기입니다 abcde",
        f"② {key} 관련 보기 2번 충분한 길이를 가진 보기입니다 abcde",
        f"③ {key} 관련 보기 3번 충분한 길이를 가진 보기입니다 abcde",
        f"④ {key} 관련 보기 4번 충분한 길이를 가진 보기입니다 abcde",
        f"⑤ {key} 관련 보기 5번 충분한 길이를 가진 보기입니다 abcde",
    ]
    evidence = MaieuticaTextbookEvidence(
        source_file=_SOURCE_FILE,
        chunk_id="ch08-01",
        found_text=key,
        status="확인",
    )
    leap = LeapExplanation(
        text="폐포 다음 개념으로의 도약.", textbook_evidence=evidence.model_copy()
    )
    wrong = "폐포 관련 오답 설명입니다."
    combined = f"{wrong} ─ 도약 ─ {leap.text}"
    return QuizItemCandidate(
        semester=_SEMESTER,
        course_slug=_COURSE,
        item_no=item_no,
        week=_WEEK,
        chapter_no=_CHAPTER_NO,
        chapter=_CHAPTER,
        section="1. 호흡계통의 구조",
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
        textbook_evidence=evidence,
        answer_explanation_combined=combined,
        option_length_ok=True,
        explanation_length_ok=True,
        review_note="",
    )


def _make_flawed_quiz_option_length(item_no: int = 2) -> QuizItemCandidate:
    """A quiz item with option_length_ok=False (option text too short)."""
    key = "기관지"
    # Deliberately short options — less than 30 codepoints.
    options = [f"① 짧은보기{i}" for i in range(1, 6)]
    evidence = MaieuticaTextbookEvidence(source_file=_SOURCE_FILE, status="미확인")
    leap = LeapExplanation(text="짧은 도약.")
    wrong = "짧은 설명."
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
        difficulty="하",
        stem_polarity="부정형",
        text=f"{item_no}번 문제: {key}에 대해 옳지 않은 것은?",
        options=options,
        answer_no=1,
        option_evidence=[f"{key} 근거 {i}" for i in range(1, 6)],
        wrong_explanation=wrong,
        leap=leap,
        textbook_evidence=evidence,
        answer_explanation_combined=combined,
        option_length_ok=False,  # <-- violation
        explanation_length_ok=True,
        review_note="",
    )


def _make_flawed_quiz_leap_evidence(item_no: int = 3) -> QuizItemCandidate:
    """A quiz item with leap.textbook_evidence.status == '미확인'."""
    key = "가로막"
    options = [
        f"① {key} 관련 보기 1번 충분한 길이를 가진 보기입니다 abcde",
        f"② {key} 관련 보기 2번 충분한 길이를 가진 보기입니다 abcde",
        f"③ {key} 관련 보기 3번 충분한 길이를 가진 보기입니다 abcde",
        f"④ {key} 관련 보기 4번 충분한 길이를 가진 보기입니다 abcde",
        f"⑤ {key} 관련 보기 5번 충분한 길이를 가진 보기입니다 abcde",
    ]
    item_evidence = MaieuticaTextbookEvidence(
        source_file=_SOURCE_FILE,
        chunk_id="ch08-01",
        found_text=key,
        status="확인",
    )
    leap_evidence = MaieuticaTextbookEvidence(
        source_file=_SOURCE_FILE,
        status="미확인",  # <-- leap backstop trigger
    )
    leap = LeapExplanation(
        text=f"{key} 도약 설명입니다.",
        textbook_evidence=leap_evidence,
    )
    wrong = f"{key} 오답 설명입니다."
    combined = f"{wrong} ─ 도약 ─ {leap.text}"
    return QuizItemCandidate(
        semester=_SEMESTER,
        course_slug=_COURSE,
        item_no=item_no,
        week=_WEEK,
        chapter_no=_CHAPTER_NO,
        chapter=_CHAPTER,
        key_concept=key,
        question_type="맥락통찰",
        difficulty="상",
        stem_polarity="긍정형",
        text=f"{item_no}번 문제: {key}에 대해 옳은 것은?",
        options=options,
        answer_no=1,
        option_evidence=[f"{key} 근거 {i}" for i in range(1, 6)],
        wrong_explanation=wrong,
        leap=leap,
        textbook_evidence=item_evidence,
        answer_explanation_combined=combined,
        option_length_ok=True,
        explanation_length_ok=True,
        review_note="",
    )


def _make_clean_formative(no: int = 1) -> FormativeItemCandidate:
    """A fully valid formative item — textbook_evidence 확인."""
    topic = _FORMATIVE_TOPIC
    evidence = MaieuticaTextbookEvidence(
        source_file=_SOURCE_FILE,
        chunk_id="ch08-01",
        found_text=topic,
        status="확인",
    )
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
        textbook_evidence=evidence,
        review_note="",
    )


def _make_flawed_formative_evidence(no: int = 2) -> FormativeItemCandidate:
    """A formative item with textbook_evidence.status == '미확인'."""
    topic = "외부지식"
    evidence = MaieuticaTextbookEvidence(
        source_file=_SOURCE_FILE,
        status="미확인",  # <-- violation
    )
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
        textbook_evidence=evidence,
        review_note="",
    )


# ---------------------------------------------------------------------------
# FR-018: review_note blank after build
# ---------------------------------------------------------------------------


def test_build_leaves_review_note_blank(tmp_path: Path) -> None:
    """FR-018: all candidates emitted by build have review_note == ''."""
    from maieutica.generate.backend import SubscriptionBackend
    from maieutica.pipeline import build

    bronze, data_root = _build_bronze(tmp_path)
    spec = load_generation_spec(bronze / "generation_spec.yaml")
    curriculum_map = load_curriculum_map(bronze / "curriculum_map.yaml")

    silver = data_root / "silver" / "maieutica" / f"{_SEMESTER}-{_COURSE}"
    responses_dir = silver / "responses"
    _write_canned_responses(responses_dir)
    backend = SubscriptionBackend(staging_dir=silver / "staging", responses_dir=responses_dir)

    items, _run_dir = build(
        spec=spec,
        curriculum_map=curriculum_map,
        bronze_dir=bronze,
        data_root=data_root,
        backend=backend,
        generation_spec_path=bronze / "generation_spec.yaml",
        curriculum_map_path=bronze / "curriculum_map.yaml",
    )

    # All quiz candidates must have blank review_note after build.
    for item in items:
        assert item.review_note == "", (
            f"item {item.item_no} has non-empty review_note after build: {item.review_note!r}"
        )

    # Also verify via the written yaml.
    run_dir_path = _run_dir
    doc = yaml.safe_load((run_dir_path / "출제후보_완전판.yaml").read_text(encoding="utf-8"))
    for d in doc["quiz"]:
        assert d["review_note"] == "", (
            f"yaml quiz item {d['item_no']} has non-empty review_note: {d['review_note']!r}"
        )
    for d in doc["formative"]:
        assert d["review_note"] == "", (
            f"yaml formative item {d['no']} has non-empty review_note: {d['review_note']!r}"
        )


# ---------------------------------------------------------------------------
# review_candidates — rules-only layer
# ---------------------------------------------------------------------------


def test_clean_items_keep_blank_review_note() -> None:
    """Clean candidates (no violations) keep review_note == '' after rules pass."""
    from maieutica.verify.review_agent import review_candidates

    clean_quiz = [_make_clean_quiz_item(1)]
    clean_formative = [_make_clean_formative(1)]
    reviewed_quiz, reviewed_formative = review_candidates(clean_quiz, clean_formative, backend=None)

    assert reviewed_quiz[0].review_note == ""
    assert reviewed_formative[0].review_note == ""


def test_option_length_violation_sets_review_note() -> None:
    """option_length_ok=False → review_note is non-empty and mentions length."""
    from maieutica.verify.review_agent import review_candidates

    flawed = _make_flawed_quiz_option_length(2)
    reviewed_quiz, _ = review_candidates([flawed], [], backend=None)

    note = reviewed_quiz[0].review_note
    assert note != "", "Expected non-empty review_note for option length violation"
    assert "length" in note.lower() or "길이" in note or "option" in note.lower(), (
        f"review_note does not mention length issue: {note!r}"
    )


def test_explanation_length_violation_sets_review_note() -> None:
    """explanation_length_ok=False → review_note is non-empty."""
    from maieutica.verify.review_agent import review_candidates

    # Build an item with explanation_length_ok=False but options ok.
    key = "폐포"
    options = [
        f"① {key} 관련 보기 1번 충분한 길이를 가진 보기입니다 abcde",
        f"② {key} 관련 보기 2번 충분한 길이를 가진 보기입니다 abcde",
        f"③ {key} 관련 보기 3번 충분한 길이를 가진 보기입니다 abcde",
        f"④ {key} 관련 보기 4번 충분한 길이를 가진 보기입니다 abcde",
        f"⑤ {key} 관련 보기 5번 충분한 길이를 가진 보기입니다 abcde",
    ]
    long_text = "가" * 201  # exceeds 200 char limit
    leap = LeapExplanation(text=long_text)
    wrong = "짧은 설명."
    combined = f"{wrong} ─ 도약 ─ {long_text}"
    item = QuizItemCandidate(
        semester=_SEMESTER,
        course_slug=_COURSE,
        item_no=10,
        week=_WEEK,
        chapter_no=_CHAPTER_NO,
        chapter=_CHAPTER,
        key_concept=key,
        question_type="지식축적",
        difficulty="중",
        stem_polarity="부정형",
        text=f"10번 문제: {key}에 대해 옳지 않은 것은?",
        options=options,
        answer_no=1,
        option_evidence=[f"{key} 근거 {i}" for i in range(1, 6)],
        wrong_explanation=wrong,
        leap=leap,
        answer_explanation_combined=combined,
        option_length_ok=True,
        explanation_length_ok=False,  # <-- violation
        review_note="",
    )
    reviewed_quiz, _ = review_candidates([item], [], backend=None)
    note = reviewed_quiz[0].review_note
    assert note != "", "Expected non-empty review_note for explanation length violation"


def test_duplicate_flag_sets_review_note() -> None:
    """duplicate_flag=True → review_note is non-empty and mentions duplicate."""
    from maieutica.verify.review_agent import review_candidates

    item = _make_clean_quiz_item(4).model_copy(update={"duplicate_flag": True})
    reviewed_quiz, _ = review_candidates([item], [], backend=None)
    note = reviewed_quiz[0].review_note
    assert note != "", "Expected non-empty review_note for duplicate_flag=True"
    assert "중복" in note or "duplicate" in note.lower(), (
        f"review_note does not mention duplicate: {note!r}"
    )


def test_item_evidence_unconfirmed_sets_review_note() -> None:
    """textbook_evidence.status=='미확인' → review_note mentions evidence issue."""
    from maieutica.verify.review_agent import review_candidates

    # Take a clean item and override its textbook_evidence to 미확인.
    unconfirmed_ev = MaieuticaTextbookEvidence(source_file=_SOURCE_FILE, status="미확인")
    item = _make_clean_quiz_item(5).model_copy(update={"textbook_evidence": unconfirmed_ev})
    reviewed_quiz, _ = review_candidates([item], [], backend=None)
    note = reviewed_quiz[0].review_note
    assert note != "", "Expected non-empty review_note for 미확인 textbook_evidence"
    assert "교재근거" in note or "evidence" in note.lower() or "미확인" in note, (
        f"review_note does not name the evidence issue: {note!r}"
    )


def test_leap_evidence_unconfirmed_sets_review_note() -> None:
    """leap.textbook_evidence.status=='미확인' → review_note mentions leap evidence."""
    from maieutica.verify.review_agent import review_candidates

    item = _make_flawed_quiz_leap_evidence(3)
    reviewed_quiz, _ = review_candidates([item], [], backend=None)
    note = reviewed_quiz[0].review_note
    assert note != "", "Expected non-empty review_note for 미확인 leap evidence"
    # Must name the leap issue specifically.
    assert "도약" in note or "leap" in note.lower(), (
        f"review_note does not mention leap evidence issue: {note!r}"
    )


def test_formative_evidence_unconfirmed_sets_review_note() -> None:
    """Formative item with textbook_evidence.status=='미확인' gets review_note."""
    from maieutica.verify.review_agent import review_candidates

    flawed = _make_flawed_formative_evidence(2)
    _, reviewed_formative = review_candidates([], [flawed], backend=None)
    note = reviewed_formative[0].review_note
    assert note != "", "Expected non-empty review_note for 미확인 formative evidence"


def test_mixed_batch_annotates_only_flawed() -> None:
    """Mixed batch: only flawed items get review_note; clean items stay blank."""
    from maieutica.verify.review_agent import review_candidates

    clean = _make_clean_quiz_item(1)
    flawed = _make_flawed_quiz_option_length(2)
    reviewed_quiz, _ = review_candidates([clean, flawed], [], backend=None)

    assert reviewed_quiz[0].review_note == "", "Clean item should stay blank"
    assert reviewed_quiz[1].review_note != "", "Flawed item should be annotated"


# ---------------------------------------------------------------------------
# Degrade: no backend → rules-only, no hard stop
# ---------------------------------------------------------------------------


def test_degrade_no_backend_does_not_raise() -> None:
    """review_candidates with backend=None completes without error (Constitution I)."""
    from maieutica.verify.review_agent import review_candidates

    items = [_make_clean_quiz_item(1), _make_flawed_quiz_option_length(2)]
    # Should not raise even without a backend.
    reviewed_quiz, _ = review_candidates(items, [], backend=None)
    assert len(reviewed_quiz) == 2


# ---------------------------------------------------------------------------
# candidate_yaml reader round-trip
# ---------------------------------------------------------------------------


def test_read_candidate_yaml_round_trip(tmp_path: Path) -> None:
    """read_candidate_yaml reconstructs typed models from a written yaml."""
    from maieutica.output.candidate_yaml import read_candidate_yaml, write_candidate_yaml

    quiz_items = [_make_clean_quiz_item(1)]
    formative_items = [_make_clean_formative(1)]

    dest = tmp_path / "출제후보_완전판.yaml"
    write_candidate_yaml(quiz_items, formative_items, dest)

    recovered_quiz, recovered_formative = read_candidate_yaml(dest)
    assert len(recovered_quiz) == 1
    assert len(recovered_formative) == 1
    assert isinstance(recovered_quiz[0], QuizItemCandidate)
    assert isinstance(recovered_formative[0], FormativeItemCandidate)
    assert recovered_quiz[0].item_no == quiz_items[0].item_no
    assert recovered_formative[0].no == formative_items[0].no
    assert recovered_quiz[0].review_note == ""


def test_read_candidate_yaml_preserves_review_note(tmp_path: Path) -> None:
    """review_note populated by review_candidates survives write→read round-trip."""
    from maieutica.output.candidate_yaml import read_candidate_yaml, write_candidate_yaml
    from maieutica.verify.review_agent import review_candidates

    flawed = _make_flawed_quiz_option_length(2)
    reviewed_quiz, reviewed_formative = review_candidates([flawed], [], backend=None)
    assert reviewed_quiz[0].review_note != "", "Precondition: flawed item annotated"

    dest = tmp_path / "출제후보_완전판.yaml"
    write_candidate_yaml(reviewed_quiz, reviewed_formative, dest)

    recovered_quiz, _ = read_candidate_yaml(dest)
    assert recovered_quiz[0].review_note == reviewed_quiz[0].review_note


# ---------------------------------------------------------------------------
# CLI verify subcommand
# ---------------------------------------------------------------------------


def test_cli_verify_missing_run_exits_2(tmp_path: Path) -> None:
    """verify exits 2 when the candidate yaml for the run does not exist."""
    from maieutica.cli.main import app

    bronze, data_root = _build_bronze(tmp_path)

    rc = app(
        [
            "verify",
            "--semester",
            _SEMESTER,
            "--course",
            _COURSE,
            "--week",
            str(_WEEK),
            "--generation-spec",
            str(bronze / "generation_spec.yaml"),
            "--curriculum-map",
            str(bronze / "curriculum_map.yaml"),
        ]
    )
    # Run yaml does not exist yet → exit 2.
    assert rc == 2


def test_cli_verify_after_build_exits_0_and_annotates(tmp_path: Path) -> None:
    """verify exits 0 after build, annotates a deliberately-flawed item only.

    A clean build produces only clean candidates, so the "annotates" half is
    unprovable without a flaw.  We inject one: after build, the written yaml's
    first quiz item is mutated to ``option_length_ok=False`` (a length flaw).
    The CLI verify pass must then annotate that item's ``review_note`` while
    leaving the other (clean) quiz item blank.
    """
    import os

    from maieutica.cli.main import app
    from maieutica.generate.backend import SubscriptionBackend
    from maieutica.output.candidate_yaml import read_candidate_yaml, write_candidate_yaml
    from maieutica.pipeline import build

    bronze, data_root = _build_bronze(tmp_path)
    spec = load_generation_spec(bronze / "generation_spec.yaml")
    curriculum_map = load_curriculum_map(bronze / "curriculum_map.yaml")

    silver = data_root / "silver" / "maieutica" / f"{_SEMESTER}-{_COURSE}"
    responses_dir = silver / "responses"
    _write_canned_responses(responses_dir)
    backend = SubscriptionBackend(staging_dir=silver / "staging", responses_dir=responses_dir)

    _items, run_dir = build(
        spec=spec,
        curriculum_map=curriculum_map,
        bronze_dir=bronze,
        data_root=data_root,
        backend=backend,
        generation_spec_path=bronze / "generation_spec.yaml",
        curriculum_map_path=bronze / "curriculum_map.yaml",
    )

    yaml_path = run_dir / "출제후보_완전판.yaml"

    # Inject a deliberate flaw into the FIRST quiz item (option_length_ok=False).
    quiz_items, formative_items = read_candidate_yaml(yaml_path)
    assert len(quiz_items) >= 2, "fixture must produce >=2 quiz items"
    flawed_item_no = quiz_items[0].item_no
    clean_item_no = quiz_items[1].item_no
    quiz_items[0] = quiz_items[0].model_copy(update={"option_length_ok": False})
    write_candidate_yaml(quiz_items, formative_items, yaml_path)

    # Verify from CLI (rules-only, no LLM backend → default subscription mode).
    old_cwd = os.getcwd()
    os.chdir(tmp_path)
    try:
        rc = app(
            [
                "verify",
                "--semester",
                _SEMESTER,
                "--course",
                _COURSE,
                "--week",
                str(_WEEK),
                "--generation-spec",
                str(bronze / "generation_spec.yaml"),
                "--curriculum-map",
                str(bronze / "curriculum_map.yaml"),
            ]
        )
    finally:
        os.chdir(old_cwd)

    assert rc == 0

    # The yaml must have been rewritten: flawed item annotated, clean item blank.
    doc = yaml.safe_load(yaml_path.read_text(encoding="utf-8"))
    by_no = {d["item_no"]: d for d in doc["quiz"]}
    for d in doc["quiz"]:
        assert "review_note" in d, f"review_note missing from quiz item {d['item_no']}"

    flawed_note = by_no[flawed_item_no]["review_note"]
    clean_note = by_no[clean_item_no]["review_note"]
    assert flawed_note != "", "Flawed item must be annotated after verify"
    assert "length" in flawed_note.lower() or "길이" in flawed_note, (
        f"Flawed item review_note should name the length issue: {flawed_note!r}"
    )
    assert clean_note == "", "Clean item must stay blank after verify"
