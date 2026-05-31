# how_to_use_immersio

> **immersio v0.1.x** — 시험 결과 해석 + 학생 맞춤형 보고서 생성 모듈.
> (라틴어 *immersio*: 몰입)
> OMR·성적을 받아 문항 품질을 분석하고, needs-map 진단과 결합 분석하며,
> 학생별 맞춤 보고서를 만들어 이메일로 발송한다.

paideia 의 결과 해석 모듈로, 한 학기에 여러 **Phase** 로 나누어 실행한다.
모든 통계·라벨·카드는 결정론 코드, 코칭 멘트 자연어화만 LLM 옵션이다.

---

## 1. 한눈에

```bash
uv run --package immersio immersio <subcommand> [옵션]
```

- 콘솔 스크립트: **`immersio`**
- 서브커맨드: `ingest` · `analyze` · `combine` · `email`
  (보조: `email-init-test-fixtures` · `email-cleanup-log`)
- 데이터 키: `{semester}-{course}` (예: `2026-1-anatomy`)

| Phase | 커맨드 | 역할 |
|---|---|---|
| 0 | `ingest` | Bronze → Silver 4종 |
| 1+2 | `analyze` | 시험 품질 분석 + 학생 지표 + 보고서 |
| 3 | `combine` | needs-map × 시험 결합 분석 |
| 6 | `email` | 학생 맞춤 PDF 발송 |

---

## 2. `ingest` — Phase 0 (Bronze → Silver)

설문·OMR·출석부·시험문제를 파싱·검증·통합한다.

```bash
uv run --package immersio immersio ingest \
  --bronze-dir data/bronze \
  --mapping    data/bronze/매핑/anatomy.diagnostic.yaml \
  --output-key 2026-1-anatomy
```

| 플래그 | 필수 | 기본값 |
|---|---|---|
| `--bronze-dir` | ✅ | — (`진단평가/`·`시험성적/`·`출석/`·`시험문제/`·`매핑/` 포함) |
| `--mapping` | ✅ | — 진단 매핑 YAML |
| `--exam-yaml` | — | 시험문제/ 자동 감지 |
| `--output-key` | — | `{semester}-{course}` |
| `--output-dir` | — | `data/silver/immersio/` |
| `--exam-result-pattern` | — | `*_{section}반*결과.xls(x)` (제외 토큰: `(OX)`,`(문항분석)`,`결시`) |
| `--no-git-commit` | — | off |

**산출** (`data/silver/immersio/{key}/`): `student_master.parquet` ·
`diagnostic_response.parquet` · `exam_result.parquet` · `exam_item.parquet` ·
`manifest.json`.
(앞 두 개가 **needs-map 의 입력**이다.)

---

## 3. `analyze` — Phase 1+2 (시험 품질 + 학생 지표)

```bash
uv run --package immersio immersio analyze \
  --semester 2026-1 --course anatomy
```

| 플래그 | 필수 | 기본값 |
|---|---|---|
| `--semester` / `--course` | ✅ | — |
| `--silver-dir` / `--gold-dir` | — | `data/silver` / `data/gold` |
| `--legacy-xlsx` | — | `data/silver/legacy/중간고사_분석결과.xlsx` (부재 시 diff 스킵) |
| `--created-at-utc` | — | 입력 sha256 기반 계산 (지정 시 byte-identical) |
| `--seed` | — | `42` (env `PAIDEIA_RANDOM_SEED`) |
| `--no-needs-map` | — | off (켜면 진단 연계 컬럼 N/A) |

**산출**:
- Silver: `문항통계.parquet` · `학생지표.parquet`
- Gold: `시험분석결과.xlsx`(7시트: 전체요약·메타데이터·변별력·정답률·학생성적·히스토그램·문항상세) ·
  `시험품질보고서.{md,pdf}` · `figs/fig{1,2}_*.png` · `legacy_diff.md`

> needs-map silver(`data/silver/needs-map/{key}/factor_scores.parquet`)가 있으면
> 학생 지표 시트에 `관심챕터_*`·`비호감챕터_*` 컬럼이 채워진다. 없으면 N/A.

---

## 4. `combine` — Phase 3 (진단 × 시험 결합)

needs-map 군집·요인 점수와 시험 결과를 결합해 상관·회귀·군집 비교를 분석한다.

```bash
uv run --package immersio immersio combine \
  --semester 2026-1 --course anatomy \
  --silver-dir data/silver --gold-dir data/gold \
  --include-cluster --include-subgroup
```

| 플래그 | 필수 | 의미 |
|---|---|---|
| `--semester` / `--course` | ✅ | — |
| `--silver-dir` / `--gold-dir` | ✅ | 기본값 없음 — 명시 필수 |
| `--include-cluster` | — | 군집 비교(fig5·§4·sheet3) 활성화 |
| `--include-subgroup` | — | 서브그룹 비교(fig6·§5·sheet4) 활성화 |

**입력**: needs-map 4종(`factor_scores`·`cluster_assignment`·`cluster_names.json`·
`manifest.json`) + immersio 4종(`student_master`·`diagnostic_response`·
`학생지표`·`manifest`).

**산출**:
- Silver: `진단×시험결합.parquet` · `manifest_phase3.json`
- Gold: `결합분석보고서.{md,pdf}` · `결합분석.xlsx`(2~4시트) · `figs/fig{3,4,5,6}_*.png`

---

## 5. `email` — Phase 6 (학생 맞춤 PDF 발송)

학생별 PDF 를 Gmail API 로 발송한다. **dry-run → self-test → 실제 발송** 순서를 권장.

```bash
# (1) dry-run — Gmail 호출 0, .eml 미리보기만
uv run immersio email --profile kjeong \
  --semester 2026-1 --course anatomy --exam-name "기말고사"

# (2) self-test — 운영자에게만 5건 (학생 도달 0, --send 필수)
uv run immersio email --profile kjeong \
  --semester 2026-1 --course anatomy --exam-name "기말고사" --self-test 5 --send

# (3) 실제 발송 — 확인 게이트(yes/no) 후 발송
uv run immersio email --profile kjeong \
  --semester 2026-1 --course anatomy --exam-name "기말고사" --send

# 실패자만 재시도
uv run immersio email --profile kjeong \
  --semester 2026-1 --course anatomy --exam-name "기말고사" --send --retry-failed
```

| 플래그 | 필수 | 기본값 |
|---|---|---|
| `--profile` | ✅ | `~/.config/paideia/immersio_email/{profiles,test_profiles}/{name}.yaml` |
| `--semester` / `--course` | ✅ | — |
| `--exam-name` | ✅ | — (빈 문자열 거부) |
| `--sent-date` | — | 오늘 (KST) |
| `--send` | — | off (= dry-run) |
| `--self-test N` | — | None (1–10, `--send` 필요) |
| `--retry-failed` / `--retry-skipped` | — | (상호 배타) |
| `--rate-per-min` | — | profile (기본 20, 1–30) |
| `--cohort` | — | `all` (또는 `low_score`/`rest`) |
| `--confirm-sample` | — | profile (기본 3) |
| `--bronze-csv` | — | `data/bronze/진단평가/진단평가_1차_결과.csv` |
| `--gold-pdf-dir` | — | `data/gold/immersio/{key}/이메일_발송용` |

### dry-run vs send 의미론 (중요)

| | dry-run (기본) | `--send` |
|---|---|---|
| Gmail API 호출 | 0 | 있음 |
| 학생 도달 | 0 | 있음 |
| 로그 파일 | `메일_발송로그_dryrun.csv` (truncate) | `메일_발송로그.csv` (append) |
| 미리보기 | `.eml` (To=학생) | — |
| 확인 게이트 | 없음 | 첫 N건 표본 + yes/no |

> **로그 파일이 분리**되어 dry-run 이 실제 발송 로그를 오염시키지 않는다.
> `status=success` 행은 재실행 시 자동 skip (idempotent).

### 인증

profile YAML 의 `secrets_ref.service_account_json_path_env` 가 가리키는 env
변수(예: `PAIDEIA_GCP_SA_JSON_PATH_KJEONG`)에 Service Account JSON 경로를 둔다.
Gmail DwD(domain-wide delegation) 위임 필요. 키 파일은 0400 권장(agenix 암호화).

### 보조 커맨드

- `immersio email-init-test-fixtures --profile <test>` — 테스트용 더미 PDF 생성
- `immersio email-cleanup-log --semester ... --course ... --keep success,test_dummy [--dry-run]`
  — v0.1.0 시기의 섞인 발송 로그 정리

---

## 6. 종료 코드 (요약)

| 커맨드 | 0 | 주요 비-0 |
|---|---|---|
| ingest | 성공 | 1 검증 · 2 인자/파일 · 3 IO · 4 무결성 |
| analyze | 성공 | 1 검증 · 2 pydantic · 3 결측 · 4 archival · 6 폰트 |
| combine | 성공 | 1·2·3·4 · 5 스키마 mismatch · 6 폰트 |
| email | 성공 | 1/2 입력 · 3 IO · 4 무결성 · 5 인증 · 7 lock · 8 부분실패 |

---

## 7. 환경 변수

| 변수 | 의미 |
|---|---|
| `PAIDEIA_RANDOM_SEED` | analyze seed (`--seed` 가 우선) |
| `PAIDEIA_KR_FONT_PATH` / `_BOLD_PATH` | NanumGothic 경로 (PDF/PNG 필수) |
| `PAIDEIA_GCP_SA_JSON_PATH_{PROFILE}` | email Service Account JSON 경로 |

---

## 8. 자주 막히는 곳

| 증상 | 해결 |
|---|---|
| `exit 6` / 한글 깨짐 | NanumGothic 설치 |
| `semester` 거부 | `YYYY-[12SW]` (예: `2026-1`), 하이픈 필수 |
| `course` 거부 | kebab-case 소문자 (`anatomy` OK, `Anatomy` 거부) |
| email exit 5 | SA JSON 경로/DwD 위임 확인 |
| email exit 7 | 동시 `--send` 또는 cleanup-log lock 충돌 |
| `--cohort low_score` 인데 exit 3 | `학생지표.parquet` 필요 |

---

## 관련 문서

- 선행 진단: [needs-map](../needs-map/how_to_use_needs-map.md) (Phase 3 결합 입력)
- 시험 출제: [examen](../examen/how_to_use_examen.md)
- 회고 환류: [retro-mester](../retro-mester/how_to_use_retro-mester.md)
- 설계 철학: [why_paideia](../why_paideia.md)
</content>
