# needs-map (paideia v0.1.0)

사전진단 분석 모듈 — 척도 신뢰도 / 의미축 점수 / 군집화 / 자유서술 분류 /
집단 분포 보고서 / 1인 1장 needs-map 카드를 결정론적으로 생산한다.
ingest(`001-ingest-phase0`)가 만든 진단 응답 Silver를 입력으로 받아
immersio Phase 3·4 결합 분석 + 학기 첫 면담 자료 + 차년도 출제 회고에
즉시 투입 가능한 산출을 만든다.

## 입력

3종 모두 필수 — 하나라도 부재·계약 위반이면 분석 중단 (FR-001).

| 입력 | 위치 | Pydantic 계약 |
|---|---|---|
| 진단 응답 Silver | `data/silver/immersio/{semester}-{course}/diagnostic_response.parquet` | `paideia_shared.schemas.DiagnosticResponse` |
| 학생 마스터 Silver | `data/silver/immersio/{semester}-{course}/student_master.parquet` | `paideia_shared.schemas.StudentMaster` |
| 매핑 YAML | `data/bronze/매핑/{course}.diagnostic.yaml` | `paideia_shared.schemas.DiagnosticMappingConfig` (V1~V6) |

## 산출

학기·교과목 단위 디렉터리에 격리(SC-008). 재실행 시 직전 산출은
`_archive/{ISO8601_UTC}/`로 무손실 이동(FR-002a).

```text
data/silver/needs-map/{semester}-{course}/
    ├── scale_reliability.parquet            # Phase A
    ├── factor_scores.parquet                # Phase B (immersio Phase 3 입력)
    ├── cluster_assignment.parquet           # Phase C (immersio Phase 4 입력)
    ├── free_text_categorization.parquet     # Phase D
    ├── manifest.json
    └── _archive/{ISO8601_UTC}/...

data/gold/needs-map/{semester}-{course}/
    ├── group_distribution.pdf               # Phase E
    ├── cluster_summary.xlsx                 # Phase E
    ├── cards/{student_id}.pdf               # Phase F (184장+α)
    ├── manifest.json
    └── _archive/{ISO8601_UTC}/...
```

## 6 Phase

| Phase | 산출 | 입력 | 핵심 함수 |
|---|---|---|---|
| A | scale_reliability.parquet | DR Silver + 매핑 | `compute_reliability` (Cronbach α 의미축별, FR-004/005) |
| B | factor_scores.parquet | DR Silver + StudentMaster + 매핑 | `aggregate_axis` × `apply_missing_policy` × `zscore` (FR-006/007/008) |
| C | cluster_assignment.parquet | factor_scores | `recommend_k` × `cluster_students` × `name_clusters` (FR-009~013) |
| D | free_text_categorization.parquet | DR Silver freetext + 키워드 사전 | `classify_dictionary` × `classify_with_llm_fallback` (FR-014~016) |
| E | group_distribution.pdf + cluster_summary.xlsx | factor_scores + cluster_report + 자유서술 | `compute_axis_distributions` × `compute_partition_for_axis` × `render_group_distribution_pdf` (FR-017/018) |
| F | cards/{student_id}.pdf | factor_scores + cluster_report + free_text + StudentMaster | `generate_all_cards` (FR-019~022) |

## 빠른 사용

```bash
# 전체 Phase, --no-llm 모드 (LLM 비활성)
uv run paideia-needs-map run \
    --semester 2026-1 \
    --course anatomy \
    --no-llm

# Phase A·B만 (immersio Phase 3 차단 해소용 빠른 실행, 30초 이내)
uv run paideia-needs-map run --semester 2026-1 --course anatomy --phases A-B --no-llm

# 군집 수 강제 (FR-010)
uv run paideia-needs-map run --semester 2026-1 --course anatomy --k 4 --no-llm
```

상세 사용법은 `specs/002-needs-map-v0-1-0/quickstart.md`.

## 의존성

| 카테고리 | 패키지 |
|---|---|
| 핵심 | pydantic ≥2.6, pandas ≥2.0, pyarrow ≥15, scikit-learn ≥1.4, scipy ≥1.11, numpy ≥1.26 |
| PDF/시각화 | matplotlib ≥3.8, reportlab ≥4, openpyxl ≥3.1 |
| LLM (옵션) | instructor ≥1, anthropic ≥0.40 |
| 기타 | pyyaml ≥6, python-dotenv ≥1, paideia-shared (workspace) |
| 시스템 | NixOS `noto-fonts-cjk-sans` (한국어 PDF 렌더링), Python 3.11 |

LLM 환경변수가 부재하면 모든 LLM 옵션은 자동 비활성되고 룰/사전/템플릿
폴백으로 정상 완주한다(SC-005).

## 헌장 5 원칙 준수

| # | 원칙 | 본 모듈 구현 |
|---|---|---|
| I | Deterministic-First with Optional LLM | KMeans `random_state=seed`, matplotlib dpi=150 + bbox='tight', reportlab `setProducer` + `setCreationDate`, 학번 zero-pad 정렬, NeedsMapArgs.created_at_utc 1회 캐시 (4축 결정성). LLM 옵션 4훅, 모두 폴백 1급 시민 |
| II | Bronze→Silver→Gold + Pydantic Contracts | 입력 3종 Silver 검증, 5 신규 모델(`ScaleReliabilityRow`/`FactorScoreRow`/`ClusterAssignmentRow`/`FreeTextRow`/`NeedsMapManifest`) 모두 `paideia_shared.schemas`에 위치. 모든 산출 모델 검증 통과 후에만 디스크 기록 |
| III | Variability via Configuration, Not Code | 매핑 YAML 외 코드는 의미축 키만 참조 (FR-024). `partition_axis: bool` 필드로 부분군 비교 가변성 흡수. 키워드 사전은 `shared/paideia_shared/keywords/{lang}.yaml` 외부 자산 |
| IV | Student-Individual as the Terminal Output | Phase F 1인 1장 카드(FR-019~022)가 종착 산출. Phase E 집단 보고서는 교수자 자기 점검 보조 |
| V | Privacy, Reproducibility, Audit Stewardship | `data/`는 paideia 루트 .gitignored. agenix 비밀키, env 부재 시 LLM 자동 비활성. LLM 페이로드 학번/이름 정규식 제거 + validation_flag (FR-PII-002~003). NeedsMapManifest에 입력 sha256 + LLM 통계 + archival 경로 + missing_policy 출처 모두 기록 |

## 운영 메모

- **report_tone polish (FR-018)**: v0.1.0은 룰 템플릿 only — LLM 호출 경로 미구현.
  spec FR-018의 운영 요구("LLM 부재·실패 시에도 보고서는 동일 구조로 정상 생성")는
  룰 템플릿만으로 충족됨. v0.2+에서 LLM tone polish 추가 검토.
- **Archive timestamp 형식**: ISO8601 표준은 `:` separator지만 본 모듈은 파일경로
  안전성을 위해 `-` separator로 치환 (`2026-04-27T00-12-34-567890Z`). 표준 변형
  의도이며 ingest와 호환 (운영 중 디스크 정리 시 단순 prefix sort로 시간순 보장).
- **결정성 4축**: KMeans seed + 학번 정렬 + matplotlib dpi/bbox + reportlab Producer/CreationDate.
  `--no-llm` 모드에서 두 회 실행 시 모든 parquet/PDF byte-equal (FR-022, SC-002).

## 레퍼런스

- spec: `specs/002-needs-map-v0-1-0/spec.md`
- plan: `specs/002-needs-map-v0-1-0/plan.md`
- contracts: `specs/002-needs-map-v0-1-0/contracts/{cli,keyword_dictionary.schema.yaml,needs_map_card.layout,diagnostic_mapping_extension}.md`
- 헌장: `.specify/memory/constitution.md` v1.0.0
