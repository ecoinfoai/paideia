# examen — 시험 문제 초안 결정론적 출제 paideia 모듈

examen 은 paideia 우산의 **정식 시험(기말) 출제** 모듈이다. 교수자가 선언한
출제사양(`blueprint.yaml`)과 주차→장 매핑(`curriculum_map.yaml`)을 입력으로,
기말 범위 6개 장의 **교재만을 근거**로 객관식 문항 초안(40~50문항)을 형성평가(전수
변환)·퀴즈(약 15 변형)·교과서(채움) 세 출처에서 산출한다. 생성 외 모든 단계는
**결정론 코드**이고 LLM 은 `generate/` 한 곳으로 격리되며(단일 LLM 경계), 산출은
교재 행에 앵커되어 **사람(교수자)이 검토하는 초안 생성기**다. examen 은 한 방향
생성기이며 교수자 편집본을 다시 읽어 병합하지 않는다(FR-020).

## 현재 상태 (v0.1.0)

- US1~US7 구현 완료, **488개 테스트 통과** (contract/integration/unit/property).
- FR-025 의 **강조 기반 슬롯 우선순위(출제 우선순위 반영)는 의도적으로 보류** —
  US7 은 문항 강조 라벨링 + `manifest_examen.json` 의 `emphasis_summary` 기록까지
  수행한다(솔버 안정성 보존).
- **CLI 의 formative/quiz 와이어링은 마무리 중(known gap).** `examen build` 는
  현재 **교과서 경로를 end-to-end** 로 완주한다. 파이프라인 코어
  (`pipeline.build_exam`)는 `formative_inventory`/`quiz_inventory` 인자를 통한
  형성 변환·퀴즈 변형을 이미 지원하지만, `cli/main.py` 의 `build` 핸들러가 아직
  이 두 인벤토리를 주입하지 않는다(별도 task 에서 봉합 중).
- `generate`/`verify` 서브커맨드는 **스텁**이다(blueprint 만 검증하고 "not yet
  implemented" 출력). 실제 end-to-end 실행은 `build` 가 담당한다.

## 파이프라인 개요 (Bronze→Silver→Gold)

```
Bronze (교재·STT·형성·퀴즈·중간고사 레퍼런스)
  │  ingest  ── 교재 클린·청킹, STT 파싱, 출처 대장, 강조 셀, ingest_report  (LLM 0)
  ▼
Silver (교재 청크·근거 인덱스·출처 대장·강조 셀·blueprint 해석·생성요청 번들·LLM 캐시)
  │  plan    ── blueprint solver: 총 문항 수→챕터 균등·난이도·출처 믹스 → 슬롯  (LLM 0)
  │  generate ─ 슬롯→문항 (교과서 신규/형성 변환/퀴즈 변형)  ◀── 단일 LLM 경계
  │  verify  ── groundedness·형식·정답번호 균형·중복·문제검증  (검토만)
  ▼
Gold (기말출제초안.{xlsx,yaml} · 출제품질리포트.md · ingest_report.json · manifest_examen.json)
```

### 7개 사용자 스토리 한눈에

| US | 우선순위 | 한 줄 |
|---|---|---|
| US1 교과서 근거 문항 초안 | P1 (MVP) | 교재만 근거, 5지선다·형식 준수, 전 문항 교재 행 앵커 또는 "미확인" |
| US2 형성평가 전수 변환 | P1 | 형성 12 전수를 객관식으로, **틀린 보기가 정답**(부정형 발문) |
| US3 퀴즈 변형 + 균형 | P2 | 퀴즈 ≈15 변형(토큰 자카드 0<J<0.8), 챕터 균등·난이도 45/35/20 달성 |
| US4 메타데이터·산출·검토 | P2 | 28컬럼 xlsx + 중첩 yaml, 채택상태(생성/교수수정/채택/제외) 추적 |
| US5 출제 품질 리포트 | P3 | 목표 대비 실측(챕터/난이도/출처/정답번호) `출제품질리포트.md` |
| US6 문항 자동 재검토 | P3 | review agent 가 문제검증 컬럼 채움(최초 공백) |
| US7 강의 강조 enrichment | P3 | STT→절별 4분반 교집합 강조 라벨, 없어도 Core 완주(degrade) |

자세한 사양: `specs/008-examen-question-gen/{spec,plan,data-model,quickstart}.md`.

## CLI 사용법

진입점: `examen = "examen.cli.main:app"`. 모든 명령은 `--semester`·`--course` 로
데이터 디렉터리(`data/{layer}/examen/{semester}-{course}/`)를 결정한다.

```bash
# 전체 파이프라인 한 번에 (실제 end-to-end 명령 — 현재 교과서 경로 완주)
paideia examen build --semester 2026-1학기 --course 인체구조와기능

# 자주 쓰는 옵션
paideia examen build \
  --semester 2026-1학기 --course 인체구조와기능 \
  --blueprint      data/bronze/examen/2026-1학기-인체구조와기능/blueprint.yaml \
  --curriculum-map data/bronze/examen/2026-1학기-인체구조와기능/curriculum_map.yaml \
  --backend subscription \   # subscription(기본) | api
  --stt data/stt \           # 강조 STT 디렉터리 (미지정 시 규약 경로 자동 탐색)
  --no-emphasis              # 강조 무시(degrade 강제)
```

| 서브커맨드 | 역할 | 상태 |
|---|---|---|
| `ingest` | Bronze→Silver: 교재 클린·청킹, STT 파싱, 출처 대장, ingest_report (LLM 0) | 스텁 (blueprint 검증) |
| `plan` | blueprint solver → 슬롯 목록 (LLM 0) | 스텁 (blueprint 검증) |
| `dry-run` | 슬롯별 생성요청 번들만 산출, LLM 미호출 (헌장 I 결정론 검증) | 스텁 (blueprint 검증) |
| `generate` | 번들→문항 생성 (LLM) | 스텁 (blueprint 검증) |
| `verify` | groundedness·형식·정답번호 균형·중복·문제검증 | 스텁 (blueprint 검증) |
| **`build`** | **전체 파이프라인 + Gold 산출 (구현됨, end-to-end)** | **구현 (교과서 경로)** |

공통 옵션: `--semester`(필수) · `--course`(필수) · `--blueprint PATH` ·
`--curriculum-map PATH` · `--backend {subscription,api}` · `--no-emphasis`.
`build` 는 추가로 `--stt PATH` 를 받는다.

종료 코드(immersio 규약 계승): `0` 성공 · `2` 입력/설정 검증 실패(필수 입력·교재
결측·blueprint 범위 위반) · `3` 생성/검증 단계 실패 · `4` LLM 백엔드 도달
실패(api 모드).

입력 디렉터리 규약과 현재 `data/` → 정규 Bronze 이전은
[`docs/bronze_layout.md`](docs/bronze_layout.md), 실행 흐름은
[`specs/008-examen-question-gen/quickstart.md`](../../specs/008-examen-question-gen/quickstart.md)
참조.

## 테스트 실행

NixOS + nix-ld + uv 환경에서 pandas/xlrd 네이티브 의존 때문에 LD_LIBRARY_PATH 주입이
필요하다(캐노니컬 래퍼):

```bash
nix develop --command bash -c 'export LD_LIBRARY_PATH=/run/current-system/sw/share/nix-ld/lib${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}; uv run --package examen pytest modules/examen -q'
```

`ruff check modules/examen` 으로 린트한다.

## 결정성 + LLM 백엔드 모드

- **결정성:** 같은 Bronze + 같은 설정 → **byte-identical Gold**(SC-009). 생성만
  LLM 이지만 **입력해시 캐시**로 재호출을 막아 재실행 산출이 동일하다. openpyxl
  `<dcterms:modified>` 후처리 · yaml `sort_keys`/`allow_unicode` 고정 · parquet
  `use_dictionary=False`/`write_statistics=False` 로 byte 결정성을 보장한다.
- **LLM 백엔드 (`--backend`):**
  - `subscription` (기본) — Claude Code 세션 내 생성. examen 이 Silver 의
    `staging/` 에 생성요청 번들을 쓰고 `responses/` 에서 응답을 읽는다. **토큰 과금 0.**
  - `api` — anthropic SDK(temp=0) 직접 호출. 자동화용, 키는 agenix 로 주입.
    백엔드 도달 실패 시 exit 4.
- **dry-run / 사람 폴백:** LLM 미가용 시에도 ingest~plan~생성요청 번들까지 결정론적으로
  완주한다(헌장 1.2.0 생성 모듈 단서의 "사람 폴백").

## 산출물 (Gold)

`data/gold/examen/{semester}-{course}/` (quickstart §3, contracts/exam_draft_outputs.md):

- **`기말출제초안.xlsx`** — 검토용 평탄화 28컬럼(번호·출처·챕터·난이도·문제·보기1~5·
  정답·오답/도약설명·교재근거위치·출제의도·채택상태 등). 교수자가 여기서 가감·채택상태 표기.
- **`기말출제초안.yaml`** — 중첩 완전판(보기별오답근거 list[5]·교재근거위치 객체·강조 분반수).
  엑셀과 항상 함께·동일 내용(SC-010).
- **`출제품질리포트.md`** — 목표 대비 실측(챕터별 수·난이도 비율·출처 비율·정답번호 분포).
- **`manifest_examen.json`** — 입력 해시·설정 식별자·LLM 백엔드·생성시각·소스/난이도/챕터
  breakdown·`emphasis_summary`. 사후 추적(헌장 V).
- **`ingest_report.json`** — STT/형성/퀴즈/교재 적재 이상 명시(조용한 누락 금지, FR-024).

### immersio ExamItem 투영 seam

`ExamItemDraft` → immersio `ExamItem`(item_no·chapter·source·expected_difficulty·
answer_key·text·distractors·bloom) 투영으로 출제→분석 루프를 닫는다(FR-018,
`output/exam_item_projection.py`). 보기별오답근거·강조 분반수(0~4)는 하류 immersio 의
오개념 분석·강조 강도 소비를 위한 seam 으로 보존된다.
