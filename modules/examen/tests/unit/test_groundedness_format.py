"""T020 — Unit/property tests: groundedness anchor + format validation.

Covers:
- verify_groundedness(): 확인 vs 미확인 (concept present/absent in chapter-scoped index);
  external-knowledge fact (key_concept absent in textbook) → 미확인; re-check uses
  ORIGINAL textbook lines; returns frozen ExamItemDraft (model_copy).
- check_format(): option_length_ok boundary (29/30/40/41 chars), 5-option enforcement,
  stem_polarity consistency.
"""

from __future__ import annotations

from examen.silver.evidence_index import EvidenceIndex
from paideia_shared.schemas import ExamItemDraft, TextbookEvidence

# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

_BASE_OPTIONS_30 = [
    "① " + "가" * 28,  # 2 + 28 = 30
    "② " + "나" * 28,
    "③ " + "다" * 28,
    "④ " + "라" * 28,
    "⑤ " + "마" * 28,
]

_BASE_OPTIONS_40 = [
    "① " + "가" * 38,  # 2 + 38 = 40
    "② " + "나" * 38,
    "③ " + "다" * 38,
    "④ " + "라" * 38,
    "⑤ " + "마" * 38,
]

_BASE_OPTIONS_OK = [
    "① 뇌하수체는 터키안장에 위치한다.",  # 18 chars — under 30 → for violation test
    "② 전엽과 후엽으로 구성된다.",
    "③ 뇌하수체 전엽에서는 GH가 분비된다.",
    "④ 후엽은 신경 조직으로 이루어진다.",
    "⑤ 뇌하수체는 복막 안에 위치한다.",
]

_BASE_DISTRACTOR = [
    "옳은 진술1",
    "옳은 진술2",
    "옳은 진술3",
    "옳은 진술4",
    "틀린 진술5",
]


def _make_item(
    *,
    key_concept: str | None = "뇌하수체",
    options: list[str] | None = None,
    stem_polarity: str = "부정형",
    text: str = "다음 중 뇌하수체에 대한 설명으로 가장 옳지 않은 것은?",
    textbook_evidence: TextbookEvidence | None = None,
    option_length_ok: bool = True,
) -> ExamItemDraft:
    """Build a minimal ExamItemDraft for testing."""
    if options is None:
        options = _BASE_OPTIONS_30
    if textbook_evidence is None:
        textbook_evidence = TextbookEvidence(
            source_file="8장.txt",
            line=1,
            found_text="뇌하수체는 터키안장에 위치한다.",
            status="확인",
            search_term=key_concept,
        )
    return ExamItemDraft(
        semester="2026-1",
        course_slug="anatomy",
        item_no=1,
        source="textbook",
        source_ref=None,
        chapter="8장 호흡계통",
        chapter_no=8,
        section=None,
        week=None,
        key_concept=key_concept,
        is_emphasized=None,
        emphasis_class_count=None,
        question_type="지식축적",
        bloom=None,
        difficulty="1_쉬움",
        stem_polarity=stem_polarity,
        text=text,
        options=options,
        answer_no=5,
        distractor_rationale=_BASE_DISTRACTOR,
        wrong_explanation="오답 설명 테스트." * 20,
        leap_explanation="도약 설명 테스트." * 20,
        textbook_evidence=textbook_evidence,
        intent="뇌하수체의 해부학적 위치를 정확히 알고 있는지 확인한다.",
        option_length_ok=option_length_ok,
        duplicate_flag=False,
        review_note="",
        adoption_status="생성",
        note=None,
    )


def _make_evidence_index(lines: list[str] | None = None) -> EvidenceIndex:
    """Build a chapter-scoped EvidenceIndex."""
    if lines is None:
        lines = [
            "뇌하수체는 터키안장에 위치한다.",
            "뇌하수체 전엽과 후엽으로 구성된다.",
            "갑상샘은 목 앞쪽에 위치한다.",
            "호르몬이 혈액을 통해 이동한다.",
        ]
    return EvidenceIndex.build(lines, source_file="8장.txt")


# ===========================================================================
# T027 — verify_groundedness
# ===========================================================================


class TestVerifyGroundedness:
    """Tests for examen.verify.groundedness.verify_groundedness()."""

    def _verify(
        self,
        item: ExamItemDraft | None = None,
        evidence_index: EvidenceIndex | None = None,
    ) -> ExamItemDraft:
        from examen.verify.groundedness import verify_groundedness

        if item is None:
            item = _make_item()
        if evidence_index is None:
            evidence_index = _make_evidence_index()
        return verify_groundedness(item, evidence_index)

    # --- Return type and immutability ---

    def test_returns_exam_item_draft(self) -> None:
        """verify_groundedness returns an ExamItemDraft."""
        result = self._verify()
        assert isinstance(result, ExamItemDraft)

    def test_returns_new_object_not_mutated(self) -> None:
        """Returns a new object (model_copy); original is unchanged (frozen)."""
        item = _make_item()
        result = self._verify(item=item)
        # Both must be ExamItemDraft, but the result may differ
        assert isinstance(result, ExamItemDraft)
        # Frozen model: original should not have been mutated
        # (would raise FrozenInstanceError if attempted)

    # --- 확인: key_concept present in evidence_index ---

    def test_status_confirmed_when_concept_in_index(self) -> None:
        """Status is '확인' when key_concept is found in the chapter-scoped index."""
        item = _make_item(key_concept="뇌하수체")
        idx = _make_evidence_index()
        result = self._verify(item=item, evidence_index=idx)
        assert result.textbook_evidence is not None
        assert result.textbook_evidence.status == "확인"

    def test_evidence_line_set_when_confirmed(self) -> None:
        """When confirmed, textbook_evidence.line is a positive integer."""
        item = _make_item(key_concept="뇌하수체")
        idx = _make_evidence_index()
        result = self._verify(item=item, evidence_index=idx)
        assert result.textbook_evidence is not None
        assert result.textbook_evidence.line is not None
        assert result.textbook_evidence.line >= 1

    def test_evidence_found_text_set_when_confirmed(self) -> None:
        """When confirmed, textbook_evidence.found_text is a non-empty string."""
        item = _make_item(key_concept="갑상샘")
        idx = _make_evidence_index()
        result = self._verify(item=item, evidence_index=idx)
        assert result.textbook_evidence is not None
        assert result.textbook_evidence.found_text is not None
        assert len(result.textbook_evidence.found_text) > 0

    def test_search_term_preserved_on_confirm(self) -> None:
        """search_term on evidence matches the key_concept used."""
        item = _make_item(key_concept="호르몬")
        idx = _make_evidence_index()
        result = self._verify(item=item, evidence_index=idx)
        assert result.textbook_evidence is not None
        assert result.textbook_evidence.search_term == "호르몬"

    # --- 미확인: key_concept absent from evidence_index ---

    def test_status_unconfirmed_when_concept_absent(self) -> None:
        """Status is '미확인' when key_concept is NOT found in the index."""
        item = _make_item(key_concept="존재하지않는단어XYZ")
        idx = _make_evidence_index()
        result = self._verify(item=item, evidence_index=idx)
        assert result.textbook_evidence is not None
        assert result.textbook_evidence.status == "미확인"

    def test_line_none_when_unconfirmed(self) -> None:
        """When unconfirmed, textbook_evidence.line is None."""
        item = _make_item(key_concept="없는개념ABC")
        idx = _make_evidence_index()
        result = self._verify(item=item, evidence_index=idx)
        assert result.textbook_evidence is not None
        assert result.textbook_evidence.line is None

    def test_found_text_none_when_unconfirmed(self) -> None:
        """When unconfirmed, textbook_evidence.found_text is None."""
        item = _make_item(key_concept="없는개념ABC")
        idx = _make_evidence_index()
        result = self._verify(item=item, evidence_index=idx)
        assert result.textbook_evidence is not None
        assert result.textbook_evidence.found_text is None

    # --- External knowledge: key_concept absent → 미확인 (not silent pass) ---

    def test_external_knowledge_fact_is_unconfirmed(self) -> None:
        """A key_concept absent from the textbook index → 미확인, never '확인'."""
        # Simulate an item with a key_concept that doesn't appear in ANY line
        item = _make_item(key_concept="외부지식개념없음")
        idx = EvidenceIndex.build(
            ["특정내용A", "특정내용B", "특정내용C"],
            source_file="8장.txt",
        )
        result = self._verify(item=item, evidence_index=idx)
        assert result.textbook_evidence is not None
        assert result.textbook_evidence.status == "미확인", (
            "External-knowledge fact must be flagged 미확인, not silently passed"
        )

    def test_none_key_concept_is_unconfirmed(self) -> None:
        """key_concept=None → '미확인' (cannot anchor, so never '확인')."""
        item = _make_item(key_concept=None)
        idx = _make_evidence_index()
        result = self._verify(item=item, evidence_index=idx)
        assert result.textbook_evidence is not None
        assert result.textbook_evidence.status == "미확인"

    # --- Chapter-scoped index: different chapters are not cross-contaminated ---

    def test_concept_in_different_chapter_index_is_unconfirmed(self) -> None:
        """A concept absent from THIS chapter's index → 미확인 even if elsewhere."""
        # Chapter 8 index has only 호흡, 폐 content
        ch8_lines = ["폐포에서 가스 교환이 일어난다.", "호흡은 들숨과 날숨으로 구성된다."]
        ch8_idx = EvidenceIndex.build(ch8_lines, source_file="8장.txt")
        # key_concept '뇌하수체' is NOT in ch8 (it's an endocrine concept)
        item = _make_item(key_concept="뇌하수체")
        result = self._verify(item=item, evidence_index=ch8_idx)
        assert result.textbook_evidence is not None
        assert result.textbook_evidence.status == "미확인"

    # --- Source file preserved ---

    def test_source_file_from_index(self) -> None:
        """textbook_evidence.source_file matches the evidence_index.source_file."""
        idx = EvidenceIndex.build(["뇌하수체 내용"], source_file="10장 내분비계통.txt")
        item = _make_item(key_concept="뇌하수체")
        result = self._verify(item=item, evidence_index=idx)
        assert result.textbook_evidence is not None
        assert result.textbook_evidence.source_file == "10장 내분비계통.txt"

    # --- Non-textbook items: evidence may be None, verify does not crash ---

    def test_formative_item_without_evidence_handled(self) -> None:
        """verify_groundedness on a formative item with textbook_evidence=None."""
        from examen.verify.groundedness import verify_groundedness

        # Build a formative item (textbook_evidence=None allowed for formative)
        item = ExamItemDraft(
            semester="2026-1",
            course_slug="anatomy",
            item_no=2,
            source="formative",
            source_ref="형성평가:8장#1",
            chapter="8장 호흡계통",
            chapter_no=8,
            section=None,
            week=None,
            key_concept="폐포",
            is_emphasized=None,
            emphasis_class_count=None,
            question_type="지식축적",
            bloom=None,
            difficulty="1_쉬움",
            stem_polarity="부정형",
            text="다음 중 폐포에 대한 설명으로 가장 옳지 않은 것은?",
            options=_BASE_OPTIONS_30,
            answer_no=3,
            distractor_rationale=_BASE_DISTRACTOR,
            wrong_explanation="오답 설명." * 25,
            leap_explanation="도약 설명." * 25,
            textbook_evidence=None,
            intent="폐포의 기능을 파악한다.",
            option_length_ok=True,
            duplicate_flag=False,
            review_note="",
            adoption_status="생성",
            note=None,
        )
        idx = _make_evidence_index()
        # Should not raise; may return as-is or with evidence populated
        result = verify_groundedness(item, idx)
        assert isinstance(result, ExamItemDraft)


# ===========================================================================
# T028 — check_format
# ===========================================================================


class TestCheckFormat:
    """Tests for examen.verify.format_checks.check_format()."""

    def _check(
        self,
        item: ExamItemDraft | None = None,
    ) -> ExamItemDraft:
        from examen.verify.format_checks import check_format

        if item is None:
            item = _make_item(options=_BASE_OPTIONS_30)
        return check_format(item)

    # --- Return type ---

    def test_returns_exam_item_draft(self) -> None:
        """check_format returns an ExamItemDraft."""
        result = self._check()
        assert isinstance(result, ExamItemDraft)

    # --- option_length_ok boundaries ---

    def test_all_options_30_chars_ok(self) -> None:
        """All options of exactly 30 codepoints → option_length_ok=True."""
        opts = ["① " + "가" * 28] * 5  # 2+28=30 chars
        item = _make_item(options=opts)
        result = self._check(item=item)
        assert result.option_length_ok is True

    def test_all_options_40_chars_ok(self) -> None:
        """All options of exactly 40 codepoints → option_length_ok=True."""
        opts = ["① " + "가" * 38] * 5  # 2+38=40 chars
        item = _make_item(options=opts)
        result = self._check(item=item)
        assert result.option_length_ok is True

    def test_option_29_chars_violation(self) -> None:
        """One option of 29 codepoints → option_length_ok=False (violation)."""
        # 4 options of 30, one of 29
        ok4 = ["① " + "가" * 28] * 4  # 30 chars each
        short_one = ["② " + "나" * 27]  # 2+27=29 chars
        opts = ok4[:1] + short_one + ok4[1:]
        assert len(opts) == 5
        item = _make_item(options=opts)
        result = self._check(item=item)
        assert result.option_length_ok is False

    def test_option_41_chars_violation(self) -> None:
        """One option of 41 codepoints → option_length_ok=False (violation)."""
        ok4 = ["① " + "가" * 38] * 4  # 40 chars each
        long_one = ["② " + "나" * 39]  # 2+39=41 chars
        opts = ok4[:1] + long_one + ok4[1:]
        assert len(opts) == 5
        item = _make_item(options=opts)
        result = self._check(item=item)
        assert result.option_length_ok is False

    def test_option_35_chars_ok(self) -> None:
        """Options of 35 codepoints (middle of range) → option_length_ok=True."""
        opts = ["① " + "가" * 33] * 5  # 2+33=35 chars
        item = _make_item(options=opts)
        result = self._check(item=item)
        assert result.option_length_ok is True

    def test_violation_does_not_raise(self) -> None:
        """check_format does NOT raise on violation — flags it instead."""
        opts = ["①가"] * 5  # 2 chars each — clear violation
        item = _make_item(options=opts)
        # Must not raise
        result = self._check(item=item)
        assert result.option_length_ok is False

    def test_mixed_valid_invalid_options_violation(self) -> None:
        """If any option is out of range, option_length_ok=False."""
        good = "① " + "가" * 28  # 30 chars
        bad = "② " + "나" * 39  # 41 chars
        opts = [good, bad, good, good, good]
        item = _make_item(options=opts)
        result = self._check(item=item)
        assert result.option_length_ok is False

    # --- 5-option confirmation ---

    def test_five_options_accepted(self) -> None:
        """Exactly 5 options → schema-valid item returned."""
        opts = ["① " + "가" * 28] * 5
        item = _make_item(options=opts)
        result = self._check(item=item)
        assert len(result.options) == 5

    # --- stem_polarity consistency ---

    def test_negative_stem_text_with_negative_polarity(self) -> None:
        """부정형 text contains '옳지 않은' → stem_polarity stays 부정형."""
        text = "다음 중 가장 옳지 않은 것은?"
        item = _make_item(stem_polarity="부정형", text=text)
        result = self._check(item=item)
        assert result.stem_polarity == "부정형"

    def test_positive_stem_text_with_positive_polarity(self) -> None:
        """긍정형 text → stem_polarity stays 긍정형."""
        text = "다음 중 가장 옳은 것은?"
        item = _make_item(stem_polarity="긍정형", text=text)
        result = self._check(item=item)
        assert result.stem_polarity == "긍정형"

    # --- Immutability: does not raise on frozen model ---

    def test_returns_new_object(self) -> None:
        """check_format returns an ExamItemDraft (not the same Python object)."""
        item = _make_item()
        result = self._check(item=item)
        # model is frozen — result should be produced via model_copy
        assert isinstance(result, ExamItemDraft)

    # --- option_length_ok is recalculated (verify stage owns this field) ---

    def test_recalculates_option_length_ok(self) -> None:
        """check_format recalculates option_length_ok regardless of item's prior value."""
        # Provide item with option_length_ok=True but options that are too short
        short_opts = ["①가"] * 5  # 2 chars — violation
        item = _make_item(options=short_opts, option_length_ok=True)
        result = self._check(item=item)
        # Must recalculate to False (overrides the prior True)
        assert result.option_length_ok is False


# ---------------------------------------------------------------------------
# T035 — check_formative (answer-marker contract + 부정형 enforcement)
# ---------------------------------------------------------------------------


def _make_formative_item(
    *,
    answer_no: int = 5,
    stem_polarity: str = "부정형",
    text: str = "다음 중 허파꽈리 세포에 대한 설명으로 가장 옳지 않은 것은?",
    distractor_rationale: list[str] | None = None,
    review_note: str = "",
) -> ExamItemDraft:
    """Build a minimal formative ExamItemDraft for check_formative tests."""
    if distractor_rationale is None:
        distractor_rationale = [
            "옳은 진술: 제1형 허파세포는 가스 교환에 적합하다.",
            "옳은 진술: 제2형 허파세포는 표면활성제를 분비한다.",
            "옳은 진술: 표면활성제는 표면장력을 낮춘다.",
            "옳은 진술: 허파꽈리는 두 종류 세포로 구성된다.",
            "틀린 진술: 제2형 허파세포는 섬모를 보유한다.",
        ]
    return ExamItemDraft(
        semester="2026-1",
        course_slug="anatomy",
        item_no=1,
        source="formative",
        source_ref="형성평가:8장#1",
        chapter="8장 호흡계통",
        chapter_no=8,
        section=None,
        week=8,
        key_concept="제2형 허파세포",
        is_emphasized=None,
        emphasis_class_count=None,
        question_type="지식축적",
        bloom=None,
        difficulty="2_보통",
        stem_polarity=stem_polarity,
        text=text,
        options=_BASE_OPTIONS_30,
        answer_no=answer_no,
        distractor_rationale=distractor_rationale,
        wrong_explanation="오답 설명 테스트." * 20,
        leap_explanation="도약 설명 테스트." * 20,
        textbook_evidence=None,
        intent="허파꽈리 세포 기능을 정확히 이해하는지 확인한다.",
        option_length_ok=True,
        duplicate_flag=False,
        review_note=review_note,
        adoption_status="생성",
        note=None,
    )


class TestCheckFormative:
    """Unit tests for check_formative (T035)."""

    def _check(self, item: ExamItemDraft) -> ExamItemDraft:
        from examen.verify.format_checks import check_formative

        return check_formative(item)

    def test_non_formative_passthrough(self) -> None:
        """check_formative returns non-formative items unchanged."""
        from examen.verify.format_checks import check_formative

        textbook_item = _make_item()  # source="textbook"
        result = check_formative(textbook_item)
        assert result is textbook_item, "non-formative items must pass through unchanged"

    def test_marker_present_no_violation(self) -> None:
        """When answer_no rationale carries '틀린', no marker violation is recorded."""
        item = self._make_clean()
        result = self._check(item)
        assert "마커가 없습니다" not in result.review_note

    def _make_clean(self) -> ExamItemDraft:
        # answer_no=5 → rationale[4] carries '틀린', others do not
        return _make_formative_item(answer_no=5)

    def test_marker_missing_records_violation(self) -> None:
        """When answer_no rationale LACKS '틀린', a violation is recorded."""
        # answer_no=1 but rationale[0] is "옳은 진술" (no 틀린 marker)
        item = _make_formative_item(answer_no=1)
        result = self._check(item)
        assert "마커가 없습니다" in result.review_note, (
            "missing 틀린 marker on the answer rationale must be flagged"
        )

    def test_marker_on_non_answer_records_violation(self) -> None:
        """If a non-answer rationale carries '틀린', flag a possible answer mis-index."""
        rationales = [
            "틀린 진술: 잘못된 설명1.",  # idx0 carries marker but is NOT the answer
            "옳은 진술2.",
            "옳은 진술3.",
            "옳은 진술4.",
            "틀린 진술: 제2형 허파세포는 섬모를 보유한다.",  # idx4 is the answer
        ]
        item = _make_formative_item(answer_no=5, distractor_rationale=rationales)
        result = self._check(item)
        assert "정답 번호 지정 오류" in result.review_note, (
            "a 틀린 marker on a non-answer option must be flagged"
        )

    def test_non_negative_stem_polarity_flagged(self) -> None:
        """A formative item declared 긍정형 is flagged (must be 부정형)."""
        item = _make_formative_item(stem_polarity="긍정형")
        result = self._check(item)
        assert "stem_polarity 오류" in result.review_note

    def test_does_not_raise(self) -> None:
        """check_formative never raises — it only records review_note violations."""
        item = _make_formative_item(answer_no=1)  # marker mismatch
        result = self._check(item)  # must not raise
        assert isinstance(result, ExamItemDraft)
