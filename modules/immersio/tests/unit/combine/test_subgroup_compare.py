"""TDD tests for ``combine.subgroup_compare`` (T051, US4).

Verifies 4-meta (section / prior_biology / occupation / education) ×
시험 점수 비교의 분기:
- 2-카테고리 → Welch's t-test + Cohen's d (M6 V1)
- 3+카테고리 등분산 → ANOVA + η² (M6 V2)
- 3+카테고리 이분산 → Welch ANOVA + η²
- n<10 카테고리 자동 제외 (FR-019, excluded_reason 채움)
- 메타 미정의 (mapping 키 부재) → "(메타 미정의)" 폴백 (M6 V3, R-10)

Anti-payload (qa Rule 5 페어):
- meta_kinds=[] → ValueError (silent skip 차단)
- 카테고리 추출 컬럼 후보 0건 → "(메타 미정의)" 폴백 (silent skip 아님)
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest
from immersio.combine.subgroup_compare import compute_subgroup_score_comparison


def _df_with_subgroups(
    *,
    section_distribution: dict[str, int] | None = None,
    occupation_values: list[str] | None = None,
    seed: int = 0,
    score_mean: float = 70.0,
    score_sd: float = 5.0,
) -> pd.DataFrame:
    """Build a synthetic joined dataframe with subgroup columns."""
    rng = np.random.default_rng(seed)
    rows: list[dict] = []
    section_dist = section_distribution or {"A": 30, "B": 30, "C": 30}
    sids = []
    sections = []
    for sec, n in section_dist.items():
        for _ in range(n):
            sids.append(f"2026{len(sids):06d}")
            sections.append(sec)
    n_total = len(sids)
    occ_list = occupation_values if occupation_values is not None else [None] * n_total
    if len(occ_list) < n_total:
        occ_list = list(occ_list) + [None] * (n_total - len(occ_list))

    for i in range(n_total):
        rows.append(
            {
                "student_id": sids[i],
                "exam_taken": True,
                "total_score": float(rng.normal(score_mean, score_sd)),
                "section": sections[i],
                "occupation": occ_list[i],
                "prior_readiness_q5": None,
                "prior_readiness_q6": None,
            }
        )
    return pd.DataFrame(rows)


# ----------------------------------------------------------------------
# Smoke
# ----------------------------------------------------------------------


def test_returns_three_components() -> None:
    df = _df_with_subgroups()
    rows, headers = compute_subgroup_score_comparison(df)
    assert isinstance(rows, list)
    assert isinstance(headers, list)


def test_emits_one_header_per_meta() -> None:
    df = _df_with_subgroups()
    _, headers = compute_subgroup_score_comparison(df)
    meta_kinds = {h.meta_kind for h in headers}
    # 4 meta kinds always emitted (with N/A fallback if undefined).
    assert meta_kinds == {"section", "prior_biology", "occupation", "education"}


# ----------------------------------------------------------------------
# 3-카테고리 → ANOVA + η²
# ----------------------------------------------------------------------


def test_section_three_categories_uses_anova() -> None:
    df = _df_with_subgroups(
        section_distribution={"A": 40, "B": 40, "C": 40},
    )
    _, headers = compute_subgroup_score_comparison(df)
    section_header = next(h for h in headers if h.meta_kind == "section")
    assert section_header.test_used in {"ANOVA", "Welch_ANOVA"}
    assert section_header.effect_size_kind == "eta_squared"


# ----------------------------------------------------------------------
# 2-카테고리 → Welch t-test + Cohen's d
# ----------------------------------------------------------------------


def test_section_two_categories_uses_welch_t() -> None:
    df = _df_with_subgroups(section_distribution={"A": 40, "B": 40})
    _, headers = compute_subgroup_score_comparison(df)
    section_header = next(h for h in headers if h.meta_kind == "section")
    assert section_header.test_used == "t_test_welch"
    assert section_header.effect_size_kind == "cohen_d"


# ----------------------------------------------------------------------
# n<10 자동 제외
# ----------------------------------------------------------------------


def test_n_lt_10_category_excluded() -> None:
    df = _df_with_subgroups(
        section_distribution={"A": 40, "B": 40, "C": 5},  # C < 10
    )
    rows, _ = compute_subgroup_score_comparison(df)
    excluded = [
        r for r in rows if r.meta_kind == "section" and r.meta_value == "C" and r.excluded_reason
    ]
    assert excluded, "n<10 category C must be excluded with reason"
    assert "10" in excluded[0].excluded_reason


def test_excluded_category_drops_to_two_remaining() -> None:
    df = _df_with_subgroups(
        section_distribution={"A": 40, "B": 40, "C": 5},
    )
    _, headers = compute_subgroup_score_comparison(df)
    section_header = next(h for h in headers if h.meta_kind == "section")
    # n<10 dropped → 2 remaining → t_test_welch
    assert section_header.test_used == "t_test_welch"


# ----------------------------------------------------------------------
# 메타 미정의 폴백 (R-10)
# ----------------------------------------------------------------------


def test_undefined_meta_yields_na_header() -> None:
    """occupation 컬럼이 모두 None ⇒ 'meta_value=(메타 미정의)' 행 + N/A header."""
    df = _df_with_subgroups()  # occupation 없음
    rows, headers = compute_subgroup_score_comparison(df)
    occ_header = next(h for h in headers if h.meta_kind == "occupation")
    assert occ_header.test_used == "N/A"
    assert occ_header.effect_size_kind == "cohen_d"  # default; n_categories_compared=0 V3 enforced
    assert occ_header.n_categories_compared == 0

    occ_rows = [r for r in rows if r.meta_kind == "occupation"]
    assert any(r.meta_value == "(메타 미정의)" for r in occ_rows)


def test_education_meta_undefined_in_minimal_fixture() -> None:
    """학력 (education) 컬럼이 fixture 에 없음 → '(메타 미정의)' 폴백."""
    df = _df_with_subgroups()
    _, headers = compute_subgroup_score_comparison(df)
    edu_header = next(h for h in headers if h.meta_kind == "education")
    assert edu_header.test_used == "N/A"


# ----------------------------------------------------------------------
# Occupation small subgroup (n=2 자동 제외 시나리오)
# ----------------------------------------------------------------------


def test_occupation_small_subgroup_auto_exclude() -> None:
    """fixture 의 occupation 'industry-edge' n=2 → 자동 제외."""
    occupation_vals = ["industry-edge"] * 2 + ["student"] * 28
    df = _df_with_subgroups(
        section_distribution={"A": 30},
        occupation_values=occupation_vals,
    )
    rows, headers = compute_subgroup_score_comparison(df)
    occ_excluded = [
        r for r in rows if r.meta_kind == "occupation" and r.meta_value == "industry-edge"
    ]
    assert occ_excluded
    assert occ_excluded[0].excluded_reason is not None


# ----------------------------------------------------------------------
# BH-FDR adjusted q across 4 metas
# ----------------------------------------------------------------------


def test_fdr_q_populated_when_test_used_not_na() -> None:
    df = _df_with_subgroups(section_distribution={"A": 40, "B": 40, "C": 40})
    _, headers = compute_subgroup_score_comparison(df)
    section_header = next(h for h in headers if h.meta_kind == "section")
    assert section_header.fdr_q is not None
    assert 0.0 <= section_header.fdr_q <= 1.0


def test_fdr_q_none_when_test_used_na() -> None:
    df = _df_with_subgroups()  # occupation 모두 None
    _, headers = compute_subgroup_score_comparison(df)
    occ_header = next(h for h in headers if h.meta_kind == "occupation")
    assert occ_header.fdr_q is None


# ----------------------------------------------------------------------
# Determinism — repeat call identity
# ----------------------------------------------------------------------


def test_repeat_call_byte_identical_headers() -> None:
    df = _df_with_subgroups(section_distribution={"A": 40, "B": 40, "C": 40})
    rows1, h1 = compute_subgroup_score_comparison(df)
    rows2, h2 = compute_subgroup_score_comparison(df)
    assert [(r.meta_kind, r.meta_value) for r in rows1] == [
        (r.meta_kind, r.meta_value) for r in rows2
    ]
    assert [(h.meta_kind, h.test_used) for h in h1] == [(h.meta_kind, h.test_used) for h in h2]


# ----------------------------------------------------------------------
# Empty input
# ----------------------------------------------------------------------


def test_empty_dataframe_rejected() -> None:
    df = pd.DataFrame()
    with pytest.raises(ValueError, match="empty"):
        compute_subgroup_score_comparison(df)


def test_no_exam_taker_rejected() -> None:
    df = _df_with_subgroups()
    df["exam_taken"] = False
    df["total_score"] = None
    with pytest.raises(ValueError, match="exam"):
        compute_subgroup_score_comparison(df)
