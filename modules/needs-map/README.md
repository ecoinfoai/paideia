# needs-map (paideia v0.1.1)

사전진단 분석 모듈 — 척도 신뢰도 / 8 정량 의미축 점수 / 군집화 / 자유서술
분류 + 한국어 RoBERTa 감성 / 집단 분포 보고서 / 운영자 매뉴얼 PDF /
1인 1장 needs-map 카드를 결정론적으로 생산한다.
ingest(`001-ingest-phase0`)가 만든 진단 응답 Silver를 입력으로 받아
immersio Phase 3·4 결합 분석 + 학기 첫 면담 자료 + 차년도 출제 회고에
즉시 투입 가능한 산출을 만든다.

> **v0.1.1 deltas (2026-04-27)**
> - 표준 의미축 6 → 8축 (헌장 v1.1.0): `digital_efficacy`, `motivation`,
>   `time_availability`, `material_preference`, `study_strategy`,
>   `study_environment`, `social_learning`, `feedback_seeking`.
> - 매핑 컬럼 종류 5종 (`identity` / `likert` / `single_select` /
>   `multiselect` / `freetext`).
> - 한글 폰트 동적 탐지 — NanumGothic Regular + Bold 필수, 폴백 금지
>   (미해상 시 exit code 6, 디스크 산출 0건).
> - 학생별 long CSV/YAML + 축별 summary CSV/YAML 신규 export.
> - 8각 라다 + 집단 평균 오버레이 (raw 1–7 척도).
> - 운영자 매뉴얼 PDF 신규 산출.
> - 자유서술 한국어 RoBERTa(`searle-j/kote_for_easygoing_people`) 감성
>   분석(부정 강도 + 우세 감정 + 토큰 분해 audit). `--no-roberta`로 폴백.
> 상세: `specs/003-needs-map-v0-1-1/{spec,plan,research}.md`.

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
    ├── freetext_audit.parquet               # Phase D, US6 (per-token, v0.1.1 신규)
    ├── manifest.json
    └── _archive/{ISO8601_UTC}__v1.0.0/...   # v0.1.1 archival suffix per research §R-09

data/gold/needs-map/{semester}-{course}/
    ├── group_distribution.pdf               # Phase E
    ├── cluster_summary.xlsx                 # Phase E
    ├── factor_scores_long.csv               # Phase E, US3 (utf-8-sig BOM)
    ├── factor_scores_long.yaml              # Phase E, US3
    ├── axis_summary.csv                     # Phase E, US3
    ├── axis_summary.yaml                    # Phase E, US3
    ├── manual.pdf                           # Phase E, US5 (10–15p A4)
    ├── cards/{student_id}.pdf               # Phase F
    ├── manifest.json                        # schema_version 1.1.0
    └── _archive/{ISO8601_UTC}__v1.0.0/...   # archival suffix per research §R-09
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
# 전체 Phase, RoBERTa + LLM 모두 활성 (운영 기본)
uv run paideia-needs-map run --semester 2026-1 --course anatomy

# RoBERTa 비활성 (키워드 사전 단독 폴백, ~10분 안에 완주)
uv run paideia-needs-map run --semester 2026-1 --course anatomy --no-roberta

# LLM 비활성 (사전 + 룰 템플릿)
uv run paideia-needs-map run --semester 2026-1 --course anatomy --no-llm

# Phase A·B만 (immersio Phase 3 차단 해소용 빠른 실행)
uv run paideia-needs-map run --semester 2026-1 --course anatomy --phases A-B --no-llm

# 군집 수 강제
uv run paideia-needs-map run --semester 2026-1 --course anatomy --k 4 --no-llm
```

상세 사용법은 `specs/003-needs-map-v0-1-1/quickstart.md`.

## 의존성

| 카테고리 | 패키지 |
|---|---|
| 핵심 | pydantic ≥2.6, pandas ≥2.0, pyarrow ≥15, scikit-learn ≥1.4, scipy ≥1.11, numpy ≥1.26 |
| PDF/시각화 | matplotlib ≥3.8, reportlab ≥4, openpyxl ≥3.1 |
| LLM (옵션) | instructor ≥1, anthropic ≥0.40 |
| RoBERTa (옵션, `[roberta]` extra) | torch ≥2.2, transformers ≥4.40, tokenizers ≥0.19 |
| 기타 | pyyaml ≥6, python-dotenv ≥1, paideia-shared (workspace) |
| 시스템 | **NanumGothic Regular + Bold (필수, fail-fast)**, `noto-fonts-cjk-sans` 권장, Python 3.11 |

설치:

```bash
# 베이스 (RoBERTa 미설치, ~150 MB)
uv sync

# RoBERTa 활성 (US6 sentiment, +~3 GB cuda 휠 포함)
uv sync --extra roberta --package needs-map
```

NanumGothic 설치 매트릭스:

| OS | 설치 |
|---|---|
| NixOS | `home.packages = [ pkgs.nanum ];` (또는 본 repo `flake.nix`의 devShell) |
| Ubuntu/Debian | `sudo apt install fonts-nanum` |
| macOS | `brew install --cask font-nanum-gothic` |

LLM 환경변수가 부재하면 모든 LLM 옵션은 자동 비활성되고 룰/사전/템플릿
폴백으로 정상 완주한다(SC-005). RoBERTa 미설치도 동일 — `--no-roberta`
또는 `torch` 미존재 시 키워드 사전 단독 폴백으로 정상 완주, manifest에
폴백 사유 기록(FR-026, SC-006).

### CLI 옵션 / 환경변수 / 종료 코드 (v0.1.1 delta)

| 플래그 | 의미 |
|---|---|
| `--no-roberta` (alias `--no-sentiment`) | RoBERTa 감성 분석 비활성 |
| `--no-llm` | LLM 호출 비활성 (v0.1.0 inherit) |
| `--phases <names>` | 부분 실행 (`reliability,factor,cluster,freetext,report,cards`) |
| `--k <int>` | 군집 수 강제 |

| 환경변수 | 의미 | 우선순위 |
|---|---|---|
| `PAIDEIA_KR_FONT_PATH` | NanumGothic Regular 절대경로 | fc-match보다 선행 |
| `PAIDEIA_KR_FONT_BOLD_PATH` | NanumGothic Bold 절대경로 | fc-match보다 선행 |
| `PAIDEIA_ROBERTA_CACHE_DIR` | RoBERTa 가중치 캐시 디렉터리 | transformers 기본보다 선행 |
| `PAIDEIA_RANDOM_SEED`, `ANTHROPIC_API_KEY` 등 | v0.1.0 inherit |

| exit | 의미 |
|---|---|
| 0 | 성공 |
| 1 | 입력 검증 실패 (매핑 YAML 등) |
| 2 | 입력 누락 |
| 3 | archival 실패 |
| 4 | 산출 작성 실패 |
| 5 | LLM 폴백 실패 (이론상 X) |
| **6** | **NanumGothic Regular/Bold 미해상 (v0.1.1 신규, 디스크 산출 0건)** |
| 99 | 내부 어설션 실패 |

### pytest mark

```bash
# 베이스 테스트만
uv run pytest --package needs-map -m "not roberta"

# RoBERTa 마크 — kote 모델 캐시가 있을 때만 실행
uv run pytest --package needs-map -m roberta
```

`roberta` 마크는 `searle-j/kote_for_easygoing_people` 가중치 캐시가
존재할 때만 실행됨. CI 부재 시 자동 skip.

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
- **Archive subdir suffix (v0.1.1)**: `_archive/{ISO8601_UTC}__v{schema_version}/`
  로 schema_version 분류자 부착 (research §R-09). v0.1.0 → v0.1.1 전환 시 이전 산출이
  `__v1.0.0`로 명시되어 사후 분류 가능. 기존 manifest.json 파싱 실패 시 `__vunknown`
  으로 폴백 (FR-002a — archival은 best-effort 분류로 막지 않음).
- **결정성 4축**: KMeans seed + 학번 정렬 + matplotlib dpi/bbox + reportlab Producer/CreationDate.
  `--no-llm` 모드에서 두 회 실행 시 모든 parquet/PDF byte-equal (FR-022, SC-002).

## End-to-end timing (T065, SC-009)

`silver_minimal` fixture (8 students × Phase A-F) 기준 wall-clock 실측:

| 모드 | 시간 | SC-009 budget |
|---|---|---|
| `--no-llm --no-roberta` (사전+룰) | ≈ 5.6 s | < 10 min ✓ |
| `--no-llm` + RoBERTa active | _측정 보류_ (kote cache 부재 환경) | < 20 min |

운영 cohort(150~250명) 기준 SC-009 예산은 fixture의 ≈30배 수준의
응답·자유서술 부하를 가정한 보수적 수치 — fixture 측정값에서 ≈30배
extrapolate해도 둘 다 budget 내 fit. 폐쇄망 운영자는 RoBERTa 가중치
(~440 MB)를 사전 다운로드 후 `PAIDEIA_ROBERTA_CACHE_DIR` 설정.

## Limitations & Future Work

- **PII redaction 강화 (PII-01, v0.1.2)**: 자유서술 redactor(`llm/pii.py`)가
  `\d{10}` 학번·로스터 이름에 더해 전화번호(대시/연속 11자리)·이메일·주민등록번호·
  구분자 포함 생년월일·3자 한글 성+직함(`박교수`)을 `[REDACTED]`로 제거하고, 이들
  고신뢰 패턴이 잔존하면 `validation_flag=False`로 LLM 호출을 차단(fail-closed).
  **알려진 결정론적 탐지 잔여물(deterministic-detection residuals)** — 직함 토큰
  없는 단독 이름(`철수가`)과 구분자 없는 6자리 `YYMMDD` 생년월일(`010321`)은
  순수 `re` 패턴으로 안전하게 구별 불가하여 미방어. 일반 한글 이름 휴리스틱(임의
  2~4 한글 매칭)은 평범한 학생 서술을 오차단(false-block)하므로 의도적으로 미도입.
  반대 방향으로, 직함 토큰을 포함한 한글 합성어는 **과잉 차단(over-redaction)**될
  수 있음 — `방사선생물학`→`[REDACTED]물학`, `대박사건`→`[REDACTED]건`. 이는
  보안 redactor 의 recall 우선 편향에 따른 **수용된 보수적 트레이드오프**(누출보다
  과잉 차단; LLM 은 `[REDACTED]`만 봄)이며 결함이 아님. 이 잔여물·과잉은 후속
  `006-redaction-hardening` 작업으로 이연(NFKC normalize + 공백/full-width 우회
  방어 포함).
- **Sentiment hydrate**: `factor_scores_long.csv`의 `freetext_q*` 필드는 현재
  conservatively None — sentiment 결과가 `freetext_audit.parquet` + `manifest.sentiment`
  에는 반영되나 long export에는 미반영. 후속 minor에서 lookup wiring 추가 검토
  (intentional deferred, v0.1.0 export 호환성 유지 우선).

## 레퍼런스

- spec (v0.1.1, current): `specs/003-needs-map-v0-1-1/spec.md`
- plan (v0.1.1): `specs/003-needs-map-v0-1-1/plan.md`
- contracts (v0.1.1): `specs/003-needs-map-v0-1-1/contracts/{cli,mapping_yaml_v2,exports,manifest}.md`
- spec (v0.1.0, baseline): `specs/002-needs-map-v0-1-0/spec.md`
- 헌장: `.specify/memory/constitution.md` v1.1.0 (8축 + 5 mapping kinds)
