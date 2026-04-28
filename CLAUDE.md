# paideia Development Guidelines

Auto-generated from all feature plans. Last updated: 2026-04-28

## Active Technologies
- Python 3.11 (uv workspace, paideia umbrella). 신규 모듈 `modules/needs-map`을 workspace member로 등록. (002-needs-map-v0-1-0)
- 로컬 파일시스템. (002-needs-map-v0-1-0)
- Python 3.11 (uv workspace, paideia umbrella). 기존 `modules/needs-map` workspace member 갱신 + `shared/paideia_shared` 갱신. 신규 모듈 없음(부패키지 추가). (003-needs-map-v0-1-1)
- 로컬 파일시스템 — v0.1.0과 동일 디렉터리 구조에 신규 파일 추가. (003-needs-map-v0-1-1)
- 로컬 파일시스템 (Bronze→Silver→Gold). silver `*.parquet`, gold `xlsx`/`md`/`pdf`/`png`. (004-immersio-phase1-exam-quality)

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
- 004-immersio-phase1-exam-quality: Added Python 3.11 (uv workspace, paideia umbrella)
- 003-needs-map-v0-1-1: Added Python 3.11 (uv workspace, paideia umbrella). 기존 `modules/needs-map` workspace member 갱신 + `shared/paideia_shared` 갱신. 신규 모듈 없음(부패키지 추가).
- 002-needs-map-v0-1-0: Added Python 3.11 (uv workspace, paideia umbrella). 신규 모듈 `modules/needs-map`을 workspace member로 등록.


<!-- MANUAL ADDITIONS START -->
<!-- MANUAL ADDITIONS END -->
