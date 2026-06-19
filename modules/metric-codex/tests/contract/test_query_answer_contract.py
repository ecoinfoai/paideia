"""T034 RED — Contract tests for EvidenceCitation and QueryAnswer (spec 013)."""

from __future__ import annotations

import pytest

# These imports will fail (RED) until the schema is implemented.
from paideia_shared.schemas.metric_codex import EvidenceCitation, QueryAnswer
from pydantic import ValidationError

# ---------------------------------------------------------------------------
# EvidenceCitation
# ---------------------------------------------------------------------------


def _citation(**overrides) -> dict:
    base = dict(
        key="score_total",
        value=85.0,
        source_id="school_excel:성적출석.xlsx",
        observed_at="2026-06-01",
        layer="minimal",
    )
    base.update(overrides)
    return base


class TestEvidenceCitation:
    def test_valid_float_value(self):
        c = EvidenceCitation(**_citation(value=92.5))
        assert c.value == 92.5
        assert isinstance(c.value, float)

    def test_valid_str_value(self):
        c = EvidenceCitation(**_citation(value="category_A", layer="rich"))
        assert c.value == "category_A"
        assert isinstance(c.value, str)

    def test_observed_at_optional(self):
        c = EvidenceCitation(**_citation(observed_at=None))
        assert c.observed_at is None

    def test_layer_minimal(self):
        c = EvidenceCitation(**_citation(layer="minimal"))
        assert c.layer == "minimal"

    def test_layer_rich(self):
        c = EvidenceCitation(**_citation(layer="rich"))
        assert c.layer == "rich"

    def test_layer_invalid_rejected(self):
        with pytest.raises(ValidationError):
            EvidenceCitation(**_citation(layer="bronze"))

    def test_extra_field_rejected(self):
        with pytest.raises(ValidationError):
            EvidenceCitation(**_citation(unexpected="x"))

    def test_immutable(self):
        c = EvidenceCitation(**_citation())
        with pytest.raises((ValidationError, TypeError)):
            c.key = "changed"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# QueryAnswer
# ---------------------------------------------------------------------------


def _answer(**overrides) -> dict:
    base = dict(
        student_pseudonym="S001",
        question_id="q_total",
        citations=[],
        available_layers=["minimal"],
        no_evidence=True,
        narrative=None,
        rendered_by=None,
    )
    base.update(overrides)
    return base


def _make_citation() -> EvidenceCitation:
    return EvidenceCitation(**_citation())


class TestQueryAnswerNoEvidenceInvariant:
    def test_no_evidence_true_with_empty_citations_ok(self):
        qa = QueryAnswer(**_answer(no_evidence=True, citations=[]))
        assert qa.no_evidence is True
        assert qa.citations == []

    def test_no_evidence_true_with_non_empty_citations_raises(self):
        """Fabrication guard: no_evidence=True but citations present → ValueError."""
        with pytest.raises(ValidationError):
            QueryAnswer(
                **_answer(
                    no_evidence=True,
                    citations=[_make_citation()],
                )
            )

    def test_no_evidence_false_with_citations_ok(self):
        c = _make_citation()
        qa = QueryAnswer(
            **_answer(
                no_evidence=False,
                citations=[c],
                available_layers=["minimal"],
            )
        )
        assert qa.no_evidence is False
        assert len(qa.citations) == 1


class TestQueryAnswerNarrativeRenderedByInvariant:
    def test_both_none_ok(self):
        qa = QueryAnswer(**_answer(narrative=None, rendered_by=None))
        assert qa.narrative is None
        assert qa.rendered_by is None

    def test_narrative_set_rendered_by_set_ok(self):
        qa = QueryAnswer(
            **_answer(
                no_evidence=False,
                citations=[_make_citation()],
                available_layers=["minimal"],
                narrative="학생의 총점은 85점입니다.",
                rendered_by="template",
            )
        )
        assert qa.rendered_by == "template"

    def test_narrative_set_rendered_by_none_raises(self):
        with pytest.raises(ValidationError):
            QueryAnswer(
                **_answer(
                    no_evidence=False,
                    citations=[_make_citation()],
                    available_layers=["minimal"],
                    narrative="Some narrative",
                    rendered_by=None,
                )
            )

    def test_narrative_none_rendered_by_set_raises(self):
        with pytest.raises(ValidationError):
            QueryAnswer(**_answer(narrative=None, rendered_by="template"))

    def test_rendered_by_llm_accepted(self):
        qa = QueryAnswer(
            **_answer(
                no_evidence=False,
                citations=[_make_citation()],
                available_layers=["minimal"],
                narrative="LLM narrative",
                rendered_by="llm",
            )
        )
        assert qa.rendered_by == "llm"

    def test_rendered_by_invalid_rejected(self):
        with pytest.raises(ValidationError):
            QueryAnswer(
                **_answer(
                    no_evidence=False,
                    citations=[_make_citation()],
                    narrative="text",
                    rendered_by="unknown_renderer",
                )
            )


class TestQueryAnswerPseudonymPattern:
    def test_valid_pseudonym_s001(self):
        qa = QueryAnswer(**_answer(student_pseudonym="S001"))
        assert qa.student_pseudonym == "S001"

    def test_valid_pseudonym_s999(self):
        qa = QueryAnswer(**_answer(student_pseudonym="S999"))
        assert qa.student_pseudonym == "S999"

    def test_valid_pseudonym_long(self):
        qa = QueryAnswer(**_answer(student_pseudonym="S1234"))
        assert qa.student_pseudonym == "S1234"

    def test_invalid_no_prefix(self):
        with pytest.raises(ValidationError):
            QueryAnswer(**_answer(student_pseudonym="001"))

    def test_invalid_lowercase_prefix(self):
        with pytest.raises(ValidationError):
            QueryAnswer(**_answer(student_pseudonym="s001"))

    def test_invalid_too_short_digits(self):
        with pytest.raises(ValidationError):
            QueryAnswer(**_answer(student_pseudonym="S01"))

    def test_invalid_non_digit(self):
        with pytest.raises(ValidationError):
            QueryAnswer(**_answer(student_pseudonym="S00A"))


class TestQueryAnswerExtraForbid:
    def test_extra_field_rejected(self):
        with pytest.raises(ValidationError):
            QueryAnswer(**_answer(unknown_field="x"))
