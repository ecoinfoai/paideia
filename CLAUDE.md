# paideia Development Guidelines

Auto-generated from all feature plans. Last updated: 2026-04-29

## Active Technologies
- Python 3.11 (uv workspace, paideia umbrella). 신규 모듈 `modules/needs-map`을 workspace member로 등록. (002-needs-map-v0-1-0)
- 로컬 파일시스템. (002-needs-map-v0-1-0)
- Python 3.11 (uv workspace, paideia umbrella). 기존 `modules/needs-map` workspace member 갱신 + `shared/paideia_shared` 갱신. 신규 모듈 없음(부패키지 추가). (003-needs-map-v0-1-1)
- 로컬 파일시스템 — v0.1.0과 동일 디렉터리 구조에 신규 파일 추가. (003-needs-map-v0-1-1)
- 로컬 파일시스템 (Bronze→Silver→Gold). silver `*.parquet`, gold `xlsx`/`md`/`pdf`/`png`. (004-immersio-phase1-exam-quality)
- Python 3.11 (uv workspace, paideia umbrella) + scipy≥1.11 (Levene/ANOVA/Welch), matplotlib≥3.8 (figs Agg dpi=150), reportlab≥4 (PDF Platypus + 자체 MD parser), pypdf≥5 (dev — PDF text 검증). 결정성: openpyxl 의 `<dcterms:modified>` core.xml 후처리 + reportlab `SOURCE_DATE_EPOCH` context manager + matplotlib PNG `Software=paideia` metadata + pyarrow `use_dictionary=False`/`write_statistics=False`. (004-immersio-phase1-exam-quality)

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
- 004-immersio-phase1-exam-quality: immersio v0.1.0 — Phase 1+2 시험 품질 + 학생 지표 단일 명령 (`paideia immersio analyze`). 9 산출 파일 (xlsx 7시트 + md/pdf + 2 figs + 2 parquet + 2 manifest + legacy_diff). byte-identical 결정성, LLM 호출 0, NanumGothic 폰트 의존, 6종 distractor 라벨 룰셋, archival pre-step (Constitution V "부분 산출 금지"). 305 passed, 13 xfailed.
- 003-needs-map-v0-1-1: Added Python 3.11 (uv workspace, paideia umbrella). 기존 `modules/needs-map` workspace member 갱신 + `shared/paideia_shared` 갱신. 신규 모듈 없음(부패키지 추가).
- 002-needs-map-v0-1-0: Added Python 3.11 (uv workspace, paideia umbrella). 신규 모듈 `modules/needs-map`을 workspace member로 등록.


<!-- MANUAL ADDITIONS START -->
<!-- MANUAL ADDITIONS END -->
