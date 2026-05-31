# how_to_use_needs-map

> **needs-map v0.1.x** — 사전진단 분석 모듈.
> 척도 신뢰도 · 8개 정량 의미축 점수 · 군집화 · 자유서술 분류/감성 ·
> 집단 분포 보고서 · 운영자 매뉴얼 · **1인 1장 피드백 카드**를
> 결정론적으로 생산한다.

학기 첫 1~2주, 사전진단(요구조사) 설문 응답으로부터 학생 집단·개인 패턴을
도출하는 paideia 의 **첫 모듈**이다. 산출은 immersio Phase 3(결합 분석)와
차년도 retro-mester 회고에 그대로 투입된다.

---

## 1. 한눈에

```bash
uv run --package needs-map paideia-needs-map run \
  --semester 2026-1 \
  --course   anatomy
```

- 콘솔 스크립트 이름: **`paideia-needs-map`** (pyproject `project.scripts`)
- 서브커맨드: `run`
- 입력: `data/silver/immersio/{semester}-{course}/` + 진단 매핑 YAML
- 산출: `data/{silver,gold}/needs-map/{semester}-{course}/`

---

## 2. 입력 (3종 모두 필수)

하나라도 부재·계약 위반이면 분석 중단(부분 산출 금지).

| 입력 | 경로 | 계약 |
|---|---|---|
| 진단 응답 Silver | `data/silver/immersio/{semester}-{course}/diagnostic_response.parquet` | `DiagnosticResponse` |
| 학생 명단 Silver | `data/silver/immersio/{semester}-{course}/student_master.parquet` | `StudentMaster` |
| 진단 매핑 YAML | `data/bronze/매핑/{course}.diagnostic.yaml` | `DiagnosticMappingConfig` (**mapping_version: 2**) |

> 앞 두 Silver 는 `immersio ingest`(Phase 0)가 설문 CSV·출석부로부터 만든다.

### 매핑 YAML v2 골격

```yaml
metadata:
  semester: '2026-1'
  course_slug: 'anatomy'
  course_name_kr: '인체구조와기능'
  mapping_version: 2            # ★ v0.1.1 필수 (v1 거부 → exit 1)

columns:
  - source: 'student_id'
    kind: identity
  - source: 'Q1_digital_efficacy'
    kind: likert
    axis: digital_efficacy
    aggregate: mean
    ordinal_map: {'전혀 그렇지 않다.': 1, ..., '매우 그렇다.': 7}
  # ... motivation, time_availability, material_preference, study_strategy,
  #     study_environment, social_learning, feedback_seeking (8축 전부 필수)
  - source: 'Q61_anxiety'
    kind: freetext
    axis: anxiety_freetext

axes:
  required:                     # 표준 8축을 정확히 포함 (부분/초과 모두 거부)
    - digital_efficacy
    - motivation
    - time_availability
    - material_preference
    - study_strategy
    - study_environment
    - social_learning
    - feedback_seeking
  optional:
    - prior_readiness
    - anxiety_freetext
```

**컬럼 종류(kind)**: `identity` / `likert` / `single_select` / `multiselect` / `freetext`.
파일 크기 ≤ 256 KB (DoS 방어).

---

## 3. CLI 옵션

### 필수

| 플래그 | 형식 | 예시 |
|---|---|---|
| `--semester` | `^\d{4}-[12SW]$` | `2026-1` |
| `--course` | `^[a-z][a-z0-9-]{1,39}$` | `anatomy` |

### Phase·분석 제어

| 플래그 | 기본값 | 의미 |
|---|---|---|
| `--phases` | `all` | 실행 범위. `A-B`·`A-C`·`A-D`·`A-E`·`A-F`·`all` |
| `--k` | (자동) | 군집 수 강제(2–6). 미지정 시 silhouette 자동 추천. **k=1 거부** |
| `--no-llm` | off | LLM 비활성 — 룰/사전/템플릿 폴백 |
| `--no-roberta` (별칭 `--no-sentiment`) | off | RoBERTa 감성분석 비활성 — 키워드 사전 단독 |

### LLM 설정 (env 로도 지정 가능)

| 플래그 | 기본값 / env |
|---|---|
| `--llm-provider` | `PAIDEIA_LLM_PROVIDER` / `anthropic` |
| `--llm-model` | `PAIDEIA_LLM_MODEL` / `claude-sonnet-4-6` |
| `--llm-timeout-seconds` | `30.0` |
| `--llm-retries` | `1` |

### 경로·유틸리티

| 플래그 | 기본값 | 의미 |
|---|---|---|
| `--input-root` | `./data` | Bronze/Silver 입력 루트 |
| `--output-root` | `./data` | Silver/Gold 출력 루트 |
| `--keyword-language` | `ko` | 키워드 사전 언어 |
| `--seed` | `PAIDEIA_RANDOM_SEED` / `42` | 난수 seed |
| `--dry-run` | off | 입력 검증·계획만, 산출 미생성 |
| `--verbose` | off | DEBUG 로그 |

### 환경 변수

| 변수 | 의미 |
|---|---|
| `PAIDEIA_KR_FONT_PATH` / `_BOLD_PATH` | NanumGothic Regular/Bold 절대 경로 (`fc-match` 보다 선행) |
| `PAIDEIA_ROBERTA_CACHE_DIR` | RoBERTa 가중치 캐시 |
| `ANTHROPIC_API_KEY` | LLM 활성 시 필수 |

---

## 4. 처리 파이프라인 (6 Phase)

| Phase | 산출(Silver) | 알고리즘 |
|---|---|---|
| **A** | `scale_reliability.parquet` | Cronbach's α (축별 신뢰도, n_items≥3) |
| **B** | `factor_scores.parquet` | 평균 집계 → 결측 정책 → z-score |
| **C** | `cluster_assignment.parquet` | silhouette → KMeans → 규칙 기반 군집명 |
| **D** | `free_text_categorization.parquet` | 키워드 사전 매칭 → LLM 폴백 |
| **D+** | `freetext_audit.parquet` | RoBERTa 감성 + 토큰 분해 audit |
| **E** | (Gold) 집단 분포 PDF·군집요약 xlsx·long/summary export·운영자 매뉴얼 PDF | 분포 계산 + matplotlib/reportlab |
| **F** | (Gold) `cards/{학번}.pdf` | 8각 라다 + cohort 평균 오버레이 + 코칭 |

B 의 `factor_scores` 와 C 의 `cluster_assignment` 는 **immersio Phase 3/4 의
입력**이다. C·E·F 는 B 산출을 요구하며 미실행 시 자동 합성한다.

---

## 5. 산출 파일

### Silver (`data/silver/needs-map/{semester}-{course}/`)
`scale_reliability.parquet` · `factor_scores.parquet` ·
`cluster_assignment.parquet` · `free_text_categorization.parquet` ·
`freetext_audit.parquet` · `manifest.json`

### Gold (`data/gold/needs-map/{semester}-{course}/`)
- `group_distribution.pdf` — 8축 분포 히스토그램 + 군집 오버레이
- `cluster_summary.xlsx` — 군집별 요약
- `factor_scores_long.{csv,yaml}` — 학생별 long-form (CSV 는 UTF-8 BOM)
- `axis_summary.{csv,yaml}` — 축별 요약
- `needs-map_manual.pdf` — 운영자 매뉴얼 (결정론 생성)
- `cards/{학번}.pdf` — **1인 1장 카드** (8각 라다 + 코칭)
- `manifest.json`

재실행 시 직전 산출은 `_archive/{ISO8601_UTC}__v{schema}/` 로 무손실 이동된다.

---

## 6. 사용 예시

```bash
# 풀 실행 (RoBERTa + LLM)
uv run --package needs-map paideia-needs-map run --semester 2026-1 --course anatomy

# 폐쇄망/고속 (외부 호출 0)
uv run --package needs-map paideia-needs-map run \
  --semester 2026-1 --course anatomy --no-llm --no-roberta

# immersio Phase 3 입력만 빠르게 준비 (A-B)
uv run --package needs-map paideia-needs-map run \
  --semester 2026-1 --course anatomy --phases A-B --no-llm

# 군집 수 고정
uv run --package needs-map paideia-needs-map run \
  --semester 2026-1 --course anatomy --k 4

# 입력 검증만
uv run --package needs-map paideia-needs-map run \
  --semester 2026-1 --course anatomy --dry-run
```

RoBERTa 감성분석을 쓰려면 선택 의존성 설치:

```bash
uv sync --extra roberta --package needs-map
```

---

## 7. 종료 코드

| 코드 | 조건 | 산출 |
|---|---|---|
| 0 | 성공 (LLM/RoBERTa 폴백도 정상 → 0) | 완전 |
| 1 | 인자 오류 (`--k=1`, 잘못된 semester, 매핑 v1) | 0건 |
| 2 | 입력 파일 부재·계약 위반 | 0건 |
| 3 | archival 실패 | 0건 (atomic) |
| 4 | 산출 작성 실패 (권한·디스크) | 부분 |
| 6 | **NanumGothic 미설치** (Regular/Bold) | 0건 (pre-flight) |
| 99 | 내부 버그 | 부분 |

---

## 8. 자주 막히는 곳

| 증상 | 해결 |
|---|---|
| `exit 6: Required Korean font 'NanumGothic'` | `sudo apt install fonts-nanum` 또는 `PAIDEIA_KR_FONT_PATH` 지정 |
| `ImportError: torch` 후 정상 완주 | RoBERTa 미설치 → 폴백 동작(정상). 쓰려면 `uv sync --extra roberta` |
| 매핑 YAML v1 거부 (exit 1) | `mapping_version: 2` + `axes.required` 8축 모두 명시 |
| CSV 한글 깨짐 | `factor_scores_long.csv` 는 UTF-8 BOM. 파일 첫 3바이트 `EF BB BF` 확인 |
| 두 실행 산출 byte-differ | `manifest.json` 의 `font_resolution`·`sentiment.model_sha256`·`seed` 비교 |

---

## 관련 문서

- 다음 단계: [immersio](../immersio/how_to_use_immersio.md) Phase 3 결합 분석
- 회고 환류: [retro-mester](../retro-mester/how_to_use_retro-mester.md)
- 설계 철학: [why_paideia](../why_paideia.md)
</content>
