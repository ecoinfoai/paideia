# paideia Development Guidelines

Auto-generated from all feature plans. Last updated: 2026-06-21

## Active Technologies
- Python 3.11 (uv workspace, paideia umbrella). 신규 모듈 `modules/metric-codex` workspace member + `shared/paideia_shared/schemas/metric_codex/` 계약 7종. pydantic≥2.6, pandas≥2.0+pyarrow≥15 (codex_entry.parquet 결정성), openpyxl≥3.1+xlrd≥2.0 (학교 성적·출석), pyyaml≥6, anthropic SDK(선택·가명화·폴백). 로컬 파일시스템 Bronze→Silver→Gold (Gold=md/yaml). (013-metric-codex-v0-1-0)
- Python 3.11 (uv workspace, paideia umbrella). 신규 모듈 `modules/needs-map`을 workspace member로 등록. (002-needs-map-v0-1-0)
- 로컬 파일시스템. (002-needs-map-v0-1-0)
- Python 3.11 (uv workspace, paideia umbrella). 기존 `modules/needs-map` workspace member 갱신 + `shared/paideia_shared` 갱신. 신규 모듈 없음(부패키지 추가). (003-needs-map-v0-1-1)
- 로컬 파일시스템 — v0.1.0과 동일 디렉터리 구조에 신규 파일 추가. (003-needs-map-v0-1-1)
- 로컬 파일시스템 (Bronze→Silver→Gold). silver `*.parquet`, gold `xlsx`/`md`/`pdf`/`png`. (004-immersio-phase1-exam-quality)
- Python 3.11 (uv workspace, paideia umbrella) + scipy≥1.11 (Levene/ANOVA/Welch), matplotlib≥3.8 (figs Agg dpi=150), reportlab≥4 (PDF Platypus + 자체 MD parser), pypdf≥5 (dev — PDF text 검증). 결정성: openpyxl 의 `<dcterms:modified>` core.xml 후처리 + reportlab `SOURCE_DATE_EPOCH` context manager + matplotlib PNG `Software=paideia` metadata + pyarrow `use_dictionary=False`/`write_statistics=False`. (004-immersio-phase1-exam-quality)
- Python 3.11 (uv workspace, paideia umbrella). 기존 `modules/immersio` workspace member 갱신 + `shared/paideia_shared/schemas/` 신규 모델 7종 추가. + pandas≥2.0, pyarrow≥15 (parquet `use_dictionary=False`/`write_statistics=False` 결정성), pydantic≥2.6, scipy≥1.11 (Pearson · Levene · Welch · t-test · Tukey HSD · `false_discovery_control` BH-FDR · `studentized_range` Games-Howell 의 critical value), **statsmodels≥0.14 (신규 도입 — OLS 적합 + VIF)**, matplotlib≥3.8 (figs Agg dpi=150 + `Software=paideia` PNG metadata, NanumGothic), reportlab≥4 (PDF Platypus + Phase 1+2 자체 MD parser 재사용, `SOURCE_DATE_EPOCH` context manager), openpyxl≥3.1 (xlsx 4 시트 + `<dcterms:modified>` core.xml 후처리). **Games-Howell 사후 비교는 수동 구현** (`combine/cluster_compare.py` 안 — 외부 의존 0; research.md R3 참조). (005-immersio-phase3-combined-analysis)
- 로컬 파일시스템 (Bronze→Silver→Gold). silver `진단×시험결합.parquet` + `manifest_phase3.json`; gold `결합분석보고서.{md,pdf}`, `결합분석.xlsx` (4 시트), `figs/fig{3..6}_*.png`. 디렉터리 규약 `data/silver/immersio/{semester}-{course}/`, `data/gold/immersio/{semester}-{course}/` (Phase 1+2 와 동일, archival 디렉터리 패턴 inherit). (005-immersio-phase3-combined-analysis)
- Python 3.11 (uv workspace, paideia umbrella). 기존 `modules/immersio` workspace member 갱신 + `shared/paideia_shared/schemas/` 신규 모델 1종 (PreSendSummary). 신규 모듈·워크스페이스 멤버 없음. (007-immersio-email-v0-1-1)
- 로컬 파일시스템 (Bronze→Silver→Gold). v0.1.0 디렉터리 구조 그대로 유지하되 dry-run 산출 파일 위치 분리: (007-immersio-email-v0-1-1)
- Python 3.11 (uv workspace, paideia umbrella). 신규 모듈 `modules/examen` 을 workspace member 로 등록. + pydantic≥2.6 (계약), pandas≥2.0 + xlrd≥2.0 (퀴즈 BIFF8 cp949 `.xls` 읽기) + openpyxl≥3.1 (xlsx 산출 + `<dcterms:modified>` 후처리 결정성), pyyaml≥6 (blueprint/curriculum_map/형성평가 yaml + 산출 yaml), pyarrow≥15 (silver parquet `use_dictionary=False`/`write_statistics=False` 결정성), anthropic SDK + instructor (LLM 구조화 출력; 폴백·캐시 동반). 외부 LLM 미도달 시에도 결정론 단계는 완주. (008-examen-question-gen)
- 로컬 파일시스템 (Bronze→Silver→Gold). Bronze: 교재·STT·형성평가·퀴즈·중간고사 레퍼런스. Silver: 교재 청크·근거 인덱스·출처 대장·강조 셀·blueprint 해석·생성요청 번들·LLM 응답 캐시. Gold: `기말출제초안.{xlsx,yaml}` · `출제품질리포트.md` · `ingest_report.json` · `manifest_examen.json`. (008-examen-question-gen)
- Python 3.11 (uv workspace, paideia umbrella). metric-codex v0.1.1 감사 후속 패치 — 신규 모듈·런타임 의존 없음(anthropic 핀만 추가). 기존 `modules/metric-codex` + `shared/paideia_shared/schemas/{_common,metric_codex/*}` 교정. 가명 append-only·stale Gold clear·manifest lineage·경계 fail-fast·가명화/근거 게이트·CanonicalStudentId ASCII. (014-metric-codex-v0-1-1)
- 로컬 파일시스템 (Bronze→Silver→Gold) — v0.1.0 구조 유지, Bronze 에 `cluster_names.json` own-copy 추가(FR-026). (014-metric-codex-v0-1-1)

- Python 3.11 (uv workspace, paideia umbrella) + pydantic≥2.6, pandas≥2.0, openpyxl≥3.1 (xlsx), xlrd≥2.0 (legacy .xls), pyarrow≥15 (001-ingest-phase0)

## Project Structure

```text
src/
tests/
```

## Commands

cd src [ONLY COMMANDS FOR ACTIVE TECHNOLOGIES][ONLY COMMANDS FOR ACTIVE TECHNOLOGIES] pytest [ONLY COMMANDS FOR ACTIVE TECHNOLOGIES][ONLY COMMANDS FOR ACTIVE TECHNOLOGIES] ruff check .

## Code Style

Python 3.11 (uv workspace, paideia umbrella): Follow standard conventions

## Recent Changes
- 014-metric-codex-v0-1-1: metric-codex v0.1.1 감사 후속 패치(BLOCK 해소) — 37건 전 등급 + T061 4게이트. 신규 모듈·런타임 의존 없음(anthropic 핀). 가명 append-only·stale 학생별 clear·manifest lineage(ledger 기반 input_hashes + roster 해시)·경계 fail-fast(--semester/--course·Excel 중복·Silver 키대조·off-roster)·가명화/근거 게이트(3자 한글이름 redact·PRIV-01 cache/staging_responses·reveal bijection·EVID template-only 명문)·LLM 백엔드 정합(temperature 제거·예외 타입분기)·CanonicalStudentId ASCII(전 워크스페이스 회귀).
- 013-metric-codex-v0-1-0: Added Python 3.11 (uv workspace, paideia umbrella). 신규 모듈 `modules/metric-codex` 를 workspace member 로 등록 + `shared/paideia_shared/schemas/metric_codex/` 신규 계약 7종. + pydantic≥2.6, pandas≥2.0 + pyarrow≥15 (silver `codex_entry.parquet` 결정성), openpyxl≥3.1 (학교 성적·출석 `.xlsx` 읽기) + xlrd≥2.0 (legacy `.xls`), pyyaml≥6 (성적출석_map·지도교수배정·question_set·자체 Bronze 사본 blueprint/curriculum), anthropic SDK (선택 `api` LLM 다듬기 — `InputHashCache` 재사용, 미도달 시 결정론 template 폴백). **가명화(S001) LLM 경계 — PII 불출(net-new)**; immersio/needs-map Silver 소비 + Silver 미영속 입력은 자체 Bronze 사본(원칙 II). Gold 는 md/yaml (xlsx/PDF/PNG·vector DB 없음).
- 008-examen-question-gen: Added Python 3.11 (uv workspace, paideia umbrella). 신규 모듈 `modules/examen` 을 workspace member 로 등록. + pydantic≥2.6 (계약), pandas≥2.0 + xlrd≥2.0 (퀴즈 BIFF8 cp949 `.xls` 읽기) + openpyxl≥3.1 (xlsx 산출 + `<dcterms:modified>` 후처리 결정성), pyyaml≥6 (blueprint/curriculum_map/형성평가 yaml + 산출 yaml), pyarrow≥15 (silver parquet `use_dictionary=False`/`write_statistics=False` 결정성), anthropic SDK + instructor (LLM 구조화 출력; 폴백·캐시 동반). 외부 LLM 미도달 시에도 결정론 단계는 완주.


<!-- MANUAL ADDITIONS START -->
<!-- MANUAL ADDITIONS END -->

<!-- SPECKIT START -->
For additional context about technologies to be used, project structure,
shell commands, and other important information, read the current plan:
specs/015-security-hardening/plan.md
<!-- SPECKIT END -->
