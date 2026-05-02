# immersio

paideia 우산의 시험 결과 해석 + 학생 맞춤형 보고서 생성 모듈.

## v0.1.0 현재 상태

| Phase | 상태 | 주요 산출 |
|-------|------|----------|
| 0 (Bronze→Silver ingest) | ✅ 완료 | 4 Pydantic silver schemas + 5s SLA |
| 1 (시험 품질) | ✅ 완료 | xlsx 6 sheets + md/pdf + fig1/fig2 + manifest |
| 2 (학생 지표) | ✅ 완료 | 학생성적 7번째 시트 + 학생지표.parquet round-trip |
| 3 (진단↔성적 결합) | ✅ 완료 (v0.1.0) | silver `진단×시험결합.parquet` + manifest_phase3 + gold md/pdf/xlsx + 4 figs (fig3 heatmap / fig4 β-bar / fig5 cluster / fig6 subgroup) — `paideia immersio combine --semester {S} --course {C} --silver-dir {D} --gold-dir {D} [--include-cluster] [--include-subgroup]` |
| 4 (라벨링) | 후속 spec |  |
| 6 (카드 PDF) | 후속 spec |  |
| email (학생별 보고서 발송) | ✅ 완료 (v0.1.0 / spec 006) | dry-run 미리보기 .eml + Gmail API 본 발송 + 발송 로그 13컬럼 + 한국어 보고서 + cohort 분할 + idempotent 재실행 — `immersio email --profile {N} --semester {S} --course {C} --exam-name {E} [--cohort {low_score|rest|all}] [--send] [--self-test N] [--retry-failed \| --retry-skipped] [--rate-per-min N]` |

### `immersio email` 한 단락 (spec 006)

학생 1인 1장 보고서 PDF 184장을 각 학생 이메일로 1:1 단건 발송. **운영 흐름 4단계**:
1. **dry-run** (default — `--send` 없음) → `tmp/immersio_email_preview/{semester}-{course}/*.eml` + cohort 명단 md → 운영자 시각 검수
2. **self-test** (`--self-test N --send`) → 첫 N건이 운영자 본인 메일함으로 발송 → 한국어 인코딩·캘린더 링크·첨부 학번 시각 확인
3. **본 발송** (`--send`) → 확인 게이트 (`yes` 입력) → Gmail API DwD impersonation 으로 학생 184건 발송 + 발송 로그 csv (13컬럼) + 한국어 보고서 md
4. **재실행** (FR-D03) → `success` 학생 자동 skip; `--retry-failed` / `--retry-skipped` 분리 옵션

자세한 절차: `specs/006-immersio-email-v0-1-0/quickstart.md` (Cohort 분할 발송 시나리오 포함).

본 README 의 §사용법 / §exit code / §환경변수 / §Privacy 는 v0.1.0
spec (`specs/004-immersio-phase1-exam-quality/`) 의 **Phase 1+2 단일
명령 사용** 을 기준으로 한다. Phase 0 ingest 자세한 절차는
`specs/001-ingest-phase0/quickstart.md` 참조.

## 위치

- 모듈 경로: `modules/immersio/`
- 공유 데이터 계약: `shared/paideia_shared/src/paideia_shared/schemas/`
- v0.1.0 사양: `specs/004-immersio-phase1-exam-quality/{spec,plan,research,data-model,contracts/,quickstart}.md`
- v0.1.0 운영자 매뉴얼: `specs/004-immersio-phase1-exam-quality/quickstart.md`

## 설치

```sh
nix develop                               # paideia devShell 진입
uv sync --python 3.11 --all-packages --all-groups
```

NanumGothic 폰트가 시스템에 설치되어 있어야 한다 (PDF + figures Korean
glyph). NixOS:
```nix
home.packages = [ pkgs.nanum ];
```
Ubuntu/Debian: `sudo apt install fonts-nanum`. macOS: `brew install
--cask font-nanum-gothic`. 미설치 시 analyze CLI 가 exit 6 + 설치 안내로
종료한다.

## 사용법

### Phase 0 ingest (1회 또는 데이터 갱신 시)

```sh
uv run --package immersio immersio ingest \
  --bronze-dir data/bronze \
  --mapping data/bronze/매핑/anatomy.diagnostic.yaml \
  --exam-yaml data/bronze/시험문제/실제_출제문제.yaml \
  --output-key 2026-1-anatomy \
  --no-git-commit
```

### Phase 1+2 분석 — 단일 명령 (FR-032)

```sh
uv run --package immersio immersio analyze \
  --semester 2026-1 \
  --course anatomy \
  [--legacy-xlsx data/silver/legacy/중간고사_분석결과.xlsx] \
  [--created-at-utc 2026-04-29T00:00:00Z] \
  [--seed 42] \
  [--no-needs-map] \
  [--verbose | --quiet]
```

## 출력 파일 9종 (FR-001/004/022/030)

```
data/silver/immersio/{semester}-{course}/
├── 학생지표.parquet              ← StudentExamMetrics, snappy 압축
└── manifest.json                 ← silver-side audit metadata

data/gold/immersio/{semester}-{course}/
├── 시험분석결과.xlsx             ← 7 sheets (legacy 호환 구조)
├── 시험품질보고서.md             ← 룰 기반 자연어 (9 섹션)
├── 시험품질보고서.pdf            ← reportlab Platypus + 자체 MD parser
├── figs/
│   ├── fig1_전체성적_히스토그램.png
│   └── fig2_메타데이터별_정답률.png
├── legacy_diff.md                ← legacy xlsx 와의 셀 단위 비교 + 사유 추정
└── manifest.json                 ← gold-side audit metadata
```

산출 파일 9종 모두 동일 입력에 대해 **byte-identical** (FR-023, SC-002).
xlsx Producer / pdf CreationDate / png Software / parquet metadata 모두
`manifest.generated_at_utc` 단일 소스에서 도출된다 (research §R-10).

## Exit Codes (FR-033, contracts/cli.md)

| Code | 의미 |
|------|------|
| 0 | 성공 |
| 1 | 입력 검증 실패 (인자 형식 오류, semester/course 패턴 위반, --created-at-utc 비-ISO8601) |
| 2 | Pydantic ValidationError (silver schema 위반) |
| 3 | 파일 누락 (silver 4종 부재 / needs-map silver 부분 부재 / legacy xlsx 손상이 아닌 부재) |
| 4 | archival 실패 (이전 산출물 이동 실패 — 부분 산출 금지 게이트) |
| 5 | legacy_diff 생성 실패 (legacy xlsx 손상 → `LegacyLoadError`) |
| 6 | NanumGothic 폰트 미해상 (`KoreanFontUnavailableError`) |
| 99 | 내부 오류 (catch-all) |

## 환경변수

| Var | 의미 |
|-----|------|
| `PAIDEIA_RANDOM_SEED` | `--seed` default override (없으면 42) |
| `PAIDEIA_KR_FONT_PATH` | NanumGothic Regular 경로 (`fonts.py` resolver) |
| `PAIDEIA_KR_FONT_BOLD_PATH` | NanumGothic Bold 경로 |
| `SOURCE_DATE_EPOCH` | reproducible-builds convention; immersio 가 자체 pin 하므로 상속만 함 |

## Privacy (PII 정책)

본 모듈의 산출 파일 (xlsx 의 `학생성적` 시트 + 학생지표.parquet 등) 에는
**학생 학번 + 이름이 그대로 노출** 된다. 이는 spec assumption §"공통 PII
정책" 에 따른 *내부 운영자 사용* 전제의 의도된 동작이다:

- 산출 파일은 학과 RISE 사업단 + 교과목 책임 교수 의 **내부 회의용**.
- 외부 (학생, 다른 부서, 출판) 공유 시 **운영자 책임** 으로 마스킹 / 재출
  필요. 본 spec 의 v1 범위 외.
- 외부 공유 마스킹은 후속 spec (예: `010-pii-masking`) 에서 다룬다.

학생 ID 는 paideia_shared 의 `CanonicalStudentId` 패턴 (`^\d{10}$`) 을
강제하여 무결성 검증된다. 이름 / 분반 등은 출처 (출석부 / 진단평가)
원문 그대로 보존된다.

## 디렉터리

```
modules/immersio/
├── README.md
├── docs/
│   ├── immersio-idea.md          # v0.1.0 설계 노트
│   └── axis-keys.md              # 진단 axis 어휘 + migration policy
├── pyproject.toml
├── scripts/
│   └── build_attendance_template.py
├── src/immersio/
│   ├── analyze/                  # pipeline.py orchestrator + archival + silver_writer + timing
│   ├── analysis/                 # 통계: overall_summary, histogram, metadata_stats,
│   │                             #       discrimination, item_stats, distractor_labels,
│   │                             #       student_metrics, topic_alignment, stat_tests, ruleset
│   ├── cli/                      # `immersio {ingest,analyze}` 진입점
│   ├── fonts.py                  # NanumGothic 해상 (env-var → fc-match)
│   ├── ingest/                   # Phase 0 pipeline·combine·validate·write
│   ├── io/                       # 4 Bronze 파서 (출석부/OMR/진단/매핑)
│   ├── mapping/                  # YAML 로더 + 적용기
│   ├── normalize/                # 학번/Likert/multiselect/encoding/hashing
│   └── report/                   # md_parser, md_writer, pdf_writer, xlsx_writer,
│                                 # figures, legacy_diff
├── templates/
│   └── attendance.xlsx
└── tests/
    ├── fixtures/                 # bronze_minimal + synthetic_44_with_all_labels +
    │                             # legacy_xlsx_anchors.json + build_synthetic_44.py
    ├── integration/              # e2e + determinism + LLM-0 + archival + multi-semester
    │                             # + anatomy_full_run + quality_report_density + adversary
    └── unit/                     # 19 unit test files
```

## 데이터 계약

본 모듈의 산출은 `paideia_shared.schemas` 의 11 Pydantic 모델을 권위
형식으로 따른다 — Phase 0 의 4 (StudentMaster·DiagnosticResponse·
ExamResult·ExamItem) + Phase 1+2 의 6 (ItemStatistics·StudentExamMetrics·
MetadataAggregate·HistogramBin·LegacyDiffEntry·ImmersioPhase1Manifest) +
공통 IngestManifest. 매핑 YAML 은 `DiagnosticMappingConfig` 를 만족한다.

## 의존성

- Python 3.11
- pyarrow, pandas, openpyxl, xlrd, pydantic, pyyaml
- scipy (통계 검정), matplotlib (figures), reportlab (PDF), pypdf (dev)
- (dev) pytest, pytest-cov, hypothesis

상세는 `pyproject.toml` 참조.

## 후속 spec (Phase 3·4·6)

- **Phase 3** — needs-map × exam 결합 분석 (상관·회귀·군집 비교)
- **Phase 4** — 자동 학생 라벨링 (🔴 예상 외 부진, 🟢 역전 우수 등)
- **Phase 6** — 학생 1인 1장 카드 PDF (immersio + needs-map 결합)

본 v0.1.0 산출 (특히 `factor_scores_long.csv` from needs-map +
`학생지표.parquet` from immersio) 가 후속 spec 의 결합 분석 입력이 된다.

## Limitations & Future Work

본 v0.1.0-rc1 에서 의도적으로 polish/후속으로 미룬 항목:

- **`topic_alignment.CHAPTER_KEYWORDS` 코드 상수**: anatomy 7장 ↔
  needs-map 옵션 텍스트 substring 매칭 사전이 코드 상수. v2 에서 yaml
  외부화 (`data/bronze/매핑/{course}.chapter_alignment.yaml`) 로
  promote 해야 하는 트리거 3종:
  1. 두 번째 과목 (microbio 등) 의 immersio Phase 1+2 분석 시작
  2. anatomy 챕터 명칭이 학기 중 변경
  3. needs-map multiselect 옵션 텍스트가 변경
  (research §R-09 정합 — Constitution III v1 한정 절충.)
- **`immersio/fonts.py` 가 `needs_map.fonts` 와 1:1 중복**: spec 의
  `paideia_shared.fonts (이미 land)` 가 실제로는 needs-map 모듈에 land
  된 상태. 본 phase 는 immersio 안에 복제 + 후속 polish phase 에서
  paideia_shared 로 promote → 두 모듈 동시 import 변경 권장.
- **logger 헬퍼 정책**: stdlib `logging.getLogger(__name__)` 모듈 단위
  사용 (별도 `_log.py` 헬퍼 미도입). 향후 운영 메시지 표준화 시 cross-
  cutting refactor 로 promote 가능.
- **adversary A2 symlink escape**: env-var 폰트 경로의 symlink chain
  이 NanumGothic 외부로 escape 하는 시나리오는 현재 ValueError 차단까지.
  v0.2 에서 `Path.resolve(strict=True).is_relative_to(allowed_root)` 로
  strict reject.
- **adversary A8 16k 패턴 length cap 미land**: glob 패턴 length 가
  16k 초과 시 운영 환경 ReDoS 가능성. 현재 `_MAX_GLOB_PATTERN_LEN`
  (1024) 로 차단되지만 더 보수적 정책 (예: 운영 명시 256) 검토.
- **xlsx 의 modified 후처리 (T076 fix)**: openpyxl 이 `wb.save()` 시
  `<dcterms:modified>` 를 `datetime.now()` 로 덮어씀 → zip 후처리로
  rewrite. 향후 openpyxl 이 native pin 옵션을 추가하면 후처리 코드 제거
  가능 (현재는 가장 견고한 패턴).

## 라이선스

paideia 우산 라이선스를 따른다.
