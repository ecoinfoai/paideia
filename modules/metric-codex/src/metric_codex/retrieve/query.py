"""T040 — Question-set loader and answer builder for metric-codex US2.

Provides CanonicalQuestion / QuestionSet config models, a YAML loader with
located errors, and a pure answer_question function that builds a QueryAnswer
from a pre-filtered list of CodexEntry rows.

The caller is responsible for:
- Filtering entries to a single student's rows before calling answer_question.
- Supplying the pseudonym for that student (this function never sees raw PII).
"""

from __future__ import annotations

from pathlib import Path
from typing import Self

from paideia_shared.schemas.metric_codex import CodexEntry, EntryKind, QueryAnswer
from pydantic import BaseModel, ConfigDict, ValidationError, model_validator

from metric_codex.errors import LocatedInputError
from metric_codex.retrieve.evidence import retrieve_evidence
from metric_codex.yaml_load import load_yaml_mapping

# ---------------------------------------------------------------------------
# Local config models
# ---------------------------------------------------------------------------


class CanonicalQuestion(BaseModel):
    """One structured question referencing a closed set of entry kinds.

    Attributes:
        id: Unique question identifier within a QuestionSet.
        text: Human-readable question text (Korean or English).
        entry_kinds: Entry kinds that supply evidence for this question.
        domain: Optional domain filter applied alongside entry_kinds.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str
    text: str
    entry_kinds: list[EntryKind]
    domain: str | None = None


class QuestionSet(BaseModel):
    """Ordered list of canonical questions for a module session.

    Invariants:
    - ``questions`` must be non-empty (an empty set is a config error).
    - all question ``id``s must be unique within the set.

    Attributes:
        questions: Ordered, non-empty list of CanonicalQuestion items.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    questions: list[CanonicalQuestion]

    @model_validator(mode="after")
    def _non_empty(self) -> Self:
        """Fail fast: a question_set with zero questions is a config error."""
        if not self.questions:
            raise ValueError("QuestionSet must contain at least one question.")
        return self

    @model_validator(mode="after")
    def _unique_ids(self) -> Self:
        """Enforce unique question IDs within the set."""
        seen: set[str] = set()
        dups: set[str] = set()
        for q in self.questions:
            if q.id in seen:
                dups.add(q.id)
            seen.add(q.id)
        if dups:
            raise ValueError(f"Duplicate question IDs in QuestionSet: {sorted(dups)}")
        return self


# ---------------------------------------------------------------------------
# YAML loader
# ---------------------------------------------------------------------------


def load_question_set(path: Path) -> QuestionSet:
    """Load and validate a question_set YAML file.

    Args:
        path: Absolute path to the question_set YAML file.

    Returns:
        Validated QuestionSet instance.

    Raises:
        LocatedInputError: If the file is missing, YAML parse fails, content
            is not a mapping, Pydantic validation fails, IDs are duplicate, or
            the questions list is empty.
    """
    raw = load_yaml_mapping(path, "question_set.yaml")
    try:
        return QuestionSet(**raw)
    except ValidationError as exc:
        raise LocatedInputError(f"question_set validation failed: {exc}", file=str(path)) from exc


# ---------------------------------------------------------------------------
# answer_question
# ---------------------------------------------------------------------------


def answer_question(
    entries: list[CodexEntry],
    *,
    pseudonym: str,
    question: CanonicalQuestion | None = None,
    freeform_text: str | None = None,
) -> QueryAnswer:
    """Build a deterministic QueryAnswer for one student.

    Exactly one of ``question`` or ``freeform_text`` must be provided.

    ``entries`` must already be filtered to a single student — this function
    never sees student IDs or names; the caller supplies the pseudonym.

    Args:
        entries: All CodexEntry rows for ONE student (pre-filtered by caller).
        pseudonym: De-identified student label matching ``^S\\d{3,}$``.
        question: Canonical question driving the evidence filters.  Mutually
            exclusive with ``freeform_text``.
        freeform_text: Ad-hoc keyword for substring search.  Mutually exclusive
            with ``question``.

    Returns:
        QueryAnswer with ``narrative=None`` and ``rendered_by=None`` (pure
        retrieval; the generate layer adds narrative in a later unit).

    Raises:
        ValueError: If neither or both of ``question``/``freeform_text`` are given.
    """
    if question is None and freeform_text is None:
        raise ValueError(
            "Exactly one of 'question' or 'freeform_text' must be provided; got neither."
        )
    if question is not None and freeform_text is not None:
        raise ValueError("Exactly one of 'question' or 'freeform_text' must be provided; got both.")

    if question is not None:
        citations, available_layers, no_evidence = retrieve_evidence(
            entries,
            entry_kinds=set(question.entry_kinds),
            domain=question.domain,
            keyword=None,
        )
        question_id = question.id
    else:
        # freeform_text branch
        citations, available_layers, no_evidence = retrieve_evidence(
            entries,
            entry_kinds=None,
            domain=None,
            keyword=freeform_text,
        )
        question_id = "freeform"

    return QueryAnswer(
        student_pseudonym=pseudonym,
        question_id=question_id,
        citations=citations,
        available_layers=available_layers,
        no_evidence=no_evidence,
        narrative=None,
        rendered_by=None,
    )


__all__ = [
    "CanonicalQuestion",
    "QuestionSet",
    "load_question_set",
    "answer_question",
]
