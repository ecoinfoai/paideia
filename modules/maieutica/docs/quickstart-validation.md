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

---

## v0.1.1 — 챕터 내 다양성·정답 균형 (010-maieutica-quiz-diversity)

`specs/010-maieutica-quiz-diversity/quickstart.md` 의 SC-001~006 을 합성(synthetic)
픽스처 기반 통합/단위 테스트로 매핑한다. 모든 인용 테스트는 현재 **통과**한다
(아래 7개 파일·20 테스트 그린 확인).

| SC | 검증 항목 | Covered by | Key Assertions |
|----|-----------|-----------|----------------|
| SC-001 | 내용 중복 0 (정답 근거 앵커 distinct) | `tests/integration/test_us1_diversity.py::test_us1_diversity_distinct_anchors_and_spread` | 모든 후보의 `(textbook_evidence.chunk_id, line)` 앵커가 서로 다름(중복 쌍 0); FR-001/008 |
| SC-002 | 소절 분산 (≥2 소절, ≤3/소절) | `tests/integration/test_us1_diversity.py::test_us1_diversity_distinct_anchors_and_spread` | 후보가 둘 이상의 소절에 분산; 한 소절당 ≤3; FR-002/003/004 |
| SC-003 | 정답 균형 (최장 연속 ≤2, <50%) | `tests/integration/test_us2_balance.py::test_us2_balance_breaks_runs_and_is_deterministic` | `answer_no` 수열 동일 값 3연속 없음 + 어떤 번호도 ≤과반; 보기 순번 유지; 결정성 동반; FR-006/007 |
| SC-004 | byte-identical 재실행 | `tests/integration/test_determinism_v011.py::test_build_byte_identical_xls_xlsx_yaml_across_two_runs` · `::test_cached_rebuild_makes_zero_llm_recalls` | 두 run 의 `.xls`+`.xlsx`+`완전판.yaml` byte-identical(동일 run_id); 캐시 적중 시 LLM 재호출 0; FR-011 |
| SC-005 | 소절 앵커 / 미확인 0 / 제외 + 리포트 | `tests/integration/test_us3_anchor_report.py::test_us3_unconfirmed_excluded_and_reported` + `tests/unit/test_groundedness_subsection_scope.py` (8 케이스) | 미확인 후보 채택 제외(미확인 0) + 품질리포트 사유 명시; 앵커가 귀속 소절 범위 내·제목 줄 0; FR-009/015 |
| SC-006 | 편집 없이 업로드 (SC-001+003+005 동시충족) | 위 SC-001/003/005 테스트 + FR-013 LMS 포맷 계약: `tests/contract/test_quiz_upload_xls.py::test_quiz_xls_roundtrip_structure_and_cell_types` · `tests/contract/test_formative_xlsx.py::test_formative_xlsx_roundtrip_structure_and_cell_types` · `test_determinism_v011.py::test_build_xls_roundtrip_cell_types_and_zero_padding` · `::test_build_xlsx_roundtrip_cell_types` | 강제 편집 0건은 중복 0·정답 균형·확인 앵커 동시 충족으로 transitively 성립; 공개 LMS 셀 타입·0-패딩 계약 무회귀(FR-013) |

### Manual live validation (pending)

`specs/010-maieutica-quiz-diversity/quickstart.md` 의 실엔드투엔드 단계 —
8장 호흡계통(2026-1) N=15 `maieutica build --week 9 --quiz-count 15 --backend api` 를
실제 Bronze `.txt` 위에서 돌려 산출 `출제후보_완전판.yaml`/`출제품질리포트.md`/`.xls` 로
SC-001~006 을 사람이 수동 확인하는 것 — 은 남은 휴먼 검증 단계다. 실 Bronze 교재(`data/`,
gitignore·미동봉)와 Anthropic api 접근이 동시에 필요하므로 본 자동 세션에서는 실행하지
않았다. 위 합성 스위트가 동일 SC 들을 결정론적으로(실 api 없이) 성립시킨다.

### v0.1.1 SCs: COVERED (synthetic) — live run pending human step
