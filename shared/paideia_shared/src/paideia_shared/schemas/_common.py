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
