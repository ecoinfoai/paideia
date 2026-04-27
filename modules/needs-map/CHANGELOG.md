# Changelog — needs-map

## 0.1.0 — 2026-04-27

신규 모듈 — paideia 우산의 첫 분석 모듈. ingest(`001-ingest-phase0`) Silver 3종을
입력으로 받아 6 Phase(A-F) 결정론적 분석을 수행한다.

### 신규 산출 (Silver)

- `scale_reliability.parquet` — Phase A 의미축별 Cronbach α + label
  + operational_warning (`ScaleReliabilityRow`).
- `factor_scores.parquet` — Phase B 학생×의미축 점수 + z-score + 결측 플래그
  (`FactorScoreRow`). immersio Phase 3 결합 분석의 입력.
- `cluster_assignment.parquet` — Phase C K-means 군집 라벨 + 거리
  (`ClusterAssignmentRow`). immersio Phase 4 라벨링 룰의 입력.
- `free_text_categorization.parquet` — Phase D 자유서술 카테고리 + match_source
  5종 enum (`FreeTextRow`). 원문 텍스트 미저장 (PII 보호).

### 신규 산출 (Gold)

- `group_distribution.pdf` — Phase E 의미축 분포 + 군집 요약 + 자유서술 카테고리
  + 부분군 비교 (분반 + `partition_axis: true` 매핑 항목).
- `cluster_summary.xlsx` — Phase E 군집 요약 워크북 (1 summary sheet + 1 sheet
  per cluster).
- `cards/{student_id}.pdf` — Phase F 1인 1장 needs-map 카드. 응답자 + 명단
  미응답자 전원 (zero-pad 10자리 파일명).

### 신규 사이드카

- `manifest.json` (Silver + Gold 양쪽에 동일 사본) —
  입력 sha256 + 표준 어휘 사용/skip 표 + 단계별 행수 + LLM 호출 통계
  (cluster_naming/free_text/coaching) + PII 검증 boolean +
  archival 경로 + missing_policy 출처 (`NeedsMapInput.missing_policy_source`).

### 신규 / 변경 계약 (paideia_shared.schemas)

- **신규**: `StandardAxisKey` (Literal 6 어휘) — `motivation`, `anxiety`,
  `self_efficacy`, `interest`, `prior_knowledge`, `life_context`.
- **신규**: `NeedsMapInput`, `LLMCallStat`, `NeedsMapPhaseRowCount`,
  `NeedsMapManifest`.
- **신규**: `ScaleReliabilityRow`, `ScaleReliabilityReport`.
- **신규**: `FactorScoreRow`.
- **신규**: `ClusterAssignmentRow`, `ClusterCandidate`, `ClusterReport`.
- **신규**: `FreeTextRow`.
- **변경 (호환 깨짐)**: `MappingColumn.partition_axis: bool = False` 필드 추가
  + `v5_partition_axis_only_for_classifying_kinds` validator. 기존 매핑 YAML과
  비파괴(default False).
- **변경 (호환 깨짐)**: `DiagnosticMappingConfig.v6_axes_are_standard_paideia_vocabulary`
  validator 추가. 표준 6 어휘 외 키 사용 시 ValidationError —
  paideia minor 버전 bump 메시지 안내.
- **변경 (호환)**: `v4_aggregate_consistent_per_axis` validator는 이제
  `freetext` kind 컬럼을 면제 (likert + freetext가 한 axis를 공유하는
  spec-intended 패턴 허용 — contracts/diagnostic_mapping_extension.md).

### 신규 자산 (shared)

- `paideia_shared.keywords/__init__.py` — `KeywordEntry`, `KeywordDictionary`
  Pydantic 스키마 + `load(language)` 헬퍼.
- `paideia_shared/keywords/ko.yaml` — 한국어 default 5 카테고리 사전.
  immersio Phase 5와 공유. 사전 변경 = paideia minor 버전 bump (FR-026).

### 신규 / 변경 ingest 호환성

- `interest_chapters` axis 키 → 표준 `interest`로 마이그레이션 (paideia v6 정합).
- `anxiety_freetext` axis 키 → 표준 `anxiety` (V4 freetext 면제로 likert+freetext
  같은 axis 공유).
- ingest fixtures + docs/axis-keys.md 본 변경에 동기화 완료.

### CLI

- 신규 console_script: `paideia-needs-map run`.
- 13 flag: `--semester`, `--course`, `--phases {A-B,A-C,A-D,A-E,A-F,all}`,
  `--k {2..6}`, `--no-llm`, `--llm-provider {anthropic,openai}`,
  `--llm-model`, `--input-root`, `--output-root`,
  `--keyword-language {ko}`, `--seed`, `--dry-run`, `--verbose`.
- Exit codes (cli.md): 0 success / 1 arg / 2 input contract / 3 output
  contract / 4 archival or data integrity / 99 internal.
- `--k=1`은 표본 부족 자동 폴백 전용으로 CLI에서 차단 (FR-010).
- `--no-llm` > env presence 우선순위 (Phase 2 design alignment §3.2).

### 의존성

- 추가: scikit-learn ≥1.4, scipy ≥1.11, matplotlib ≥3.8, reportlab ≥4,
  openpyxl ≥3.1, instructor ≥1, anthropic ≥0.40, python-dotenv ≥1.
- 시스템 (NixOS): `noto-fonts-cjk-sans` (flake.nix devShell buildInputs).

### 결정성 4축 (FR-022 / SC-002)

1. KMeans `random_state = NeedsMapArgs.seed` (default 42, env override).
2. 학생 정렬: 학번 zero-pad string 오름차순 (clustering input + cards batch).
3. matplotlib `dpi=150 + bbox_inches="tight"` keyword-only 고정.
4. reportlab `setProducer("paideia/needs-map/0.1.0")` + `setCreationDate(args.created_at_utc)`.

`--no-llm` 모드에서 두 회 실행 시 모든 silver parquet + gold PDF byte-equal.

### 운영 노트 (제한 사항)

- **FR-018 LLM tone polish**: v0.1.0은 룰 템플릿 only. spec의 운영 요구
  ("LLM 부재·실패 시에도 보고서는 동일 구조로 정상 생성")는 충족됨. LLM tone
  polish 호출 경로는 v0.2+에서 추가 검토.
- **Archive timestamp**: 표준 ISO8601 `:` separator 대신 파일경로 안전성을
  위해 `-` separator 채택 (`2026-04-27T00-12-34-567890Z`). 표준 변형은 의도
  이며 단순 prefix sort로 시간순 보장.
- **`raw_text` 미저장**: `FreeTextRow`는 원문 텍스트를 저장하지 않고
  `raw_length`만 기록 (FR-PII-002).
- **`name_kr` LLM 미전송**: 모든 LLM 호출은 `paideia_shared.llm.pii.redact`로
  `\d{10}` 학번 + 명단 이름을 `[REDACTED]`로 치환 후 송신.
  validation_flag=False 시 호출 차단(`failure_kind="pii_block"`).

### Sequential edit (Phase 1 boundary map closure)

본 릴리스에서 4개 orchestrator 파일이 phase 경계마다 sequential edit됨 —
모두 INTEGRATION 태그로 박제 추적.

| 파일 | Edit 차수 |
|---|---|
| `paideia_shared/schemas/__init__.py` | T015 → T051 → T070 → T094 (4/4) |
| `paideia_shared/schemas/diagnostic_mapping.py` | T009 → T010 (+ V4 freetext fix) |
| `needs_map/pipeline.py` | T031 → T056 → T074 → T105 (4/4) |
| `needs_map/cli/main.py` | T032 → T057 → T075 → T106 (4/4) |

### 알려진 잔여

- T115 quickstart end-to-end의 manual run 측정 (SC-001 30초 / SC-005 no-llm
  완주)은 운영 머신 가용 시 별도 회차로 확인 권장.
- v0.2.0 (`idea/needs-map-v0.2.0.md`) 진입 시 (a) report_tone LLM polish,
  (b) per-axis missing_policy YAML 명시, (c) 다국어 키워드 사전, (d) gap
  statistic k-recommend 검토 예정.
