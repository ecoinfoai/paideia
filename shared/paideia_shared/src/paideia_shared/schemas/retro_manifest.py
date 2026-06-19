"""RetroManifest (M7): run-level audit record for a retro-mester execution.

Silver-layer schema. Written as ``manifest_retro.json`` at the end of every
pipeline run. Flexible dict shapes allow threshold values and degrade flags
to evolve without a schema bump.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from ._common import CourseSlug, SemesterCode

_SHA256_PATTERN = r"^[0-9a-f]{64}$"


class InputProvenance(BaseModel):
    """File-level provenance record for a single pipeline input artefact.

    Attributes:
        path: Resolved filesystem path to the artefact.
        sha256: SHA-256 hex digest of the artefact (64 lowercase hex chars).
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    path: str = Field(..., description="Resolved filesystem path to the input artefact.")
    sha256: str = Field(
        ...,
        pattern=_SHA256_PATTERN,
        description="SHA-256 hex digest of the artefact (64 lowercase hex chars).",
    )


class RetroManifest(BaseModel):
    """Audit manifest for one retro-mester pipeline run.

    Note:
        ``degrade`` values are ``bool | str`` to accommodate both binary
        degradation flags and structured error messages from partial-run
        recovery logic.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    module_version: str = Field(
        ...,
        description="retro-mester package version (SemVer, e.g. '0.1.0').",
    )
    schema_version: str = Field(
        ...,
        description="paideia_shared schema version in use (e.g. '0.1.0').",
    )
    semester: SemesterCode
    course_slug: CourseSlug
    inputs: dict[str, InputProvenance] = Field(
        ...,
        description=(
            "Map of input artefact role → InputProvenance (path + sha256). "
            "Roles include: combined, items, config, blueprint, curriculum_map, prior_year."
        ),
    )
    thresholds: dict[str, float] = Field(
        ...,
        description="Active threshold values used in this run (from RetroMesterConfig).",
    )
    counts: dict[str, float] = Field(
        ...,
        description=(
            "Row / item counts for key pipeline outputs "
            "(float allows fractional metrics like mean scores alongside int counts)."
        ),
    )
    degrade: dict[str, bool | str] = Field(
        ...,
        description=(
            "Degradation flags keyed by pipeline stage. "
            "True / non-empty string = stage degraded; False / '' = nominal."
        ),
    )
    warnings: list[str] = Field(
        default_factory=list,
        description=(
            "Non-fatal diagnostic messages emitted during the run (e.g. chapter name mismatches)."
        ),
    )
    generated_at_utc: str = Field(
        ...,
        description="ISO-8601 UTC timestamp when this manifest was written.",
    )


__all__ = ["InputProvenance", "RetroManifest"]
