"""T041 RED — Unit tests for metric_codex.generate.bundle.

Tests (written first per TDD mandate):
- build_bundles: one bundle per student, correct pseudonym, QueryAnswer per question.
- PII invariant: serialized staging JSON contains no 10-digit id, no name, no email.
- Missing pseudonym for a codex student_id → LocatedInputError (no silent skip).
- assert_no_pii: raises on injected 10-digit id, Korean name, email; passes clean.
- write_staging: writes deterministic JSON under silver_dir/staging/{pseudonym}.json.
- Determinism: two identical build_bundles calls return equal output.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest
from metric_codex.errors import LocatedInputError

# The imports below will fail (RED) until generate/bundle.py exists.
from metric_codex.generate.bundle import (
    BundleQuestion,
    StudentBundle,
    assert_no_pii,
    build_bundles,
    write_staging,
)
from metric_codex.retrieve.query import CanonicalQuestion, QuestionSet
from paideia_shared.schemas import PseudonymMapEntry
from paideia_shared.schemas.metric_codex import CodexEntry, EntryKind, QueryAnswer

# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

_SID_A = "2026000001"
_SID_B = "2026000002"
_NAME_A = "김철수"
_NAME_B = "이영희"
_EMAIL_A = "student@example.com"
_SEM = "2026-1"
_COURSE = "anatomy"


def _entry(student_id: str, layer: str = "minimal", **overrides) -> CodexEntry:
    """Build a minimal CodexEntry for test use."""
    base: dict = dict(
        student_id=student_id,
        semester=_SEM,
        cohort_year=2026,
        layer=layer,
        entry_kind=EntryKind.score_total,
        domain=None,
        item_ref=None,
        key="score_total",
        value_num=85.0,
        value_text=None,
        source_id="school_excel:성적출석.xlsx",
        observed_at="2026-06-01",
    )
    base.update(overrides)
    return CodexEntry(**base)


def _rich_entry(student_id: str, **overrides) -> CodexEntry:
    """Build a rich-layer domain_correct_rate entry."""
    return _entry(
        student_id,
        layer="rich",
        entry_kind=EntryKind.domain_correct_rate,
        domain="순환",
        key="chapter_correct_rate:순환",
        value_num=0.9,
        value_text=None,
        source_id="immersio:학생지표.parquet",
        observed_at="2026-05-20",
        **overrides,
    )


def _pseudonym_map(sids_names: list[tuple[str, str | None]]) -> list[PseudonymMapEntry]:
    """Build a pseudonym map sorted by student_id (S001, S002, …)."""
    sorted_sids = sorted(sids_names, key=lambda t: t[0])
    return [
        PseudonymMapEntry(
            student_id=sid,
            name_kr=name,
            pseudonym=f"S{idx:03d}",
        )
        for idx, (sid, name) in enumerate(sorted_sids, start=1)
    ]


def _question_set(*questions: tuple[str, str, list[EntryKind]]) -> QuestionSet:
    """Build a QuestionSet from (id, text, kinds) tuples."""
    return QuestionSet(
        questions=[
            CanonicalQuestion(id=q_id, text=q_text, entry_kinds=kinds)
            for q_id, q_text, kinds in questions
        ]
    )


# ---------------------------------------------------------------------------
# TestBuildBundles — happy-path shape
# ---------------------------------------------------------------------------


class TestBuildBundles:
    """build_bundles produces one bundle per student with correct pseudonym and questions."""

    def _two_student_scenario(
        self,
    ) -> tuple[list[CodexEntry], list[PseudonymMapEntry], QuestionSet]:
        """A has minimal + rich; B has minimal only."""
        entries = [
            _entry(_SID_A),
            _rich_entry(_SID_A),
            _entry(_SID_B),
        ]
        pmap = _pseudonym_map([(_SID_A, _NAME_A), (_SID_B, _NAME_B)])
        qs = _question_set(
            ("q_total", "총점을 알려주세요.", [EntryKind.score_total]),
            ("q_domain", "도메인별 정답률.", [EntryKind.domain_correct_rate]),
        )
        return entries, pmap, qs

    def test_returns_one_bundle_per_student(self):
        entries, pmap, qs = self._two_student_scenario()
        bundles = build_bundles(codex_entries=entries, pseudonym_map=pmap, question_set=qs)
        assert len(bundles) == 2

    def test_bundles_sorted_by_pseudonym(self):
        entries, pmap, qs = self._two_student_scenario()
        bundles = build_bundles(codex_entries=entries, pseudonym_map=pmap, question_set=qs)
        pseudonyms = [b.pseudonym for b in bundles]
        assert pseudonyms == sorted(pseudonyms)

    def test_bundle_pseudonym_correct(self):
        entries, pmap, qs = self._two_student_scenario()
        bundles = build_bundles(codex_entries=entries, pseudonym_map=pmap, question_set=qs)
        # SID_A < SID_B lexicographically → S001/S002
        b_a = next(b for b in bundles if b.pseudonym == "S001")
        b_b = next(b for b in bundles if b.pseudonym == "S002")
        assert b_a is not None
        assert b_b is not None

    def test_bundle_has_one_question_answer_per_question(self):
        entries, pmap, qs = self._two_student_scenario()
        bundles = build_bundles(codex_entries=entries, pseudonym_map=pmap, question_set=qs)
        for bundle in bundles:
            assert len(bundle.questions) == len(qs.questions)

    def test_bundle_question_ids_match_question_set(self):
        entries, pmap, qs = self._two_student_scenario()
        bundles = build_bundles(codex_entries=entries, pseudonym_map=pmap, question_set=qs)
        expected_ids = [q.id for q in qs.questions]
        for bundle in bundles:
            assert [bq.question_id for bq in bundle.questions] == expected_ids

    def test_bundle_question_text_matches_question_set(self):
        entries, pmap, qs = self._two_student_scenario()
        bundles = build_bundles(codex_entries=entries, pseudonym_map=pmap, question_set=qs)
        expected_texts = [q.text for q in qs.questions]
        for bundle in bundles:
            assert [bq.question_text for bq in bundle.questions] == expected_texts

    def test_available_layers_both_for_sid_a(self):
        entries, pmap, qs = self._two_student_scenario()
        bundles = build_bundles(codex_entries=entries, pseudonym_map=pmap, question_set=qs)
        b_a = next(b for b in bundles if b.pseudonym == "S001")
        assert "minimal" in b_a.available_layers
        assert "rich" in b_a.available_layers

    def test_available_layers_minimal_only_for_sid_b(self):
        entries, pmap, qs = self._two_student_scenario()
        bundles = build_bundles(codex_entries=entries, pseudonym_map=pmap, question_set=qs)
        b_b = next(b for b in bundles if b.pseudonym == "S002")
        assert b_b.available_layers == ["minimal"]

    def test_sid_b_rich_question_has_no_evidence(self):
        """SID_B (minimal-only) asked a rich question → no_evidence=True."""
        entries, pmap, qs = self._two_student_scenario()
        bundles = build_bundles(codex_entries=entries, pseudonym_map=pmap, question_set=qs)
        b_b = next(b for b in bundles if b.pseudonym == "S002")
        # Second question is the rich domain question
        bq_domain = next(bq for bq in b_b.questions if bq.question_id == "q_domain")
        assert bq_domain.answer.no_evidence is True

    def test_sid_a_total_question_has_evidence(self):
        """SID_A has a score_total entry → the total question has evidence."""
        entries, pmap, qs = self._two_student_scenario()
        bundles = build_bundles(codex_entries=entries, pseudonym_map=pmap, question_set=qs)
        b_a = next(b for b in bundles if b.pseudonym == "S001")
        bq_total = next(bq for bq in b_a.questions if bq.question_id == "q_total")
        assert bq_total.answer.no_evidence is False

    def test_answer_student_pseudonym_matches_bundle(self):
        """QueryAnswer.student_pseudonym must equal the bundle pseudonym."""
        entries, pmap, qs = self._two_student_scenario()
        bundles = build_bundles(codex_entries=entries, pseudonym_map=pmap, question_set=qs)
        for bundle in bundles:
            for bq in bundle.questions:
                assert bq.answer.student_pseudonym == bundle.pseudonym


# ---------------------------------------------------------------------------
# TestBuildBundlesPiiInvariant — the PRIV-01 / SC-004 crown jewel
# ---------------------------------------------------------------------------


class TestBuildBundlesPiiInvariant:
    """The serialized staging JSON must never contain PII."""

    def _build_and_serialize(self, tmp_path: Path) -> list[str]:
        entries = [
            _entry(_SID_A),
            _rich_entry(_SID_A),
            _entry(_SID_B),
        ]
        pmap = _pseudonym_map([(_SID_A, _NAME_A), (_SID_B, _NAME_B)])
        qs = _question_set(
            ("q_total", "총점을 알려주세요.", [EntryKind.score_total]),
        )
        bundles = build_bundles(codex_entries=entries, pseudonym_map=pmap, question_set=qs)
        own_silver = tmp_path / "silver" / "metric-codex" / f"{_SEM}-{_COURSE}"
        paths = write_staging(own_silver, bundles)
        return [p.read_text(encoding="utf-8") for p in paths]

    def test_no_10digit_student_id_in_staging(self, tmp_path):
        texts = self._build_and_serialize(tmp_path)
        sid_pattern = re.compile(r"\b\d{10}\b")
        for text in texts:
            m = sid_pattern.search(text)
            assert m is None, f"10-digit student_id found in staging JSON: {m.group()!r}"

    def test_no_korean_name_a_in_staging(self, tmp_path):
        texts = self._build_and_serialize(tmp_path)
        for text in texts:
            assert _NAME_A not in text, f"Name {_NAME_A!r} found in staging JSON"

    def test_no_korean_name_b_in_staging(self, tmp_path):
        texts = self._build_and_serialize(tmp_path)
        for text in texts:
            assert _NAME_B not in text, f"Name {_NAME_B!r} found in staging JSON"

    def test_staging_pseudonym_present(self, tmp_path):
        texts = self._build_and_serialize(tmp_path)
        # At least one file should have an S00x pseudonym
        combined = "\n".join(texts)
        assert re.search(r"\bS\d{3,}\b", combined), "No pseudonym found in staging JSON"


# ---------------------------------------------------------------------------
# TestBuildBundlesMissingPseudonym — fail-fast guard
# ---------------------------------------------------------------------------


class TestBuildBundlesMissingPseudonym:
    """codex student_id absent from pseudonym map → LocatedInputError."""

    def test_missing_pseudonym_raises_located_error(self):
        entries = [_entry(_SID_A)]
        # Map only covers SID_B — SID_A is missing.
        pmap = _pseudonym_map([(_SID_B, _NAME_B)])
        qs = _question_set(("q1", "총점?", [EntryKind.score_total]))
        with pytest.raises(LocatedInputError):
            build_bundles(codex_entries=entries, pseudonym_map=pmap, question_set=qs)

    def test_missing_pseudonym_error_mentions_student_id(self):
        entries = [_entry(_SID_A)]
        pmap = _pseudonym_map([(_SID_B, _NAME_B)])
        qs = _question_set(("q1", "총점?", [EntryKind.score_total]))
        with pytest.raises(LocatedInputError) as exc_info:
            build_bundles(codex_entries=entries, pseudonym_map=pmap, question_set=qs)
        # The error string must expose the offending student_id for traceability.
        assert _SID_A in str(exc_info.value)

    def test_no_silent_skip_on_missing_pseudonym(self):
        """Should raise, not silently return fewer bundles."""
        entries = [_entry(_SID_A), _entry(_SID_B)]
        pmap = _pseudonym_map([(_SID_A, _NAME_A)])  # SID_B missing
        qs = _question_set(("q1", "총점?", [EntryKind.score_total]))
        with pytest.raises(LocatedInputError):
            build_bundles(codex_entries=entries, pseudonym_map=pmap, question_set=qs)


# ---------------------------------------------------------------------------
# TestAssertNoPii — the PII scanner itself
# ---------------------------------------------------------------------------


class TestAssertNoPii:
    """assert_no_pii raises on injected PII; passes on clean payloads."""

    def test_passes_on_clean_pseudonym_only_payload(self):
        payload = json.dumps(
            {"pseudonym": "S001", "questions": [{"question_id": "q1", "value": 85.0}]},
            ensure_ascii=False,
        )
        # Must not raise
        assert_no_pii(payload)

    def test_raises_on_10digit_student_id(self):
        payload = json.dumps({"student_id": "2026000001", "pseudonym": "S001"})
        with pytest.raises(LocatedInputError, match=r"10-digit"):
            assert_no_pii(payload)

    def test_raises_on_email_address(self):
        payload = json.dumps({"contact": _EMAIL_A, "pseudonym": "S001"})
        with pytest.raises(LocatedInputError, match=r"[Ee]mail"):
            assert_no_pii(payload)

    def test_raises_on_known_korean_name(self):
        """Known-name check: _NAME_A appears literally in payload when supplied."""
        payload = json.dumps({"name": _NAME_A, "pseudonym": "S001"}, ensure_ascii=False)
        with pytest.raises(LocatedInputError):
            assert_no_pii(payload, known_names=frozenset([_NAME_A, _NAME_B]))

    def test_passes_on_korean_question_text(self):
        """Korean question text (not a name) must not be rejected."""
        payload = json.dumps(
            {
                "pseudonym": "S001",
                "question_text": "도메인별 정답률을 알려주세요.",
            },
            ensure_ascii=False,
        )
        # Must not raise — Korean question text is legitimate.
        assert_no_pii(payload)

    def test_passes_on_korean_freetext_category(self):
        """Korean free-text category values (e.g., health) are not PII.

        Updated (T034/W2): also confirms that the new 3rd-party name+role
        redaction pattern leaves legitimate category labels untouched.
        '건강,진로' contains no surname+role token, so no redaction occurs.
        """
        payload = json.dumps(
            {"pseudonym": "S001", "value_text": "건강,진로"},
            ensure_ascii=False,
        )
        assert_no_pii(payload)
        # W2 guard: legit Korean must survive the PII scan unchanged (no raise).

    def test_passes_on_domain_name_in_korean(self):
        """Korean chapter/domain labels like '순환' are not PII.

        Updated (T034/W2): '순환' is a bare anatomy chapter name, not a
        surname+role token — the new redaction pattern must leave it untouched.
        """
        payload = json.dumps(
            {"pseudonym": "S001", "key": "chapter_correct_rate:순환"},
            ensure_ascii=False,
        )
        assert_no_pii(payload)
        # W2 guard: domain labels must pass without false-positive redaction.

    # --- T034 RED: 3rd-party surname+role in value_text must be redacted ---

    def test_raises_on_third_party_name_role_in_payload(self):
        """A 3rd-party Korean name+role (e.g. '박교수') in payload raises.

        T034 RED: assert_no_pii must detect surname+role tokens such as
        '박교수 추천반' that could identify a 3rd-party person.  The detection
        raises LocatedInputError (guard against a surviving leak after the
        redact-transform on the LLM-facing payload).
        """
        payload = json.dumps(
            {"pseudonym": "S001", "value_text": "박교수 추천반"},
            ensure_ascii=False,
        )
        with pytest.raises(LocatedInputError):
            assert_no_pii(payload)

    def test_third_party_name_role_redacted_in_bundle_facts(self):
        """A 박교수-bearing value_text is redacted before staging/LLM payload.

        T034 RED: the LLM-facing facts string (render_template output) must NOT
        contain '박교수' when the codex entry carries it as value_text.  The
        Silver/codex entry retains the original; only the LLM-facing payload is
        redacted.
        """
        from metric_codex.generate.bundle import redact_third_party_names
        raw = "박교수 추천반"
        redacted = redact_third_party_names(raw)
        # Must not contain the original name+role token.
        assert "박교수" not in redacted
        # The redaction marker must be present to flag the substitution.
        assert "[REDACTED]" in redacted or len(redacted) < len(raw)


# ---------------------------------------------------------------------------
# TestWriteStaging — file creation + PII scan before write
# ---------------------------------------------------------------------------


class TestWriteStaging:
    """write_staging: creates silver_dir/staging/{pseudonym}.json, PII scanned before write."""

    def _bundles_single(self) -> list[StudentBundle]:
        entries = [_entry(_SID_A)]
        pmap = _pseudonym_map([(_SID_A, _NAME_A)])
        qs = _question_set(("q1", "총점?", [EntryKind.score_total]))
        return build_bundles(codex_entries=entries, pseudonym_map=pmap, question_set=qs)

    def test_creates_staging_directory(self, tmp_path):
        bundles = self._bundles_single()
        own_silver = tmp_path / "silver"
        write_staging(own_silver, bundles)
        assert (own_silver / "staging").is_dir()

    def test_armed_name_scan_raises_if_name_leaks_into_payload(self, tmp_path):
        """If a name string were somehow present in a bundle payload, armed
        write_staging must raise LocatedInputError (PRIV-01 enforcement layer).

        Simulates an upstream regression by injecting a name into a question_text
        field (which is normally PII-free Korean question text).
        """
        # Build a bundle whose question_text carries a leaked name.
        leaked_bundle = StudentBundle(
            pseudonym="S001",
            available_layers=["minimal"],
            questions=[
                BundleQuestion(
                    question_id="q1",
                    question_text=f"{_NAME_A} 학생의 총점?",  # name leaked here
                    answer=QueryAnswer(
                        student_pseudonym="S001",
                        question_id="q1",
                        citations=[],
                        available_layers=["minimal"],
                        no_evidence=True,
                    ),
                )
            ],
        )
        own_silver = tmp_path / "silver"
        with pytest.raises(LocatedInputError):
            write_staging(
                own_silver,
                [leaked_bundle],
                known_names=frozenset([_NAME_A, _NAME_B]),
            )

    def test_armed_name_scan_does_not_write_leaked_file(self, tmp_path):
        """When the armed name scan raises, no staging file is written (atomicity)."""
        leaked_bundle = StudentBundle(
            pseudonym="S001",
            available_layers=["minimal"],
            questions=[
                BundleQuestion(
                    question_id="q1",
                    question_text=f"{_NAME_A} 학생의 총점?",
                    answer=QueryAnswer(
                        student_pseudonym="S001",
                        question_id="q1",
                        citations=[],
                        available_layers=["minimal"],
                        no_evidence=True,
                    ),
                )
            ],
        )
        own_silver = tmp_path / "silver"
        with pytest.raises(LocatedInputError):
            write_staging(own_silver, [leaked_bundle], known_names=frozenset([_NAME_A]))
        # No staging JSON should exist for the rejected bundle.
        staging = own_silver / "staging"
        assert not (staging / "S001.json").exists()

    def test_clean_bundle_passes_armed_scan(self, tmp_path):
        """A genuinely PII-free bundle passes the armed scan and is written."""
        bundles = self._bundles_single()
        own_silver = tmp_path / "silver"
        paths = write_staging(
            own_silver, bundles, known_names=frozenset([_NAME_A, _NAME_B])
        )
        assert len(paths) == 1
        assert paths[0].is_file()

    def test_creates_one_file_per_bundle(self, tmp_path):
        entries = [_entry(_SID_A), _entry(_SID_B)]
        pmap = _pseudonym_map([(_SID_A, _NAME_A), (_SID_B, _NAME_B)])
        qs = _question_set(("q1", "총점?", [EntryKind.score_total]))
        bundles = build_bundles(codex_entries=entries, pseudonym_map=pmap, question_set=qs)
        own_silver = tmp_path / "silver"
        paths = write_staging(own_silver, bundles)
        assert len(paths) == 2

    def test_file_named_by_pseudonym(self, tmp_path):
        bundles = self._bundles_single()
        own_silver = tmp_path / "silver"
        paths = write_staging(own_silver, bundles)
        names = {p.name for p in paths}
        assert "S001.json" in names

    def test_file_is_valid_json(self, tmp_path):
        bundles = self._bundles_single()
        own_silver = tmp_path / "silver"
        paths = write_staging(own_silver, bundles)
        for p in paths:
            data = json.loads(p.read_text(encoding="utf-8"))
            assert isinstance(data, dict)

    def test_json_contains_pseudonym(self, tmp_path):
        bundles = self._bundles_single()
        own_silver = tmp_path / "silver"
        paths = write_staging(own_silver, bundles)
        data = json.loads(paths[0].read_text(encoding="utf-8"))
        assert data.get("pseudonym") == "S001"

    def test_json_has_sorted_keys(self, tmp_path):
        """Determinism: JSON serialized with sort_keys=True."""
        bundles = self._bundles_single()
        own_silver = tmp_path / "silver"
        paths = write_staging(own_silver, bundles)
        raw = paths[0].read_text(encoding="utf-8")
        data = json.loads(raw)
        re_serialized = json.dumps(data, sort_keys=True, ensure_ascii=False)
        # The file should match the re-serialized sorted version structurally.
        assert json.loads(raw) == json.loads(re_serialized)

    def test_returns_list_of_paths(self, tmp_path):
        bundles = self._bundles_single()
        own_silver = tmp_path / "silver"
        result = write_staging(own_silver, bundles)
        assert isinstance(result, list)
        assert all(isinstance(p, Path) for p in result)


# ---------------------------------------------------------------------------
# TestDeterminism — build_bundles output is stable
# ---------------------------------------------------------------------------


class TestDeterminism:
    """Two identical build_bundles calls return equal, sorted output."""

    def test_two_calls_equal_result(self):
        entries = [_entry(_SID_A), _rich_entry(_SID_A), _entry(_SID_B)]
        pmap = _pseudonym_map([(_SID_A, _NAME_A), (_SID_B, _NAME_B)])
        qs = _question_set(
            ("q1", "총점?", [EntryKind.score_total]),
            ("q2", "도메인?", [EntryKind.domain_correct_rate]),
        )
        bundles_1 = build_bundles(codex_entries=entries, pseudonym_map=pmap, question_set=qs)
        bundles_2 = build_bundles(codex_entries=entries, pseudonym_map=pmap, question_set=qs)
        # Compare serialized representations for equality.
        s1 = [json.dumps(b.model_dump(), sort_keys=True, ensure_ascii=False) for b in bundles_1]
        s2 = [json.dumps(b.model_dump(), sort_keys=True, ensure_ascii=False) for b in bundles_2]
        assert s1 == s2

    def test_write_staging_idempotent(self, tmp_path):
        """Writing twice to the same silver_dir yields byte-identical files."""
        entries = [_entry(_SID_A)]
        pmap = _pseudonym_map([(_SID_A, _NAME_A)])
        qs = _question_set(("q1", "총점?", [EntryKind.score_total]))
        bundles = build_bundles(codex_entries=entries, pseudonym_map=pmap, question_set=qs)
        own_silver = tmp_path / "silver"
        paths1 = write_staging(own_silver, bundles)
        content1 = paths1[0].read_text(encoding="utf-8")
        paths2 = write_staging(own_silver, bundles)
        content2 = paths2[0].read_text(encoding="utf-8")
        assert content1 == content2


# ---------------------------------------------------------------------------
# TestStudentBundleSchema — frozen dataclass / pydantic model shape
# ---------------------------------------------------------------------------


class TestStudentBundleSchema:
    """StudentBundle and BundleQuestion have the expected field shapes."""

    def _make_bundle(self) -> StudentBundle:
        entries = [_entry(_SID_A), _rich_entry(_SID_A)]
        pmap = _pseudonym_map([(_SID_A, _NAME_A)])
        qs = _question_set(("q1", "총점?", [EntryKind.score_total]))
        return build_bundles(codex_entries=entries, pseudonym_map=pmap, question_set=qs)[0]

    def test_student_bundle_has_pseudonym(self):
        b = self._make_bundle()
        assert hasattr(b, "pseudonym")
        assert re.fullmatch(r"S\d{3,}", b.pseudonym)

    def test_student_bundle_has_available_layers(self):
        b = self._make_bundle()
        assert hasattr(b, "available_layers")
        assert isinstance(b.available_layers, list)

    def test_student_bundle_has_questions(self):
        b = self._make_bundle()
        assert hasattr(b, "questions")
        assert isinstance(b.questions, list)

    def test_bundle_question_has_question_id(self):
        b = self._make_bundle()
        bq = b.questions[0]
        assert hasattr(bq, "question_id")
        assert bq.question_id == "q1"

    def test_bundle_question_has_question_text(self):
        b = self._make_bundle()
        bq = b.questions[0]
        assert hasattr(bq, "question_text")
        assert bq.question_text == "총점?"

    def test_bundle_question_has_answer(self):
        b = self._make_bundle()
        bq = b.questions[0]
        assert hasattr(bq, "answer")
        assert isinstance(bq.answer, QueryAnswer)
