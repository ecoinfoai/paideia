"""T035 RED — US2 deterministic evidence retrieval integration tests (spec 013).

Scenario B: one student with BOTH layers (minimal score entries + rich
domain_correct_rate/freetext entries).
"""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest
from metric_codex.errors import LocatedInputError
from metric_codex.retrieve.evidence import retrieve_evidence
from metric_codex.retrieve.query import (
    CanonicalQuestion,
    QuestionSet,
    answer_question,
    load_question_set,
)

# These imports will fail (RED) until the implementation is done.
from paideia_shared.schemas.metric_codex import (
    CodexEntry,
    EntryKind,
    QueryAnswer,
)

# ---------------------------------------------------------------------------
# Synthetic entry builder
# ---------------------------------------------------------------------------

_SID = "2026000001"
_SEM = "2026-1"


def _entry(**overrides) -> CodexEntry:
    base = dict(
        student_id=_SID,
        semester=_SEM,
        cohort_year=2026,
        layer="minimal",
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


def _make_both_layer_entries() -> list[CodexEntry]:
    """Build a list with minimal + rich entries for one student."""
    return [
        # --- minimal layer ---
        _entry(
            layer="minimal",
            entry_kind=EntryKind.score_total,
            key="score_total",
            value_num=85.0,
            source_id="school_excel:성적출석.xlsx",
            observed_at="2026-06-01",
        ),
        _entry(
            layer="minimal",
            entry_kind=EntryKind.score_percent,
            key="score_percent",
            value_num=90.5,
            source_id="school_excel:성적출석.xlsx",
            observed_at="2026-06-01",
        ),
        _entry(
            layer="minimal",
            entry_kind=EntryKind.attendance,
            key="attendance",
            value_num=15.0,
            source_id="school_excel:성적출석.xlsx",
            observed_at="2026-06-01",
        ),
        # --- rich layer ---
        _entry(
            layer="rich",
            entry_kind=EntryKind.domain_correct_rate,
            domain="순환",
            key="chapter_correct_rate:순환",
            value_num=0.9,
            source_id="immersio:학생지표.parquet",
            observed_at="2026-05-20",
        ),
        _entry(
            layer="rich",
            entry_kind=EntryKind.domain_correct_rate,
            domain="호흡",
            key="chapter_correct_rate:호흡",
            value_num=0.5,
            source_id="immersio:학생지표.parquet",
            observed_at="2026-05-20",
        ),
        _entry(
            layer="rich",
            entry_kind=EntryKind.freetext_category,
            key="freetext_category:q9",
            value_num=None,
            value_text="health,career",
            source_id="needs-map:free_text_categorization.parquet",
            observed_at=None,
        ),
    ]


def _make_minimal_only_entries() -> list[CodexEntry]:
    """Build a list with ONLY minimal entries (no rich layer)."""
    return [
        _entry(
            layer="minimal",
            entry_kind=EntryKind.score_total,
            key="score_total",
            value_num=70.0,
            source_id="school_excel:성적출석.xlsx",
            observed_at="2026-06-01",
        ),
        _entry(
            layer="minimal",
            entry_kind=EntryKind.attendance,
            key="attendance",
            value_num=12.0,
            source_id="school_excel:성적출석.xlsx",
            observed_at="2026-06-01",
        ),
    ]


# ---------------------------------------------------------------------------
# SC-002: retrieve_evidence — rich-layer question, both layers present
# ---------------------------------------------------------------------------


class TestRetrieveEvidenceRichQuestion:
    """SC-002: rich-layer question on a both-layers student."""

    def test_no_evidence_false(self):
        entries = _make_both_layer_entries()
        _, _, no_evidence = retrieve_evidence(
            entries,
            entry_kinds={EntryKind.domain_correct_rate},
        )
        assert no_evidence is False

    def test_citations_non_empty(self):
        entries = _make_both_layer_entries()
        citations, _, _ = retrieve_evidence(
            entries,
            entry_kinds={EntryKind.domain_correct_rate},
        )
        assert len(citations) > 0

    def test_every_citation_matches_input_entry(self):
        """SC-002: every citation key/value/source_id traces to a real input entry."""
        entries = _make_both_layer_entries()
        entry_index = {(e.key, e.source_id): e for e in entries}
        citations, _, _ = retrieve_evidence(
            entries,
            entry_kinds={EntryKind.domain_correct_rate},
        )
        for c in citations:
            key = (c.key, c.source_id)
            assert key in entry_index, f"Citation key {key!r} not in input entries"
            e = entry_index[key]
            expected_value = e.value_num if e.value_num is not None else e.value_text
            assert c.value == expected_value

    def test_available_layers_both(self):
        """FR-015: available_layers reflects the whole student codex, not filter result."""
        entries = _make_both_layer_entries()
        _, available_layers, _ = retrieve_evidence(
            entries,
            entry_kinds={EntryKind.domain_correct_rate},
        )
        assert available_layers == ["minimal", "rich"]


# ---------------------------------------------------------------------------
# SC-005: no_evidence=True when rich-layer question but student is minimal-only
# ---------------------------------------------------------------------------


class TestRetrieveEvidenceMinimalOnly:
    """SC-005: rich-layer query on minimal-only student → no evidence, no fabrication."""

    def test_no_evidence_true(self):
        entries = _make_minimal_only_entries()
        _, _, no_evidence = retrieve_evidence(
            entries,
            entry_kinds={EntryKind.domain_correct_rate},
        )
        assert no_evidence is True

    def test_citations_empty(self):
        entries = _make_minimal_only_entries()
        citations, _, _ = retrieve_evidence(
            entries,
            entry_kinds={EntryKind.domain_correct_rate},
        )
        assert citations == []

    def test_available_layers_minimal_only(self):
        """FR-015: available_layers == ['minimal'] for a minimal-only student."""
        entries = _make_minimal_only_entries()
        _, available_layers, _ = retrieve_evidence(
            entries,
            entry_kinds={EntryKind.domain_correct_rate},
        )
        assert available_layers == ["minimal"]


# ---------------------------------------------------------------------------
# Freeform keyword query — substring match
# ---------------------------------------------------------------------------


class TestRetrieveEvidenceFreeform:
    def test_keyword_matches_key_substring(self):
        entries = _make_both_layer_entries()
        citations, _, no_evidence = retrieve_evidence(entries, keyword="chapter_correct_rate")
        assert no_evidence is False
        assert all("chapter_correct_rate" in c.key for c in citations)

    def test_keyword_matches_domain_substring(self):
        entries = _make_both_layer_entries()
        citations, _, no_evidence = retrieve_evidence(entries, keyword="순환")
        assert no_evidence is False
        # The 순환 domain entry should appear
        keys = {c.key for c in citations}
        assert "chapter_correct_rate:순환" in keys

    def test_keyword_matches_value_text_substring(self):
        entries = _make_both_layer_entries()
        citations, _, no_evidence = retrieve_evidence(entries, keyword="health")
        assert no_evidence is False
        assert any(c.key == "freetext_category:q9" for c in citations)

    def test_keyword_no_match_returns_no_evidence(self):
        entries = _make_both_layer_entries()
        citations, _, no_evidence = retrieve_evidence(entries, keyword="zzz_no_match")
        assert no_evidence is True
        assert citations == []

    def test_keyword_case_insensitive(self):
        entries = _make_both_layer_entries()
        citations_lower, _, _ = retrieve_evidence(entries, keyword="score_total")
        citations_upper, _, _ = retrieve_evidence(entries, keyword="SCORE_TOTAL")
        assert len(citations_lower) == len(citations_upper)


# ---------------------------------------------------------------------------
# Determinism: two identical calls produce the same citation order
# ---------------------------------------------------------------------------


class TestRetrieveEvidenceDeterminism:
    def test_two_calls_equal_order(self):
        entries = _make_both_layer_entries()
        c1, l1, n1 = retrieve_evidence(entries)
        c2, l2, n2 = retrieve_evidence(entries)
        assert c1 == c2
        assert l1 == l2
        assert n1 == n2

    def test_sort_order_is_layer_key_source_id(self):
        entries = _make_both_layer_entries()
        citations, _, _ = retrieve_evidence(entries)
        keys = [(c.layer, c.key, c.source_id) for c in citations]
        assert keys == sorted(keys)

    def test_tie_on_layer_key_source_id_is_total_order(self):
        """Two entries sharing (layer,key,source_id) but differing in value must
        sort identically regardless of pre-sort input order (FR determinism)."""
        # Two entries identical on (layer, key, source_id) but with different values.
        e_low = _entry(
            layer="rich",
            entry_kind=EntryKind.domain_correct_rate,
            domain="순환",
            key="chapter_correct_rate:순환",
            value_num=0.1,
            source_id="immersio:학생지표.parquet",
            observed_at="2026-05-20",
        )
        e_high = _entry(
            layer="rich",
            entry_kind=EntryKind.domain_correct_rate,
            domain="순환",
            key="chapter_correct_rate:순환",
            value_num=0.9,
            source_id="immersio:학생지표.parquet",
            observed_at="2026-05-20",
        )
        forward, _, _ = retrieve_evidence([e_low, e_high])
        reverse, _, _ = retrieve_evidence([e_high, e_low])
        assert forward == reverse
        assert [c.value for c in forward] == [c.value for c in reverse]

    # T058 RED — citation total-order must include observed_at tie-break (FR-024 / MC-U27)
    def test_tie_on_observed_at_is_total_order(self):
        """Two entries differing ONLY by observed_at must sort identically regardless
        of input order.  The current sort key omits observed_at → unstable (RED)."""
        # Share (layer, key, source_id, value_num); differ only in observed_at.
        e_early = _entry(
            layer="minimal",
            entry_kind=EntryKind.score_total,
            key="score_total",
            value_num=85.0,
            source_id="school_excel:성적출석.xlsx",
            observed_at="2026-05-01",
        )
        e_late = _entry(
            layer="minimal",
            entry_kind=EntryKind.score_total,
            key="score_total",
            value_num=85.0,
            source_id="school_excel:성적출석.xlsx",
            observed_at="2026-06-01",
        )
        forward, _, _ = retrieve_evidence([e_early, e_late])
        reverse, _, _ = retrieve_evidence([e_late, e_early])
        assert forward == reverse, (
            "citation order must be identical regardless of input permutation; "
            f"forward={[c.observed_at for c in forward]!r}, "
            f"reverse={[c.observed_at for c in reverse]!r}"
        )

    def test_tie_on_observed_at_none_is_stable(self):
        """observed_at=None must sort deterministically (consistently last or first)
        relative to a non-None observed_at."""
        e_dated = _entry(
            layer="minimal",
            entry_kind=EntryKind.score_total,
            key="score_total",
            value_num=85.0,
            source_id="school_excel:성적출석.xlsx",
            observed_at="2026-06-01",
        )
        e_none = _entry(
            layer="minimal",
            entry_kind=EntryKind.score_total,
            key="score_total",
            value_num=85.0,
            source_id="school_excel:성적출석.xlsx",
            observed_at=None,
        )
        forward, _, _ = retrieve_evidence([e_dated, e_none])
        reverse, _, _ = retrieve_evidence([e_none, e_dated])
        assert forward == reverse, (
            "None observed_at must sort deterministically; "
            f"forward={[c.observed_at for c in forward]!r}, "
            f"reverse={[c.observed_at for c in reverse]!r}"
        )


# ---------------------------------------------------------------------------
# Domain filter
# ---------------------------------------------------------------------------


class TestRetrieveEvidenceDomainFilter:
    def test_domain_filter_narrows_results(self):
        entries = _make_both_layer_entries()
        citations, _, _ = retrieve_evidence(entries, domain="순환")
        # Only the 순환 domain_correct_rate entry should match
        assert all(c.key == "chapter_correct_rate:순환" for c in citations)

    def test_domain_filter_none_is_noop(self):
        entries = _make_both_layer_entries()
        citations_no_filter, _, _ = retrieve_evidence(entries)
        citations_none_domain, _, _ = retrieve_evidence(entries, domain=None)
        assert citations_no_filter == citations_none_domain


# ---------------------------------------------------------------------------
# answer_question — via CanonicalQuestion
# ---------------------------------------------------------------------------


class TestAnswerQuestionViaCanonicalQuestion:
    def _rich_question(self) -> CanonicalQuestion:
        return CanonicalQuestion(
            id="q_domain",
            text="도메인별 정답률을 알려주세요.",
            entry_kinds=[EntryKind.domain_correct_rate],
            domain=None,
        )

    def test_returns_query_answer(self):
        entries = _make_both_layer_entries()
        q = self._rich_question()
        result = answer_question(entries, pseudonym="S001", question=q)
        assert isinstance(result, QueryAnswer)

    def test_question_id_set(self):
        entries = _make_both_layer_entries()
        q = self._rich_question()
        result = answer_question(entries, pseudonym="S001", question=q)
        assert result.question_id == "q_domain"

    def test_pseudonym_set(self):
        entries = _make_both_layer_entries()
        q = self._rich_question()
        result = answer_question(entries, pseudonym="S001", question=q)
        assert result.student_pseudonym == "S001"

    def test_narrative_and_rendered_by_none(self):
        """Pure retrieval: narrative and rendered_by are both None."""
        entries = _make_both_layer_entries()
        q = self._rich_question()
        result = answer_question(entries, pseudonym="S001", question=q)
        assert result.narrative is None
        assert result.rendered_by is None

    def test_question_with_domain_applies_domain_filter(self):
        """A question carrying a non-None domain narrows retrieval to that domain."""
        entries = _make_both_layer_entries()
        q = CanonicalQuestion(
            id="q_circ",
            text="순환 단원 정답률을 알려주세요.",
            entry_kinds=[EntryKind.domain_correct_rate],
            domain="순환",
        )
        result = answer_question(entries, pseudonym="S001", question=q)
        assert result.no_evidence is False
        # Only the 순환 domain entry — not 호흡 — should be cited.
        assert [c.key for c in result.citations] == ["chapter_correct_rate:순환"]


# ---------------------------------------------------------------------------
# answer_question — via freeform_text
# ---------------------------------------------------------------------------


class TestAnswerQuestionFreeform:
    def test_freeform_sets_question_id_freeform(self):
        entries = _make_both_layer_entries()
        result = answer_question(entries, pseudonym="S001", freeform_text="score_total")
        assert result.question_id == "freeform"

    def test_freeform_returns_matching_citations(self):
        entries = _make_both_layer_entries()
        result = answer_question(entries, pseudonym="S001", freeform_text="score_total")
        assert result.no_evidence is False

    def test_neither_question_nor_freeform_raises(self):
        entries = _make_both_layer_entries()
        with pytest.raises((ValueError, LocatedInputError)):
            answer_question(entries, pseudonym="S001")

    def test_both_question_and_freeform_raises(self):
        entries = _make_both_layer_entries()
        q = CanonicalQuestion(
            id="q1",
            text="?",
            entry_kinds=[EntryKind.score_total],
        )
        with pytest.raises((ValueError, LocatedInputError)):
            answer_question(entries, pseudonym="S001", question=q, freeform_text="score")


# ---------------------------------------------------------------------------
# load_question_set
# ---------------------------------------------------------------------------


class TestLoadQuestionSet:
    def _write_valid_yaml(self, tmp_path: Path) -> Path:
        p = tmp_path / "question_set.yaml"
        p.write_text(
            textwrap.dedent("""\
                questions:
                  - id: q_total
                    text: "총점을 알려주세요."
                    entry_kinds:
                      - score_total
                    domain: null
                  - id: q_domain
                    text: "도메인별 정답률을 알려주세요."
                    entry_kinds:
                      - domain_correct_rate
                    domain: null
            """),
            encoding="utf-8",
        )
        return p

    def test_loads_valid_yaml(self, tmp_path):
        p = self._write_valid_yaml(tmp_path)
        qs = load_question_set(p)
        assert isinstance(qs, QuestionSet)
        assert len(qs.questions) == 2
        assert qs.questions[0].id == "q_total"

    def test_missing_file_raises_located_error(self, tmp_path):
        p = tmp_path / "nonexistent.yaml"
        with pytest.raises(LocatedInputError):
            load_question_set(p)

    def test_invalid_yaml_raises_located_error(self, tmp_path):
        p = tmp_path / "bad.yaml"
        p.write_text("key: [unclosed", encoding="utf-8")
        with pytest.raises(LocatedInputError):
            load_question_set(p)

    def test_non_mapping_yaml_raises_located_error(self, tmp_path):
        p = tmp_path / "list.yaml"
        p.write_text("- item1\n- item2\n", encoding="utf-8")
        with pytest.raises(LocatedInputError):
            load_question_set(p)

    def test_validation_error_raises_located_error(self, tmp_path):
        p = tmp_path / "bad_schema.yaml"
        p.write_text(
            textwrap.dedent("""\
                questions:
                  - id: q1
                    text: "ok"
                    entry_kinds: [score_total]
                    unknown_field: "x"
            """),
            encoding="utf-8",
        )
        with pytest.raises(LocatedInputError):
            load_question_set(p)

    def test_duplicate_ids_raises_located_error(self, tmp_path):
        p = tmp_path / "dup.yaml"
        p.write_text(
            textwrap.dedent("""\
                questions:
                  - id: q1
                    text: "first"
                    entry_kinds: [score_total]
                  - id: q1
                    text: "duplicate"
                    entry_kinds: [score_total]
            """),
            encoding="utf-8",
        )
        with pytest.raises(LocatedInputError):
            load_question_set(p)

    def test_empty_questions_list_raises_located_error(self, tmp_path):
        p = tmp_path / "empty.yaml"
        p.write_text("questions: []\n", encoding="utf-8")
        with pytest.raises(LocatedInputError):
            load_question_set(p)


# ---------------------------------------------------------------------------
# QuestionSet — fail-fast on empty questions
# ---------------------------------------------------------------------------


class TestQuestionSetEmpty:
    def test_empty_questions_rejected(self):
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            QuestionSet(questions=[])
