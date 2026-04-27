"""Shared annotated types used across paideia data contracts.

These types form the canonical building blocks for cross-module schema
validation. Each constrained string carries an explicit pattern so
Pydantic enforces the boundary at every model that consumes it.
"""

from typing import Annotated, Literal, TypeAlias

from pydantic import Field

CanonicalStudentId: TypeAlias = Annotated[
    str,
    Field(
        pattern=r"^\d{10}$",
        description="10-digit zero-padded student ID (post-normalization).",
    ),
]
"""10-digit student ID after normalization (e.g. '2026194999')."""

SemesterCode: TypeAlias = Annotated[
    str,
    Field(
        pattern=r"^\d{4}-[12SW]$",
        description="Academic semester: '2026-1', '2026-2', '2025-S', '2025-W'.",
    ),
]
"""Year-semester code: 1=spring, 2=fall, S=summer, W=winter."""

CourseSlug: TypeAlias = Annotated[
    str,
    Field(
        pattern=r"^[a-z][a-z0-9-]{1,39}$",
        description="ASCII kebab-case course identifier (e.g. 'anatomy').",
    ),
]
"""ASCII kebab-case slug used for cross-tool directory naming."""

OutputKey: TypeAlias = Annotated[
    str,
    Field(
        pattern=r"^\d{4}-[12SW]-[a-z][a-z0-9-]{1,39}$",
        description="Concatenation of SemesterCode and CourseSlug ('2026-1-anatomy').",
    ),
]
"""Silver output directory key: '{semester}-{course_slug}'."""

SectionLabel: TypeAlias = Literal["A", "B", "C", "D"]
"""Class section label assigned by the department's OMR template."""

StandardAxisKey: TypeAlias = Literal[
    "digital_efficacy",
    "motivation",
    "time_availability",
    "material_preference",
    "study_strategy",
    "study_environment",
    "social_learning",
    "feedback_seeking",
]
"""paideia v0.1.1 standard quantitative-axis vocabulary (8 keys, constitution v1.1.0).

The 8 keys are fixed cross-module. Adding a new quantitative axis is a paideia
minor-version bump per spec FR-AXIS-001 + FR-013. The same literal set backs
the V6 validator on ``DiagnosticMappingConfig`` and the per-axis fields of
``FactorScoreRow`` / ``ScaleReliabilityRow``.

v0.1.0 → v0.1.1 axis migration: motivation (kept), anxiety (dropped — moved to
freetext + sentiment area), self_efficacy / interest / prior_knowledge /
life_context (dropped — replaced by the 7 new keys covering digital efficacy,
study time availability, material/strategy/environment preferences, social
learning, feedback seeking).
"""

STANDARD_AXIS_KEYS: tuple[str, ...] = (
    "digital_efficacy",
    "motivation",
    "time_availability",
    "material_preference",
    "study_strategy",
    "study_environment",
    "social_learning",
    "feedback_seeking",
)
"""Tuple form of ``StandardAxisKey`` for deterministic iteration.

Used by per-axis ``model_validator`` loops in ``FactorScoreRow`` /
``FactorScoresLongRow`` and by services that need to iterate over the
canonical axis set in declaration order. Always mirrors ``StandardAxisKey``;
contract tests enforce parity (T008 in spec 003).
"""

AuxiliaryGroupKey: TypeAlias = Literal[
    "prior_readiness",
    "interest_topics",
    "categorical_intent",
]
"""Optional non-quantitative axis groups used in needs-map v0.1.1.

These keys are *not* scored — they emit category distribution rows on the
v0.1.1 axis_summary export and live alongside the 8 quantitative axes.
Constitution v1.1.0 explicitly allows modules to extend this set; the literal
here pins the keys actually used by the 2026-1 anatomy mapping.
"""

FreetextAreaKey: TypeAlias = Literal[
    "anxiety_freetext",
    "experience_freetext",
]
"""Free-text response areas processed by the v0.1.1 sentiment pipeline.

Each area carries its own dictionary categories + RoBERTa sentiment + token
audit. The two values mirror Q61 (anxiety) and Q62 (experience) on the
2026-1 anatomy diagnostic.
"""
