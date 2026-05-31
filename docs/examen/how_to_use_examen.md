# how_to_use_examen

> **examen v0.1.0** — 시험 문제 초안 결정론적 출제 모듈.
> (라틴어 *examen*: 저울의 바늘 → 무게를 달다·시험. "exam"의 어원. 구 명칭 `gen-test`)
> 교재·강의 녹취(STT)·형성평가·퀴즈를 근거로 **기말 출제 초안**을 만든다.

수치·매칭·룰 단계는 전부 결정론 코드로 처리하고, 문항 생성만 LLM 을
선택적으로 쓴다. **외부 LLM 에 도달하지 못해도 결정론 단계는 끝까지 완주**한다.

---

## 1. 한눈에

```bash
uv run --package examen examen build \
  --semester 2026-1 \
  --course   anatomy
```

- 콘솔 스크립트: **`examen`**
- 서브커맨드: `ingest` · `plan` · `dry-run` · `generate` · `verify` · `build`
- 입력: `data/bronze/examen/{semester}-{course}/`
- 산출: `data/gold/examen/{semester}-{course}/runs/{run_id}/`

---

## 2. 서브커맨드

| 커맨드 | 단계 | LLM | 설명 |
|---|---|---|---|
| `ingest` | Bronze→Silver | ✗ | 교재·STT·형성·퀴즈 적재 + 강조 집계 |
| `plan` | 계획 | ✗ | blueprint solver → 슬롯 배분 |
| `dry-run` | 번들 | ✗ | 생성요청 번들만 산출 (헌장 검증) |
| `generate` | 생성 | ✓ | 번들 → 문항 생성 (캐시) |
| `verify` | 검증 | ✗ | format·groundedness·정답 균형 |
| `build` | 전체 | ✓ | ingest→plan→generate→verify→출력 |

### 공통 옵션

| 옵션 | 필수 | 기본값 |
|---|---|---|
| `--semester` | ✅ | — (예: `2026-1`) |
| `--course` | ✅ | — (예: `anatomy`) |
| `--blueprint` | — | `data/bronze/examen/{sem}-{course}/blueprint.yaml` |
| `--curriculum-map` | — | `data/bronze/examen/{sem}-{course}/curriculum_map.yaml` |
| `--backend` | — | `subscription` (또는 `api`) |
| `--no-emphasis` | — | off (강조 자료 무시 — degrade 테스트) |

### `build` 전용

| 옵션 | 기본값 | 의미 |
|---|---|---|
| `--stt` | `data/stt` (존재 시) | 강의 녹취 STT 디렉터리 |

**백엔드**:
- `subscription` — Claude Code 세션 경유 (env 불필요). 번들을 staging 에 쓰고 응답을 읽음.
- `api` — Anthropic SDK 직접 호출 (`ANTHROPIC_API_KEY` 필요, temp=0).

---

## 3. 입력 (Bronze 배치)

```text
data/bronze/examen/{semester}-{course}/
├── textbooks/                  # 교재 .txt — 파일명에 "N장" 필수
│   ├── 8장 호흡계통.txt
│   └── 9장 근육계통.txt ...
├── formative/                  # 형성평가 (source_mix.formative>0 시 필수)
│   ├── Ch08_FormativeTest.yaml # glob: Ch*_FormativeTest.yaml
│   └── 형성평가_실제_출제문제들.txt   # ★ 정확한 파일명 필수
├── quiz/                       # 퀴즈 (source_mix.quiz>0 시 필수)
│   └── QuestionUploadExcel_9주차.xls  # BIFF8 cp949, xlrd 로 읽음
├── blueprint.yaml              # ★ 필수 — 출제사양
└── curriculum_map.yaml         # ★ 필수 — 주차→장→절 매핑
```

STT(선택)는 `data/stt/{분반}_{주차}_{차시}.txt` (예: `1C_9주차_1차시.txt`).
일부 결측은 경고만(강조 비활성), 실패 아님.

### blueprint.yaml

```yaml
semester: "2026-1"
course_slug: "anatomy"
exam_name: "2026-1학기 기말고사"
total_items: 48                 # [40, 50] 범위 — 벗어나면 exit 2
chapters:                       # curriculum_map 과 장 이름 일치 필수
  - "8장. 호흡계통"
  - "9장. 근육계통"
difficulty_targets:             # 합 ≈ 1.0
  easy: 0.45
  medium: 0.35
  hard: 0.20
source_mix:                     # 합 = total_items, formative 는 정확 일치
  formative: 12
  quiz: 15
  textbook: 21
answer_key_balance: true        # 정답번호 1~5 균등 + 연속 ≤2
```

### curriculum_map.yaml

```yaml
semester: "2026-1"
course_slug: "anatomy"
entries:
  - week: 9
    chapter_no: 8
    chapter: "8장. 호흡계통"
    sections: ["호흡기의 구조와 기능", "호흡운동", "가스교환과 운반"]
```

> **파일명 오타 = silent-skip 이 아니라 즉시 실패(exit 2).**
> 교재 `호흡계통.txt`(장 번호 없음), 형성 `형성평가_실제문제.txt`(오타),
> 퀴즈 `9주차_퀴즈.xls`(패턴 불일치) 등은 모두 미인식.

---

## 4. 파이프라인

```text
[1] INGEST (결정론)  교재 클린·청킹·EvidenceIndex / 형성·퀴즈 파싱 / STT 강조 집계
                     → ingest_report.json
[2] PLAN (결정론)    blueprint solver → 슬롯 배분 (greedy) + curriculum_map 결합
[3] GENERATE (LLM)   형성→보기 생성 / 퀴즈→변형 / 교재→신규. SHA256 캐시
[4] VERIFY (결정론)  groundedness 앵커 / 보기 글자수 / 중복 / 설명 길이 / 정답 균형
[5] OUTPUT (결정론)  xlsx·yaml·manifest·품질리포트 (atomic write)
```

**캐시**: `data/silver/examen/{semester}-{course}/cache/{sha256}.json`.
캐시 적중 시 LLM 미호출 → 재실행 byte-identical.

---

## 5. 산출 (`data/gold/examen/{semester}-{course}/runs/{run_id}/`)

`run_id` = 입력 번들 SHA-256 앞 16자 (동일 입력 → 동일 경로, idempotent).

| 파일 | 내용 |
|---|---|
| `기말출제초안.xlsx` | 검토용 평탄화 (28컬럼: 번호·출처·챕터·난이도·문제·보기1~5·정답·근거 등) |
| `기말출제초안.yaml` | 완전판 (중첩, 보기별 오답근거·교재근거 위치 포함) |
| `출제품질리포트.md` | 목표 대비 실측 (챕터·난이도·정답번호·근거 분포) |
| `manifest_examen.json` | 입력 해시·캐시율·백엔드·분포 통계 |
| `ingest_report.json` | STT/형성/퀴즈/교재 적재 결과 |

---

## 6. 사용 예시

```bash
# 전체 한 번에 (권장)
uv run --package examen examen build --semester 2026-1 --course anatomy --stt data/stt

# 단계별 디버깅
uv run --package examen examen ingest  --semester 2026-1 --course anatomy
uv run --package examen examen plan    --semester 2026-1 --course anatomy
uv run --package examen examen dry-run --semester 2026-1 --course anatomy   # LLM 없이
uv run --package examen examen generate --semester 2026-1 --course anatomy
uv run --package examen examen verify  --semester 2026-1 --course anatomy

# API 백엔드 (캐시 히트 시 고속)
uv run --package examen examen build --semester 2026-1 --course anatomy --backend api

# 캐시 리셋
rm -rf data/silver/examen/2026-1-anatomy/cache/
```

---

## 7. 종료 코드

| 코드 | 조건 |
|---|---|
| 0 | 성공 |
| 2 | 입력/설정 검증 실패 (필수 결측, blueprint 범위 위반, 교재 파일 없음) |
| 3 | 생성/검증 실패 (subscription 응답 미제공, LLM 오류) |
| 4 | LLM 백엔드 도달 실패 (`--backend api` 전용) |

---

## 8. 자주 막히는 곳

| 증상 | 원인 | 해결 |
|---|---|---|
| `FileNotFoundError` (exit 2) | 교재/형성/퀴즈 파일명 오타·결측 | 파일명 규약 재확인 (§3) |
| blueprint 거부 (exit 2) | `total_items` ∉ [40,50] 또는 `source_mix.formative` ≠ 실제 형성 수 | blueprint.yaml 수정 |
| generate 멈춤 (exit 3/4) | subscription 응답 미제공 / API 키 없음 | 번들 응답 생성 또는 `ANTHROPIC_API_KEY` 설정 |
| 퀴즈 안 읽힘 | `.xlsx`/잘못된 인코딩 | BIFF8 `.xls` + cp949 필수 |
| 강조 미적용 | STT 결측 또는 `--no-emphasis` | `--stt data/stt` 로 경로 지정 |

---

## 관련 문서

- 선행 진단: [needs-map](../needs-map/how_to_use_needs-map.md)
- 시험 후 분석: [immersio](../immersio/how_to_use_immersio.md)
- 설계 철학: [why_paideia](../why_paideia.md)
</content>
