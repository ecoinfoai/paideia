# immersio

paideia 우산의 시험 결과 해석 + 학생 맞춤형 보고서 생성 모듈. 본 v0.1은 Phase 0
(Bronze→Silver 학생 마스터 ingest)이 완료되어 다음 Phase 입력 계약을 안정적으로
공급할 준비가 되었다.

## 위치

- 모듈 경로: `modules/immersio/`
- 공유 데이터 계약: `shared/paideia_shared/src/paideia_shared/schemas/`
- 사양: `specs/001-ingest-phase0/{spec,plan,research,data-model,contracts/,quickstart}.md`

## 설치 / 실행

```sh
nix develop                  # paideia devShell 진입
uv sync --python 3.11 --all-packages --all-groups
uv run immersio ingest \
  --bronze-dir data/bronze \
  --mapping config/anatomy.diagnostic.yaml \
  --verbose
```

상세 절차: `specs/001-ingest-phase0/quickstart.md`.

## 현재 상태

| Phase | 상태 |
|-------|------|
| 0 (Bronze→Silver ingest) | 완료 — US1·US2·US3 통과, 5초 SLA, 113+ 테스트 |
| 1 (시험 품질) | 미착수 |
| 2 (학생 지표) | 미착수 |
| 3 (진단↔성적) | 미착수 |
| 4 (라벨) | 미착수 |
| 5 (자유서술) | 미착수 |
| 6 (카드 PDF) | 미착수 |
| 7 (후속 운영) | 미착수 |

## 디렉터리

```
modules/immersio/
├── README.md
├── docs/
│   ├── immersio-idea.md        # 설계 노트
│   └── axis-keys.md            # 진단 axis 어휘 + migration policy
├── pyproject.toml              # immersio package + console script
├── scripts/
│   └── build_attendance_template.py
├── src/immersio/
│   ├── cli/                    # `immersio ingest` 진입점
│   ├── ingest/                 # pipeline·combine·validate·write·errors
│   ├── io/                     # 4 Bronze 파서
│   ├── mapping/                # YAML 로더 + 적용기
│   └── normalize/              # 학번/Likert/multiselect/encoding/hashing
├── templates/
│   └── attendance.xlsx         # 출석부 표준 템플릿 (FR-021)
└── tests/
    ├── fixtures/               # bronze_minimal + bronze_minimal_microbio + mappings
    ├── integration/            # happy path · 결정성 · CLI · failfast 9종 · 포터빌리티 · 5s SLA
    └── unit/                   # normalize 5종 + 매핑 로더 + 속성 테스트
```

## 데이터 계약

본 모듈의 산출은 `paideia_shared.schemas`의 4 Pydantic 모델
(StudentMaster·DiagnosticResponse·ExamResult·ExamItem)을 권위 형식으로 따른다.
manifest 사이드카는 `IngestManifest`를, 매핑 YAML은 `DiagnosticMappingConfig`를 만족한다.

## 의존성

- Python 3.11
- pyarrow, pandas, openpyxl, xlrd, pydantic, pyyaml
- (dev) pytest, pytest-cov, hypothesis

상세는 `pyproject.toml` 참조.

## 라이선스

paideia 우산 라이선스를 따른다.
