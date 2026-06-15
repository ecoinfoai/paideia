"""T046 — Interest/aversion gap computation (US4, FR-022).

FR-022: Self-report bias must be flagged.  The gap between interest-topic
performance and aversion-topic performance is a self-report artefact and
must be presented conservatively with an explicit Korean note.

Public API: ``interest_aversion_findings(rows) -> dict``
"""

from __future__ import annotations

from paideia_shared.schemas import CombinedAnalysisRow

_BIAS_NOTE = (
    "자가응답 편향(self-report bias) 주의: 관심·기피 단원은 학생의 주관적 응답 기반으로 "
    "선별됩니다.  실제 학업 성취와 인과 관계가 없을 수 있으며, 결과 해석 시 보수적으로 "
    "접근하시기 바랍니다."
)


def interest_aversion_findings(
    rows: list[CombinedAnalysisRow],
) -> dict:
    """Compute cohort-level interest vs. aversion performance gap.

    FR-022: Returns a bias note in ALL cases, regardless of data availability.

    Args:
        rows: All CombinedAnalysisRow records for this run.

    Returns:
        Dict with keys:
        - ``interest_mean``: float | None — mean of interest_chapters_correct_rate
          for rows where it is not None; None if no such rows.
        - ``aversion_mean``: float | None — mean of aversion_chapters_correct_rate
          for rows where it is not None; None if no such rows.
        - ``gap``: float | None — interest_mean - aversion_mean; None when
          either mean is None.
        - ``n_interest``: int — count of rows with non-None interest rate.
        - ``n_aversion``: int — count of rows with non-None aversion rate.
        - ``bias_note``: str — FR-022 self-report bias note (always present).
    """
    interest_rates: list[float] = [
        row.interest_chapters_correct_rate
        for row in rows
        if row.interest_chapters_correct_rate is not None
    ]
    aversion_rates: list[float] = [
        row.aversion_chapters_correct_rate
        for row in rows
        if row.aversion_chapters_correct_rate is not None
    ]

    interest_mean: float | None = (
        sum(interest_rates) / len(interest_rates) if interest_rates else None
    )
    aversion_mean: float | None = (
        sum(aversion_rates) / len(aversion_rates) if aversion_rates else None
    )
    gap: float | None = (
        interest_mean - aversion_mean
        if interest_mean is not None and aversion_mean is not None
        else None
    )

    return {
        "interest_mean": interest_mean,
        "aversion_mean": aversion_mean,
        "gap": gap,
        "n_interest": len(interest_rates),
        "n_aversion": len(aversion_rates),
        "bias_note": _BIAS_NOTE,
    }


__all__ = ["interest_aversion_findings"]
