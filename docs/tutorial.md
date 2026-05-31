# Tutorial — 한 학기를 처음부터 끝까지

이 튜토리얼은 가상의 교과목 **「인체구조와기능」(`2026-1-anatomy`)** 을
예로, paideia 의 개발 완료 모듈 3종을 **학기 시간 순서**대로 돌려본다.

```text
개강    needs-map   사전진단 분석 → 의미축·군집·1인 1장 카드
중간    examen      교재·강의·퀴즈 → 기말 시험 출제 초안
시험후  immersio    시험 결과 → 문항분석·학생 보고서·이메일
학기말  retro-mester (개발 중)
```

> 본 튜토리얼은 [quickstart.md](quickstart.md) 의 설치·폰트 준비가 끝났다고
> 가정한다. 모든 명령은 저장소 루트(`paideia/`)에서 실행한다.

---

## 공통 규약

- 학기-과목 키: `2026-1-anatomy` (= `{semester}-{course}`)
- 데이터 계층: `data/{bronze,silver,gold}/{module}/2026-1-anatomy/`
- 모든 모듈은 **결정론** — 같은 입력 → 같은 산출.
- LLM 은 선택적 가속기 — 없어도 결정론 단계는 완주.

---

## Step 1 — needs-map: 개강 직후 사전진단 분석

학생들이 개강 첫 주에 제출한 사전진단 설문을 분석해 **학습 성향 의미축**,
**군집**, **1인 1장 피드백 카드**를 만든다.

### 1.1 입력 배치

| 입력 | 위치 |
|---|---|
| 진단 응답 Silver | `data/silver/immersio/2026-1-anatomy/diagnostic_response.parquet` |
| 학생 명단 Silver | `data/silver/immersio/2026-1-anatomy/student_master.parquet` |
| 진단 매핑 YAML | `data/bronze/매핑/anatomy.diagnostic.yaml` (`mapping_version: 2`) |

> 진단 응답·학생 명단 Silver 는 `immersio ingest` (Phase 0) 가 설문 CSV·출석부
> 로부터 만든다. Step 3.1 참조.

### 1.2 실행

```bash
uv run --package needs-map paideia-needs-map run \
  --semester 2026-1 \
  --course   anatomy
```

폐쇄망/빠른 실행이면 외부 호출을 끈다:

```bash
uv run --package needs-map paideia-needs-map run \
  --semester 2026-1 --course anatomy --no-llm --no-roberta
```

### 1.3 산출

```text
data/silver/needs-map/2026-1-anatomy/
  scale_reliability.parquet   factor_scores.parquet
  cluster_assignment.parquet  free_text_categorization.parquet
data/gold/needs-map/2026-1-anatomy/
  group_distribution.pdf   cluster_summary.xlsx
  needs-map_manual.pdf     cards/{학번}.pdf      ← 1인 1장 카드
```

`factor_scores.parquet` 와 `cluster_assignment.parquet` 는 **Step 3 immersio
결합 분석(Phase 3)의 입력**이 된다. 흐름이 여기서 이어진다.

➡ 상세 플래그: [how_to_use_needs-map.md](needs-map/how_to_use_needs-map.md)

---

## Step 2 — examen: 기말 시험 출제 초안

교재·강의 녹취(STT)·형성평가·퀴즈를 근거로 기말 출제 초안을 결정론적으로 만든다.

### 2.1 입력 배치 (`data/bronze/examen/2026-1-anatomy/`)

```text
textbooks/8장 호흡계통.txt ...          # 교재 (파일명에 "N장" 필수)
formative/Ch08_FormativeTest.yaml ...   # 형성평가 (선택)
formative/형성평가_실제_출제문제들.txt  # 정확한 파일명 필수
quiz/QuestionUploadExcel_9주차.xls ...  # 퀴즈 (BIFF8 cp949, 선택)
blueprint.yaml                          # 출제사양 (필수)
curriculum_map.yaml                     # 주차→장→절 매핑 (필수)
```

> **파일명 오타 = 즉시 실패(exit 2).** examen 은 silent-skip 을 하지 않는다.

### 2.2 실행

```bash
# 전체 파이프라인 (ingest → plan → generate → verify → 산출)
uv run --package examen examen build \
  --semester 2026-1 --course anatomy

# 또는 단계별로 (디버깅)
uv run --package examen examen ingest  --semester 2026-1 --course anatomy
uv run --package examen examen plan    --semester 2026-1 --course anatomy
uv run --package examen examen dry-run --semester 2026-1 --course anatomy  # LLM 없이 번들만
uv run --package examen examen generate --semester 2026-1 --course anatomy # LLM 호출
uv run --package examen examen verify  --semester 2026-1 --course anatomy
```

### 2.3 산출

```text
data/gold/examen/2026-1-anatomy/runs/{run_id}/
  기말출제초안.xlsx   기말출제초안.yaml
  출제품질리포트.md   manifest_examen.json   ingest_report.json
```

교수자는 `기말출제초안.xlsx` 를 검토·수정하여 실제 시험으로 확정한다.

➡ 상세 플래그·blueprint 스키마: [how_to_use_examen.md](examen/how_to_use_examen.md)

---

## Step 3 — immersio: 시험 후 결과 해석과 환류

시험을 시행한 뒤 OMR 결과를 받아 문항 품질을 분석하고, 학생별 맞춤 보고서를
만들고, 이메일로 발송한다. needs-map 진단과 결합 분석도 한다.

immersio 는 4개 단계(Phase)로 나뉜다.

### 3.1 Phase 0 — ingest (Bronze → Silver)

설문·OMR·출석부·시험문제를 Silver 4종으로 정규화한다.

```bash
uv run --package immersio immersio ingest \
  --bronze-dir data/bronze \
  --mapping    data/bronze/매핑/anatomy.diagnostic.yaml \
  --output-key 2026-1-anatomy
```

산출: `data/silver/immersio/2026-1-anatomy/{student_master, diagnostic_response,
exam_result, exam_item}.parquet`
(이 중 앞 두 개가 **Step 1 needs-map 의 입력**이다.)

### 3.2 Phase 1+2 — analyze (시험 품질 + 학생 지표)

```bash
uv run --package immersio immersio analyze \
  --semester 2026-1 --course anatomy
```

산출(Gold): `시험분석결과.xlsx`(7시트) · `시험품질보고서.{md,pdf}` ·
`figs/fig{1,2}_*.png`

### 3.3 Phase 3 — combine (진단 × 시험 결합)

needs-map(Step 1)의 군집·요인 점수와 시험 결과를 결합해 상관·회귀를 분석한다.

```bash
uv run --package immersio immersio combine \
  --semester 2026-1 --course anatomy \
  --silver-dir data/silver --gold-dir data/gold \
  --include-cluster --include-subgroup
```

산출(Gold): `결합분석보고서.{md,pdf}` · `결합분석.xlsx` ·
`figs/fig{3,4,5,6}_*.png`

### 3.4 Phase 6 — email (학생 맞춤 보고서 발송)

학생별 PDF 를 Gmail API 로 발송한다. **먼저 dry-run**, 그다음 self-test,
마지막에 실제 발송이 안전한 순서다.

```bash
# (1) dry-run — Gmail 호출 0, .eml 미리보기만 생성
uv run immersio email \
  --profile kjeong --semester 2026-1 --course anatomy \
  --exam-name "기말고사"

# (2) self-test — 운영자 본인에게만 5건 발송 (학생 도달 0)
uv run immersio email \
  --profile kjeong --semester 2026-1 --course anatomy \
  --exam-name "기말고사" --self-test 5 --send

# (3) 실제 발송 — 확인 게이트(yes/no) 통과 후 학생에게 발송
uv run immersio email \
  --profile kjeong --semester 2026-1 --course anatomy \
  --exam-name "기말고사" --send
```

> dry-run 은 `*_dryrun.csv/md` 로, 실제 발송은 `*.csv/md` 로 **로그 파일이
> 분리**된다. 발송 로그 오염이 원천 차단된다.

➡ 상세 서브커맨드·이메일 의미론: [how_to_use_immersio.md](immersio/how_to_use_immersio.md)

---

## Step 4 — retro-mester: 학기 회고 (개발 중)

학기가 끝나면 retro-mester 가 needs-map(출발)과 immersio(도착) 데이터를
회고해 **차년도 수업 설계 변경 3~5개**를 우선순위와 함께 제안한다.
아직 개발 중이며, 산출은 다음 해 needs-map 이 인용할 수 있는 형태로 남는다.

➡ [how_to_use_retro-mester.md](retro-mester/how_to_use_retro-mester.md)

---

## 전체 흐름 요약

```text
[설문 CSV·출석부]
   │ immersio ingest (Phase 0)
   ▼
student_master.parquet ─┐
diagnostic_response.parquet ─┤ paideia-needs-map run (Step 1)
   ▼                          ▼
exam_result/exam_item   factor_scores / cluster_assignment
   │ immersio analyze         │
   ▼ (Phase 1+2)              │
시험분석결과.xlsx             │
   │ immersio combine ◀───────┘ (Phase 3: 진단 × 시험)
   ▼
결합분석보고서 → immersio email (Phase 6) → 학생 발송
   │
   ▼ retro-mester (학기말)
차년도 수업 설계 제안 → (다음 학기 needs-map)
```

[examen](examen/how_to_use_examen.md) 은 이 흐름과 병렬로, 중간/기말 시험
**출제 시점**에 교재·강의 자료로부터 문제 초안을 만든다.

---

## 다음에 읽을 것

- 각 모듈 상세: [needs-map](needs-map/how_to_use_needs-map.md) ·
  [examen](examen/how_to_use_examen.md) ·
  [immersio](immersio/how_to_use_immersio.md)
- 설계 철학: [why_paideia.md](why_paideia.md)
</content>
