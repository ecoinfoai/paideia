# Quickstart Scenario → Integration Test Mapping

Validation that every scenario in `specs/009-maieutica-question-gen/quickstart.md`
is covered by an existing integration test that is currently **passing**.

Reference suite baseline: **298 tests, 0 failures**.

---

## Scenario Coverage Table

| # | Quickstart Scenario | Covered by | Key Assertions |
|---|---------------------|-----------|----------------|
| 1 | 퀴즈 후보 생성 + LMS 업로드 양식 (US1, P1) | `tests/integration/test_us1_quiz_build.py::test_us1_quiz_build_end_to_end` | 안내 시트 + Sheet1 11컬럼·quiz_count행; 보기 5개·정답 1개·30–50자; SC-007 앵커; manifest present; SC-003 셀 타입 (`tests/contract/test_quiz_upload_xls.py::test_quiz_xls_roundtrip_structure_and_cell_types`) |
| 2 | 도약 설명 fold (US2, P1) | `tests/integration/test_us2_leap_fold.py::test_us2_leap_fold_end_to_end` | `答案설명` == `{wrong} ─ 도약 ─ {leap}`; wrong/leap ≤200자; yaml `leap.text` 무손실 보존; round-trip 분리 |
| 3 | 형성평가 후보 (US3, P2) | `tests/integration/test_us3_formative.py::test_us3_formative_build_end_to_end` | `Ch{NN}_{chapter}_FormativeTest.xlsx` 14컬럼·formative_count행; rubric·support·keywords 채워짐; `support_high` 도약형 (SC-E1/FR-014); SC-003 셀 타입 (`tests/contract/test_formative_xlsx.py::test_formative_xlsx_roundtrip_structure_and_cell_types`) |
| 4 | 메타데이터·완전판·채택상태 (US4, P2) | `tests/integration/test_us4_metadata_consistency.py::test_us4_full_yaml_quality_report_consistency` | FR-015 전체 메타데이터 필드; 평탄화↔완전판 일치; `adoption_status` 컬럼(기본 `생성`); `출제품질리포트.md` 섹션 |
| 5 | 자동 2차 재검토 (US5, P3) | `tests/integration/test_us5_review.py` (여러 케이스) | 최초 `review_note == ""`; 재검토 후 결함 후보에 채워짐; verify CLI 서브커맨드 exit 0; yaml round-trip |
| 6a | 결정론 (US6, byte-identical) | `tests/integration/test_us6_determinism.py::test_us6_determinism_gold_outputs_byte_identical` | `.xls`+`.xlsx`+yaml+report byte-identical; manifest만 비결정론 |
| 6b | 사람 폴백·dry-run (US6, SC-011) | `tests/integration/test_us6_dryrun_degrade.py::test_us6_dryrun_writes_quiz_and_formative_bundles` | N+M 번들 산출; LLM 0 호출; ingest_report 기록; 하드 중단 없음 |
| 6c | manifest 동반 (US6, SC-012) | `tests/integration/test_us1_quiz_build.py::test_us1_quiz_build_end_to_end` (manifest assert) + `test_us6_determinism` | `manifest_maieutica.json` present; `generated_at` 필드 존재 |
| 7 | examen 입력 seam (US6, FR-024) | `tests/integration/test_us6_examen_seam.py::test_us6_examen_seam_identifiers` | `week`·`chapter_no`·`chapter`·`textbook_evidence.source_file`; `question_type` ∈ `{지식축적, 맥락통찰}`; `difficulty` ∈ `{상, 중, 하}` |

### Edge checks (quickstart §"Edge 검증")

| Edge case | Covered by |
|-----------|-----------|
| 챕터 `.txt` 결측 → exit 2, Gold 미작성 | `tests/unit/test_cli.py::test_missing_input_exits_2` (parametrized 6 subcommands) + `tests/integration/test_edge_cases.py::test_missing_chapter_txt_exits_2_no_gold` |
| curriculum_map 주차 결측 → exit 2 | `tests/integration/test_edge_cases.py::test_missing_week_in_map_exits_2` |
| 정답 숫자 셀 → SC-003 위반 | `tests/contract/test_quiz_upload_xls.py` (SC-003 roundtrip) + `tests/integration/test_edge_cases.py::test_answer_cell_is_text_even_for_single_digit` |

---

## All 7 scenarios: COVERED and PASSING ✓

All scenarios map to named tests; no uncovered scenario was found.
The edge-case assertions are strengthened in `tests/integration/test_edge_cases.py`
(T063 additions).
