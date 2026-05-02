"""DispatchReportData — human report serialization input (data-model.md §1.7)."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict

from .email_dispatch_log_row import DispatchLogRow, DispatchStatus
from .email_dispatch_manifest import EmailManifest


class DispatchReportData(BaseModel):
    """Aggregated state used to render ``메일_발송보고서.md`` (FR-D04).

    Carries the manifest, per-status counts, and the failed/skipped
    log rows so the report renderer can compose the Korean summary
    without re-reading the CSV.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    manifest: EmailManifest
    summary_table: dict[DispatchStatus, int]
    failed_rows: list[DispatchLogRow]
    skipped_rows: list[DispatchLogRow]
    report_generated_at_kst: datetime


__all__ = ["DispatchReportData"]
