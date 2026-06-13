# maieutica — 교재 기반 주차별 퀴즈·형성평가 후보 생성

maieutica 는 교수자가 선언한 챕터 교재 텍스트만을 근거로 주차별 객관식 퀴즈·서술형 형성평가 후보를 결정론적으로 생성하고, 맞힌 학생을 다음 개념으로 끌어올리는 **도약 설명(leap explanation)** 을 함께 산출하는 paideia 모듈이다.

산출물은 대학 LMS 불변 포맷(`.xls`/`.xlsx`)을 따르며, examen 의 상류 입력(seam)이 된다.

---

## 핵심 속성

| 속성 | 내용 |
|------|------|
| 교재 근거 전용 | 모든 후보는 챕터 `.txt` 내용에만 앵커; 외부 배경지식 차단 (FR-002) |
| 도약 설명 | 오답 설명 + 맞힌 학생용 "한 걸음 더" 도약을 `답안설명` 컬럼에 결합 (FR-013) |
| LMS 불변 포맷 | 퀴즈 `.xls` (안내 시트 + 11컬럼), 형성평가 `.xlsx` (14컬럼) — 변환 없이 LMS 업로드 (FR-005/FR-006) |
| 결정론 | 같은 입력 → byte-identical 산출 (manifest `generated_at` 제외, SC-009) |
| 부분 산출 금지 | 검증 통과 전 Gold 미작성; 오류 시 전체 롤백 (FR-020) |
| examen seam | Gold 산출이 주차·챕터·원본 식별자를 포함해 examen 이 추가 변환 없이 소비 가능 (FR-024) |
| 발송 없음 | maieutica 는 산출을 학생에게 자동 발송하지 않음 (FR-025) |

### v0.1.1 — 챕터 내 다양성·정답 균형 (010-maieutica-quiz-diversity)

한 챕터에서 N개 퀴즈 후보를 생성할 때 같은 문항이 반복되거나 정답이 한 번호로 쏠리던
v0.1.0 결함을 해소한다. 공개 계약(CLI 인자·LMS 포맷·`QuizItemCandidate` 형태)은 무변경
(FR-013). 버전 0.1.0 → 0.1.1.

| 속성 | 내용 |
|------|------|
| 챕터 내 다양성 | 챕터를 다층 소절(`N.`/`N)`/`(N)`/`가)`/`①`/`N.M` + 과대 문단 보조 분할)로 나누고, 길이 비례로 슬롯을 소절에 배정(소절당 ≤3). 각 슬롯은 귀속 소절만 컨텍스트로 + 같은 소절 회피 목록으로 생성해 후보가 서로 다르다 (FR-001/002/003/004, SC-001/002) |
| 중복 제거 | 정답 근거 교재 앵커 `(chunk_id, line)` 가 같으면 중복으로 판정해 제거 (FR-008, SC-001) |
| 정답 균형 | 채택 세트의 정답번호를 재배치해 동일 번호 3연속 없음 + 어떤 번호도 ≤50%. 보기 순번 표기(①~⑤)는 위치 순서 유지. `.xls` 를 정답 수작업 재배치 없이 업로드 가능 (FR-006/007, SC-003) |
| 소절 앵커 근거 | 각 채택 후보의 `textbook_evidence` 가 챕터 전체가 아닌 귀속 소절 범위 안 정답 근거를 앵커. 정답 근거를 원문에서 확인 못 한 후보는 채택에서 **제외**(미확인 0) (FR-009/010, SC-005) |
| 부족분 보고 | 소절 용량·중복 제거·미확인 제외로 N 을 못 채우면 `출제품질리포트.md` 에 요청-vs-산출·소절 분산·부족분 사유(합 = N−M)를 명시. 침묵 누락 없음 (FR-015) |
| 편집 없이 업로드 | 중복 0·정답 균형·확인 앵커 동시 충족으로 강제 편집 0건 (SC-006) |

---

## CLI 서브커맨드

모든 서브커맨드의 공통 옵션:

```
--semester SEMESTER      (필수) 학기 코드 (예: "2026-1")
--course COURSE          (필수) 과목 슬러그 (예: "anatomy-physiology")
--week WEEK              (필수) 대상 주차 (정수)
--generation-spec PATH   생성사양 YAML (미지정 시 bronze 규약 경로 사용)
--curriculum-map PATH    주차→챕터 매핑 YAML (미지정 시 bronze 규약 경로 사용)
--quiz-count N           퀴즈 후보 수 재정의 (선택; 기본 generation_spec 값 사용; 1..20, 범위 밖이면 exit 2 — FR-005)
--formative-count M      형성 후보 수 재정의 (선택; 기본 generation_spec 값 사용)
--backend {subscription,api}  LLM 백엔드 (기본: subscription)
```

### 종료 코드

| 코드 | 의미 |
|------|------|
| 0 | 성공 |
| 2 | 입력/설정 검증 실패 (필수 파일 결측, 스키마 오류, 주차→챕터 매핑 결측) |
| 3 | 생성/검증 단계 실패 (SubscriptionBackend 응답 파일 결측 포함) |
| 4 | LLM 백엔드 도달 실패 (api 모드 전용) |

### `ingest`

Bronze → Silver: 챕터 교재 텍스트 클리닝·청킹·근거 인덱스 산출. LLM 호출 없음.

```bash
maieutica ingest --semester 2026-1 --course anatomy-physiology --week 9
```

산출: `data/silver/maieutica/{semester}-{course}/ingest_report.json`

### `plan`

생성사양 → 슬롯 목록 (N 퀴즈 + M 형성). LLM 호출 없음.

```bash
maieutica plan --semester 2026-1 --course anatomy-physiology --week 9
```

### `dry-run`

슬롯별 생성요청 번들만 산출(LLM 미호출). 결정론 단계 완주 검증 + 사람 폴백용 작업지 산출.

```bash
maieutica dry-run --semester 2026-1 --course anatomy-physiology --week 9
```

산출: `data/silver/maieutica/{semester}-{course}/staging/quiz-{week}-001..N.json`,
`formative-{chapter_no}-001..M.json`

### `generate`

번들 → 문항 생성 (LLM 호출). 결과는 Silver responses 에 캐시.

```bash
maieutica generate --semester 2026-1 --course anatomy-physiology --week 9 --backend subscription
```

### `verify`

기존 build 의 run yaml 을 읽어 자동 2차 재검토 수행 후 yaml 덮어쓰기.

```bash
maieutica verify --semester 2026-1 --course anatomy-physiology --week 9
```

run yaml 이 없으면 exit 2 (`build` 먼저 필요).

### `build`

전체 파이프라인 (ingest → plan → generate → verify → assemble → Gold 산출).

```bash
maieutica build --semester 2026-1 --course anatomy-physiology --week 9 --backend subscription
```

---

## 데이터 레이아웃

### Bronze (입력)

```
data/bronze/maieutica/{semester}-{course}/
├── generation_spec.yaml        # 생성사양 (주차, 챕터, 퀴즈 수, 형성 수)
├── curriculum_map.yaml         # 주차→챕터 매핑
└── {chapter_no}장_{chapter}.txt  # 챕터 교재 텍스트 (원본)
```

### Silver (중간)

```
data/silver/maieutica/{semester}-{course}/
├── ingest_report.json          # Bronze 인제스트 결과 리포트
├── staging/                    # dry-run 번들 JSON (슬롯별)
│   ├── quiz-{week}-001.json
│   └── formative-{chapter_no}-001.json
├── responses/                  # subscription 백엔드 응답 캐시
│   └── {slot_id}.json
└── cache/                      # 입력 해시 기반 LLM 응답 캐시
```

### Gold (산출)

```
data/gold/maieutica/{semester}-{course}/
└── runs/{run_id}/
    ├── QuestionUploadExcel_{week}주차.xls    # LMS 퀴즈 업로드 양식
    ├── Ch{NN}_{chapter}_FormativeTest.xlsx  # LMS 형성평가 양식
    ├── 출제후보_완전판.yaml                   # 중첩 완전판 (도약 원문·보기별 근거 포함)
    ├── 출제품질리포트.md                      # 자동 품질 리포트 (v0.1.1: 요청 vs 산출·소절 분산·부족분 사유 섹션 포함, FR-015)
    └── manifest_maieutica.json              # 입력 식별자·해시→산출 추적 (SC-012)
```

`run_id` 는 `generation_spec.yaml`, `curriculum_map.yaml`, 챕터 `.txt` 세 파일의 내용 해시로 결정론적으로 산출된다. 같은 입력이면 항상 같은 `run_id` 가 되어 재실행이 멱등(idempotent)이다.

---

## 결정론 메모

- `QuestionUploadExcel_*.xls`, `Ch*_FormativeTest.xlsx`, `출제후보_완전판.yaml`, `출제품질리포트.md` 는 동일 입력 재실행 시 byte-identical.
- `manifest_maieutica.json` 의 `generated_at` 필드만 비결정론적 (실행 시각 기록).
- xlsx 결정론: openpyxl `<dcterms:modified>/<dcterms:created>` core.xml 후처리로 타임스탬프 고정.
- yaml 결정론: `sort_keys=True` 직렬화.
- xls 결정론: xlwt 단일 공유 스타일 객체.

---

## devShell 실행 명령

NixOS + nix-ld + uv 워크스페이스 환경에서 네이티브 의존(xlwt·xlrd·openpyxl) 때문에 devShell 필수. 표준 실행 명령([[test-run-command]]):

```bash
nix develop --command bash -c \
  'export LD_LIBRARY_PATH=/run/current-system/sw/share/nix-ld/lib${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}; \
   uv run --package maieutica <cmd>'
```

테스트:

```bash
nix develop --command bash -c \
  'export LD_LIBRARY_PATH=/run/current-system/sw/share/nix-ld/lib${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}; \
   uv run --package maieutica pytest modules/maieutica -q'
```

---

## 참조

- 검증 시나리오 (Quickstart): [`specs/009-maieutica-question-gen/quickstart.md`](../../../specs/009-maieutica-question-gen/quickstart.md)
- 기능 명세: [`specs/009-maieutica-question-gen/spec.md`](../../../specs/009-maieutica-question-gen/spec.md)
- 계약: [`specs/009-maieutica-question-gen/contracts/`](../../../specs/009-maieutica-question-gen/contracts/)
- examen 연계: [`modules/examen/`](../../examen/) — maieutica Gold 가 examen 의 Bronze 입력이 됨
