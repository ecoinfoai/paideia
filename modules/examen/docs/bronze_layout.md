# Bronze 레이아웃 규약 — examen (T059)

examen 의 Bronze 입력 디렉터리 규약과, **현재 흩어진 `data/` 레이아웃**에서
**정규 `data/bronze/examen/{semester}-{course}/` 레이아웃**으로의 이전(migration)을
정의한다.

> **이 문서는 규약(convention) 문서다.** 실제 파일 이동은 운영자가 한 번 수행하는
> 수동/ops 단계이며, examen 이 런타임에 자동으로 옮기지 않는다. examen 은 정규
> Bronze 경로(`data/bronze/examen/{semester}-{course}/`)에 입력이 정렬돼 있다고
>가정하고 읽는다. (현재 `examen build` 는 STT 와 일부 경로에 한해 구(舊) `data/`
> 위치 fallback 을 둔 상태 — README 의 "알려진 갭" 참조.)

근거: `specs/008-examen-question-gen/quickstart.md` §1, `plan.md` Structure Decision,
contracts/{blueprint_yaml,curriculum_map_yaml,source_inventory,manifest_examen}.md.

---

## 1. 정규 타깃 레이아웃

```text
data/bronze/examen/{semester}-{course}/        # 예: 2026-1학기-인체구조와기능
├── textbooks/            ← 원본 교재 (groundedness 권위 — 원본 행 앵커)
├── txt_summary/          ← 절단위 교재 요약 (Silver 편의 보조, LLM 파생 — 권위 아님)
├── stt/                  ← 9~13(+14)주차 강의 녹취/녹취 요약 (강조용 enrichment, degrade-safe)
├── formative/            ← Ch*_FormativeTest.yaml + 형성평가_실제_출제문제들.txt
├── quiz/                 ← QuestionUploadExcel_{week}주차.xls
├── blueprint.yaml        ← 출제사양 (총 문항 수·챕터·난이도 목표·출처 믹스)
├── curriculum_map.yaml   ← 주차→장→절 매핑
└── quiz_column_map.yaml  ← 퀴즈 .xls 컬럼 매핑 (BIFF8 cp949)
```

- `{semester}` = `SemesterCode` (예: `2026-1학기`), `{course}` = `CourseSlug`
  (예: `인체구조와기능`). 디렉터리 이름은 `{semester}-{course}` 로 결합한다.
- 설정 3종(`blueprint.yaml`·`curriculum_map.yaml`·`quiz_column_map.yaml`)이
  변동성을 모두 흡수한다(헌장 III). 챕터명·분반 라벨·파일명·시트명을 코드에
  하드코딩하지 않는다.
- `quiz_column_map.yaml` 의 표준 사본은 `modules/examen/templates/quiz_column_map.yaml`
  에 있다(퀴즈 컬럼 의미 매핑의 출처).

---

## 2. 현재 → 정규 Bronze 매핑 표

현재 `data/` 아래에 흩어진 입력 디렉터리를 정규 Bronze 서브디렉터리로 옮기는 대응표.

| 현재 위치 (`data/...`) | 정규 Bronze 서브디렉터리 | 권위/역할 | 비고 |
|---|---|---|---|
| `data/textbooks/` | `.../textbooks/` | **groundedness 권위** | 원본 교재. 모든 근거 앵커의 출처 |
| `data/txt_summary/` | `.../txt_summary/` | Silver 편의 보조 | LLM 파생 요약 — **권위 아님** |
| `data/stt/` | `.../stt/` | enrichment (강조 신호) | 없어도 Core 완주(degrade-safe) |
| `data/formative-analysis/` | `.../formative/` | 고정 입력 (형성 전수 변환) | `Ch*_FormativeTest.yaml` + 실제 출제 목록 txt |
| `data/quiz_w9_w13/` | `.../quiz/` | 고정 입력 (퀴즈 ≈15 변형) | `QuestionUploadExcel_{week}주차.xls` (BIFF8 cp949) |
| `data/midterm_exams/` | (이전 안 함 — **reference-only**) | 출력 형식/스타일 few-shot | 중간고사 산출물. 입력 출처 아님 |

### midterm_exams 는 왜 reference-only 인가

`data/midterm_exams/` 는 출제 *입력*이 아니라 **출력 형식·스타일의 레퍼런스**다.
문항 스키마(`ExamItemDraft`)는 `실제_출제문제.yaml` 의 필드를 계승·확장하고,
중간고사를 출력 형식/스타일의 few-shot 으로 사용한다(spec Assumptions
"중간고사 산출물 계승"). 따라서 Bronze 입력 디렉터리로 옮기지 않으며, examen 의
groundedness/변환 근거로도 쓰지 않는다.

### 현재 실측 입력 (2026-1학기 인체구조와기능)

| 디렉터리 | 실측 |
|---|---|
| `data/textbooks/` | `8장 호흡계통.txt` · `9장 근육계통.txt` · `10장 내분비계통.txt` · `11장 비뇨계통.txt` · `13장 신경계통.txt` · `14장 감각계통.txt` (기말 범위 6장) |
| `data/txt_summary/` | `Ch01..Ch14_*_Summary_KR.md` (14장 전체 요약, LLM 파생) |
| `data/stt/` | `9주차`~`13주차/` 하위에 `{분반}_{주차}_{차시}.txt` (분반 1A~1D) |
| `data/formative-analysis/` | `Ch08..Ch12_*_FormativeTest.{yaml,xlsx}` |
| `data/quiz_w9_w13/` | `QuestionUploadExcel_{9..13}주차.xls` |
| `data/midterm_exams/` | 중간고사 산출물 일습 (yaml·docx·xlsx·hwp 등) — reference-only |

---

## 3. 권위 규칙 (authority rule)

세 텍스트 출처는 권위 등급이 다르다. 이 구분이 groundedness 검증의 핵심이다.

1. **`textbooks/` = groundedness 권위.** 모든 문항은 원본 교재의 *파일·행*에
   앵커돼야 한다(FR-002/FR-003). 교재에서 직접 확인되지 않으면 "미확인"으로
   표기하고 무단 채택을 막는다(FR-003, SC-005). 근거 앵커는 항상 원본 교재의
   행 번호를 가리킨다(요약본이 아니다).

2. **`txt_summary/` = Silver 편의 보조 (권위 아님).** 절단위 요약은 LLM 파생
   산출물로, 생성 컨텍스트를 좁히는 *편의*일 뿐이다. groundedness 의 권위는
   원본 교재가 갖는다(spec Assumptions "교재 요약의 위치"). 요약과 원본이
   충돌하면 **원본이 이긴다.**

3. **`stt/` = enrichment 전용 (degrade-safe).** 강의 녹취는 절 단위 *강조 신호*만
   제공한다(US7). 출제 범위를 거르거나 줄이지 않으며, 강조 자료가 없거나 일부
   차시가 결측이어도 Core 출제는 100% 완주해야 한다(FR-026, SC-013). `--no-emphasis`
   또는 STT 디렉터리 부재 시 강조여부는 교재 기반 기본값으로 degrade 된다.

---

## 4. 알려진 입력 함정 (input traps)

ingest 단계는 이 이상들을 **조용히 누락하지 않고** `ingest_report.json` 에 명시한다
(FR-024). 필수 입력 결측은 실패(exit 2), 비필수(STT 등) 결측은 경고로 기록한다.

- **STT `1C_11주차_2차시` 실측 결측.** 1C 분반 11주차 2차시 녹취가 실제로 없다
  (`data/stt/11주차/` 확인 — 1C 는 1차시만 존재). ingest_report 의
  `stt.missing` 에 기록되고, 강조 집계에서 해당 차시는 제외되어 "강조 안 함"으로
  오판되지 않는다(FR-025). enrichment 이므로 degrade — 실패 아님.

- **12장(생식·발생) 진도 생략.** 12장은 기말 범위 밖이다(`blueprint.chapters`
  6장에 미포함, `curriculum_map.yaml` 에도 미등록). `data/formative-analysis/`
  에 `Ch12_*_FormativeTest.*` 와 `data/txt_summary/Ch12_*` 가 존재하지만 출제
  범위가 아니므로 사용하지 않는다. (txt_summary 는 14장 전체를 담지만 범위는
  blueprint/curriculum_map 이 결정한다.)

- **주차→장 비(非) 1:1.** 한 장이 복수 주차에 걸치고(9장 = 10·11주차: 생리/명칭),
  한 주차가 복수 장을 담는다(14주차 = 13·14장). 1:1 이 아니므로
  `curriculum_map.yaml` 이 명시적으로 선언한다. 형성/퀴즈 원본의 장 귀속과 STT
  강조의 절 정렬이 이 매핑을 따른다.

---

## 5. 산출 위치 (참고)

Bronze 입력으로 examen 이 내는 산출물 위치(quickstart §3):

```text
data/silver/examen/{semester}-{course}/   # 교재 청크·근거 인덱스·출처 대장·강조 셀·생성요청 번들·LLM 응답 캐시
data/gold/examen/{semester}-{course}/
├── 기말출제초안.xlsx       # 검토용(28컬럼)
├── 기말출제초안.yaml       # 완전판(보기별근거·근거위치 중첩)
├── 출제품질리포트.md       # 목표 대비 실측
├── ingest_report.json      # 적재 이상 명시(STT 결측 등)
└── manifest_examen.json    # 입력 해시·설정 식별자·LLM 백엔드 추적
```

같은 Bronze + 같은 설정 → byte-identical Gold(캐시). `manifest_examen.json` 의
`input_hashes`·`config_ids`·`llm_backend` 로 사후 추적한다(헌장 V).
