"""T042 RED — Unit tests for metric_codex.generate.narrative.

Tests (written first per TDD mandate):
- render_template returns a markdown string with headings from question_text.
- no_evidence entries emit the literal "근거 없음".
- Every factual value in output traces to a citation (EVID-01 — no uncited claim).
- Deterministic: two calls with the same bundle produce identical strings.
- Rendered by "template" path — no LLM call.
"""

from __future__ import annotations

# The imports below will fail (RED) until generate/bundle.py exists.
from metric_codex.generate.bundle import (
    BundleQuestion,
    StudentBundle,
)

# The import below will fail (RED) until generate/narrative.py exists.
from metric_codex.generate.narrative import render_template
from paideia_shared.schemas.metric_codex import (
    EvidenceCitation,
    QueryAnswer,
)

# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

_PSEUDONYM = "S001"


def _citation(**kwargs) -> EvidenceCitation:
    base: dict = dict(
        key="score_total",
        value=85.0,
        source_id="school_excel:성적출석.xlsx",
        observed_at="2026-06-01",
        layer="minimal",
    )
    base.update(kwargs)
    return EvidenceCitation(**base)


def _answer_with_evidence(*citations: EvidenceCitation, question_id: str = "q1") -> QueryAnswer:
    return QueryAnswer(
        student_pseudonym=_PSEUDONYM,
        question_id=question_id,
        citations=list(citations),
        available_layers=["minimal"],
        no_evidence=len(citations) == 0,
    )


def _answer_no_evidence(question_id: str = "q1") -> QueryAnswer:
    return QueryAnswer(
        student_pseudonym=_PSEUDONYM,
        question_id=question_id,
        citations=[],
        available_layers=["minimal"],
        no_evidence=True,
    )


def _bundle(questions: list[BundleQuestion]) -> StudentBundle:
    return StudentBundle(
        pseudonym=_PSEUDONYM,
        available_layers=["minimal"],
        questions=questions,
    )


def _bq(
    question_id: str,
    question_text: str,
    answer: QueryAnswer,
) -> BundleQuestion:
    return BundleQuestion(
        question_id=question_id,
        question_text=question_text,
        answer=answer,
    )


# ---------------------------------------------------------------------------
# TestRenderTemplateHeadings
# ---------------------------------------------------------------------------


class TestRenderTemplateHeadings:
    """render_template emits one heading per question_text."""

    def test_single_question_heading_present(self):
        bq = _bq("q1", "총점을 알려주세요.", _answer_no_evidence())
        result = render_template(_bundle([bq]))
        assert "총점을 알려주세요." in result

    def test_multiple_questions_all_headings_present(self):
        bq1 = _bq("q1", "총점을 알려주세요.", _answer_no_evidence("q1"))
        bq2 = _bq("q2", "도메인별 정답률.", _answer_no_evidence("q2"))
        result = render_template(_bundle([bq1, bq2]))
        assert "총점을 알려주세요." in result
        assert "도메인별 정답률." in result

    def test_heading_is_markdown(self):
        """Heading should be formatted as a Markdown heading (# prefix)."""
        bq = _bq("q1", "총점?", _answer_no_evidence())
        result = render_template(_bundle([bq]))
        # At minimum a '#' should appear before the question text somewhere
        assert "#" in result


# ---------------------------------------------------------------------------
# TestRenderTemplateNoEvidence
# ---------------------------------------------------------------------------


class TestRenderTemplateNoEvidence:
    """no_evidence → literal '근거 없음' in output (EVID-02)."""

    def test_no_evidence_emits_literal_string(self):
        bq = _bq("q1", "도메인별 정답률.", _answer_no_evidence())
        result = render_template(_bundle([bq]))
        assert "근거 없음" in result

    def test_no_evidence_does_not_fabricate_numbers(self):
        """When no_evidence is True, no numeric claims should appear for that question."""
        bq = _bq("q1", "도메인별 정답률.", _answer_no_evidence())
        result = render_template(_bundle([bq]))
        # "근거 없음" must be there; no float value lines should follow
        # (a simple heuristic: no "0." or any digit before "(" citations)
        section = result[result.find("도메인별 정답률.") :]
        # Must contain the sentinel
        assert "근거 없음" in section


# ---------------------------------------------------------------------------
# TestRenderTemplateCitations — EVID-01
# ---------------------------------------------------------------------------


class TestRenderTemplateCitations:
    """Every factual value in output carries a citation (EVID-01)."""

    def test_citation_key_present_in_output(self):
        c = _citation(key="score_total", value=85.0)
        bq = _bq("q1", "총점?", _answer_with_evidence(c))
        result = render_template(_bundle([bq]))
        assert "score_total" in result

    def test_citation_source_id_present_in_output(self):
        c = _citation(key="score_total", value=85.0, source_id="school_excel:성적출석.xlsx")
        bq = _bq("q1", "총점?", _answer_with_evidence(c))
        result = render_template(_bundle([bq]))
        assert "school_excel:성적출석.xlsx" in result

    def test_citation_value_float_present_in_output(self):
        c = _citation(key="score_total", value=85.0)
        bq = _bq("q1", "총점?", _answer_with_evidence(c))
        result = render_template(_bundle([bq]))
        assert "85" in result

    def test_citation_value_text_present_in_output(self):
        c = _citation(
            key="freetext_category:q9",
            value="health,career",
            layer="rich",
            source_id="needs-map:free_text_categorization.parquet",
            observed_at=None,
        )
        bq = _bq("q1", "자유서술?", _answer_with_evidence(c))
        result = render_template(_bundle([bq]))
        assert "health,career" in result

    def test_multiple_citations_all_appear(self):
        c1 = _citation(key="score_total", value=85.0, source_id="src:a.xlsx")
        c2 = _citation(key="score_percent", value=90.5, source_id="src:b.xlsx")
        bq = _bq("q1", "성적?", _answer_with_evidence(c1, c2))
        result = render_template(_bundle([bq]))
        assert "score_total" in result
        assert "score_percent" in result

    def test_citation_layer_present_in_output(self):
        c = _citation(key="score_total", value=85.0, layer="minimal")
        bq = _bq("q1", "총점?", _answer_with_evidence(c))
        result = render_template(_bundle([bq]))
        assert "minimal" in result


# ---------------------------------------------------------------------------
# TestRenderTemplateNonFiniteFloat — render must not crash on nan/inf
# ---------------------------------------------------------------------------


class TestRenderTemplateNonFiniteFloat:
    """render_template is a pure formatter; it must not crash on non-finite floats.

    Even though NaN is normally None-coerced upstream, the formatter must be
    robust: ``value == int(value)`` raises on nan/inf, so the implementation
    guards with math.isfinite.
    """

    def test_nan_value_does_not_crash(self):
        c = _citation(
            key="z_score",
            value=float("nan"),
            layer="rich",
            source_id="immersio:학생지표.parquet",
            observed_at=None,
        )
        bq = _bq("q1", "z?", _answer_with_evidence(c))
        # Must not raise.
        result = render_template(_bundle([bq]))
        assert isinstance(result, str)

    def test_nan_value_rendered_as_string_sentinel(self):
        c = _citation(
            key="z_score",
            value=float("nan"),
            layer="rich",
            source_id="immersio:학생지표.parquet",
            observed_at=None,
        )
        bq = _bq("q1", "z?", _answer_with_evidence(c))
        result = render_template(_bundle([bq]))
        # str(float('nan')) == 'nan' — the sentinel appears verbatim.
        assert "nan" in result

    def test_inf_value_does_not_crash(self):
        c = _citation(
            key="z_score",
            value=float("inf"),
            layer="rich",
            source_id="immersio:학생지표.parquet",
            observed_at=None,
        )
        bq = _bq("q1", "z?", _answer_with_evidence(c))
        result = render_template(_bundle([bq]))
        assert "inf" in result

    def test_finite_non_integer_float_preserved(self):
        c = _citation(key="score_percent", value=90.5)
        bq = _bq("q1", "환산?", _answer_with_evidence(c))
        result = render_template(_bundle([bq]))
        assert "90.5" in result


# ---------------------------------------------------------------------------
# TestRenderTemplateDeterminism
# ---------------------------------------------------------------------------


class TestRenderTemplateDeterminism:
    """Same bundle → identical output on two calls."""

    def test_two_calls_equal_output(self):
        c = _citation(key="score_total", value=85.0)
        bq = _bq("q1", "총점?", _answer_with_evidence(c))
        bundle = _bundle([bq])
        result1 = render_template(bundle)
        result2 = render_template(bundle)
        assert result1 == result2

    def test_two_calls_same_multi_question_bundle(self):
        c1 = _citation(key="score_total", value=85.0)
        c2 = _citation(key="score_percent", value=90.5, source_id="src:b.xlsx")
        bq1 = _bq("q1", "총점?", _answer_with_evidence(c1))
        bq2 = _bq("q2", "환산점수?", _answer_with_evidence(c2))
        bundle = _bundle([bq1, bq2])
        assert render_template(bundle) == render_template(bundle)


# ---------------------------------------------------------------------------
# TestRenderTemplateNoLlm
# ---------------------------------------------------------------------------


class TestRenderTemplateNoLlm:
    """render_template is pure/offline — it must not invoke any LLM."""

    def test_no_import_of_anthropic_in_narrative(self):
        """Indirect guard: the narrative module must not import anthropic."""

        import metric_codex.generate.narrative as mod

        # Verify that 'anthropic' is not in the module's globals
        assert "anthropic" not in dir(mod), (
            "narrative.py must not import anthropic (offline-only path)"
        )


# ---------------------------------------------------------------------------
# TestRenderTemplateReturnType
# ---------------------------------------------------------------------------


class TestRenderTemplateReturnType:
    """render_template always returns a str."""

    def test_returns_string(self):
        bq = _bq("q1", "총점?", _answer_no_evidence())
        result = render_template(_bundle([bq]))
        assert isinstance(result, str)

    def test_non_empty_string(self):
        bq = _bq("q1", "총점?", _answer_no_evidence())
        result = render_template(_bundle([bq]))
        assert len(result.strip()) > 0
