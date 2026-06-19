"""SourceRecord: one row per ingested source file in the metric-codex pipeline.

Tracks provenance of every input artefact so CodexEntry rows can be traced back
to their origin. The ``source_id`` is the primary key referenced by
``CodexEntry.source_id``.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

_SHA256_PATTERN = r"^[0-9a-f]{64}$"


class SourceRecord(BaseModel):
    """Provenance record for one ingested source file.

    Attributes:
        source_id: Logical identifier (e.g. ``"immersio:진단×시험결합"``,
            ``"school_excel:성적출석.xlsx"``).
        origin_module: Which paideia module produced / owns this file.
        origin_layer: Bronze/Silver/Gold tier of the source.
        source_path: Repo-relative path to the source file.
        sha256: SHA-256 hex digest of the file (64 lowercase hex chars).
        ingested_at: ISO-8601 UTC timestamp of when this record was created.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    source_id: str = Field(
        ...,
        description=(
            "Logical source identifier used as FK by CodexEntry. "
            "E.g. 'immersio:진단×시험결합', 'school_excel:성적출석.xlsx'."
        ),
    )
    origin_module: Literal["metric-codex", "immersio", "needs-map", "examen", "school"]
    origin_layer: Literal["bronze", "silver", "gold"]
    source_path: str = Field(..., description="Repo-relative path to the source file.")
    sha256: str = Field(
        ...,
        pattern=_SHA256_PATTERN,
        description="SHA-256 hex digest (64 lowercase hex chars).",
    )
    ingested_at: str = Field(..., description="ISO-8601 UTC timestamp of ingestion.")


__all__ = ["SourceRecord"]
