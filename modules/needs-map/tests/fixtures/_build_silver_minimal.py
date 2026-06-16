"""Synthetic Silver fixture builder for needs-map US1 tests (T037).

Run from repo root:
    uv run python modules/needs-map/tests/fixtures/_build_silver_minimal.py

Generates:
    silver_minimal/2026-1-anatomy/student_master.parquet  (10 rows)
    silver_minimal/2026-1-anatomy/diagnostic_response.parquet (long form)

Composition:
    8 roster + responded students (sections A/B distributed)
    1 off-roster + responded student (section=None)
    1 roster + non-responded student
Diagnostic items per responder:
    motivation:      3 likert items  (one student has 1 item missing)
    anxiety:         4 likert items  (one student has all items missing)
    self_efficacy:   2 likert items
    interest:        1 freetext item
    prior_knowledge: 1 multiselect partition item (one-hot expanded)
    life_context:    1 multiselect partition item (one-hot expanded)
    + 2 free-text items (anxiety + life_context)
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

_HERE = Path(__file__).parent
# Mirror the runtime layout silver/immersio/{output_key}/ so silver loaders
# can be pointed at silver_minimal/ as their input_root directly.
_SILVER_DIR = _HERE / "silver_minimal" / "silver" / "immersio" / "2026-1-anatomy"

_SECTIONS = ["A", "B", "A", "B", "A", "B", "A", "B"]  # 8 roster respondents
_LIKERT_VALUES = [3, 4, 5, 4, 6, 3, 5, 4, 5]  # used cyclically; deterministic


def _student_master_rows() -> list[dict]:
    rows: list[dict] = []
    # 8 roster + responded
    for idx, section in enumerate(_SECTIONS):
        sid = f"20261940{idx:02d}"
        rows.append(
            {
                "student_id": sid,
                "semester": "2026-1",
                "course_slug": "anatomy",
                "on_roster": True,
                "section": section,
                "name_kr": f"학생{idx:02d}",
                "diagnostic_responded": True,
                "exam_taken": False,
                "exam_absent": True,  # roster + not exam_taken ⇒ exam_absent True
                "attendance_recorded": False,
                "exam_total_score": None,
                "exam_max_score": None,
                "attendance_present_count": None,
                "attendance_absent_count": None,
                "attendance_late_count": None,
                "attendance_excused_count": None,
                "axis_scores": {"placeholder": None},
            }
        )
    # 1 off-roster + responded
    rows.append(
        {
            "student_id": "9999999999",
            "semester": "2026-1",
            "course_slug": "anatomy",
            "on_roster": False,
            "section": None,
            "name_kr": "명단외학생",
            "diagnostic_responded": True,
            "exam_taken": False,
            "exam_absent": False,  # NOT on_roster ⇒ exam_absent must be False
            "attendance_recorded": False,
            "exam_total_score": None,
            "exam_max_score": None,
            "attendance_present_count": None,
            "attendance_absent_count": None,
            "attendance_late_count": None,
            "attendance_excused_count": None,
            "axis_scores": {},
        }
    )
    # 1 roster + non-responded
    rows.append(
        {
            "student_id": "2026194099",
            "semester": "2026-1",
            "course_slug": "anatomy",
            "on_roster": True,
            "section": "A",
            "name_kr": "미응답학생",
            "diagnostic_responded": False,
            "exam_taken": False,
            "exam_absent": True,
            "attendance_recorded": False,
            "exam_total_score": None,
            "exam_max_score": None,
            "attendance_present_count": None,
            "attendance_absent_count": None,
            "attendance_late_count": None,
            "attendance_excused_count": None,
            "axis_scores": {},
        }
    )
    return rows


def _diagnostic_response_rows() -> list[dict]:
    """Long-form responses. Only 9 students respond (8 roster + 1 off-roster)."""
    rows: list[dict] = []
    responder_ids = [f"20261940{idx:02d}" for idx in range(8)] + ["9999999999"]

    # motivation: 3 items per responder; student_id "2026194002" is missing item 2
    for sid in responder_ids:
        for item_idx in range(3):
            if sid == "2026194002" and item_idx == 2:
                continue  # 1 motivation item missing for this student
            value = _LIKERT_VALUES[(int(sid[-2:]) + item_idx) % len(_LIKERT_VALUES)]
            rows.append(
                {
                    "student_id": sid,
                    "semester": "2026-1",
                    "course_slug": "anatomy",
                    "axis": "motivation",
                    "axis_kind": "likert",
                    "value_int": value,
                    "value_bool": None,
                    "value_text": None,
                    "option_key": None,
                    "source_column": f"Q01_motivation_{item_idx + 1}",
                }
            )
    # anxiety: 4 items per responder; student "2026194003" has ALL 4 items missing
    for sid in responder_ids:
        if sid == "2026194003":
            continue
        for item_idx in range(4):
            value = _LIKERT_VALUES[(int(sid[-2:]) + item_idx + 1) % len(_LIKERT_VALUES)]
            rows.append(
                {
                    "student_id": sid,
                    "semester": "2026-1",
                    "course_slug": "anatomy",
                    "axis": "anxiety",
                    "axis_kind": "likert",
                    "value_int": value,
                    "value_bool": None,
                    "value_text": None,
                    "option_key": None,
                    "source_column": f"Q05_anxiety_{item_idx + 1}",
                }
            )
    # self_efficacy: 2 items per responder
    for sid in responder_ids:
        for item_idx in range(2):
            value = _LIKERT_VALUES[(int(sid[-2:]) + item_idx + 2) % len(_LIKERT_VALUES)]
            rows.append(
                {
                    "student_id": sid,
                    "semester": "2026-1",
                    "course_slug": "anatomy",
                    "axis": "self_efficacy",
                    "axis_kind": "likert",
                    "value_int": value,
                    "value_bool": None,
                    "value_text": None,
                    "option_key": None,
                    "source_column": f"Q07_self_efficacy_{item_idx + 1}",
                }
            )
    # interest: 1 freetext item per responder
    interest_texts = [
        "근육 구조에 관심이 있어요.",
        "심혈관계가 흥미로워요.",
        "신경계 챕터 기대됩니다.",
        "호흡기계가 매력적입니다.",
        "내분비계 관심 있음.",
        "감각기관 관심 많아요.",
        "전부 흥미로움.",
        "특별히 없음.",
        "골격계가 좋습니다.",
    ]
    for sid, text in zip(responder_ids, interest_texts, strict=False):
        rows.append(
            {
                "student_id": sid,
                "semester": "2026-1",
                "course_slug": "anatomy",
                "axis": "interest",
                "axis_kind": "freetext",
                "value_int": None,
                "value_bool": None,
                "value_text": text,
                "option_key": None,
                "source_column": "Q11_interest_freetext",
            }
        )
    # prior_knowledge: 1 multiselect partition item, options {bio_high, bio_none}
    pk_choices = [
        "bio_high",
        "bio_high",
        "bio_none",
        "bio_none",
        "bio_high",
        "bio_high",
        "bio_none",
        "bio_high",
        "bio_high",
    ]
    for sid, choice in zip(responder_ids, pk_choices, strict=False):
        for option in ("bio_high", "bio_none"):
            rows.append(
                {
                    "student_id": sid,
                    "semester": "2026-1",
                    "course_slug": "anatomy",
                    "axis": "prior_knowledge",
                    "axis_kind": "multiselect_onehot",
                    "value_int": None,
                    "value_bool": option == choice,
                    "value_text": None,
                    "option_key": option,
                    "source_column": "Q03_prior_knowledge",
                }
            )
    # life_context: 1 multiselect partition item, options {worker, student}
    lc_choices = [
        "student",
        "worker",
        "student",
        "worker",
        "student",
        "worker",
        "student",
        "worker",
        "student",
    ]
    for sid, choice in zip(responder_ids, lc_choices, strict=False):
        for option in ("worker", "student"):
            rows.append(
                {
                    "student_id": sid,
                    "semester": "2026-1",
                    "course_slug": "anatomy",
                    "axis": "life_context",
                    "axis_kind": "multiselect_onehot",
                    "value_int": None,
                    "value_bool": option == choice,
                    "value_text": None,
                    "option_key": option,
                    "source_column": "Q04_life_context",
                }
            )
    # 2 free-text items (anxiety + life_context)
    anxiety_texts = [
        "암기가 너무 많습니다.",
        "시간이 부족해요.",
        "따라가기 어려워요.",
        "조금 불안하지만 괜찮습니다.",
        "기초가 부족합니다.",
        "걱정이 많아요.",
        "괜찮아요.",
        "외울 게 너무 많습니다.",
        "병행이 힘들어요.",
    ]
    for sid, text in zip(responder_ids, anxiety_texts, strict=False):
        rows.append(
            {
                "student_id": sid,
                "semester": "2026-1",
                "course_slug": "anatomy",
                "axis": "anxiety",
                "axis_kind": "freetext",
                "value_int": None,
                "value_bool": None,
                "value_text": text,
                "option_key": None,
                "source_column": "Q62_anxiety_freetext",
            }
        )
    lc_texts = [
        "주말에 알바합니다.",
        "야간 공부가 어렵습니다.",
        "통학시간이 깁니다.",
        "가족 도움 받습니다.",
        "직장과 병행입니다.",
        "특별한 사정 없음.",
        "간호사가 꿈입니다.",
        "도서관 자주 갑니다.",
        "조용히 공부합니다.",
    ]
    for sid, text in zip(responder_ids, lc_texts, strict=False):
        rows.append(
            {
                "student_id": sid,
                "semester": "2026-1",
                "course_slug": "anatomy",
                "axis": "life_context",
                "axis_kind": "freetext",
                "value_int": None,
                "value_bool": None,
                "value_text": text,
                "option_key": None,
                "source_column": "Q63_life_context_freetext",
            }
        )
    return rows


def main() -> None:
    _SILVER_DIR.mkdir(parents=True, exist_ok=True)
    sm = pd.DataFrame(_student_master_rows())
    dr = pd.DataFrame(_diagnostic_response_rows())
    sm.to_parquet(_SILVER_DIR / "student_master.parquet", index=False)
    dr.to_parquet(_SILVER_DIR / "diagnostic_response.parquet", index=False)
    print(f"Wrote {_SILVER_DIR}: student_master={len(sm)} rows, diagnostic_response={len(dr)} rows")


if __name__ == "__main__":
    main()
