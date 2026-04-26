# Axis Key Vocabulary (immersio Phase 0)

매핑 YAML(`config/{course-slug}.diagnostic.yaml`)이 학생 응답 컬럼을 의미축에
사상할 때 사용하는 표준 axis 키 어휘. 본 문서는 paideia 우산 모듈 사이의 안정성
계약(헌장 III "Variability via Configuration")을 박제한다.

## Standard axis keys (v0.1)

| axis | kind | 정의 | 후속 Phase 사용 |
|------|------|------|-----------------|
| `motivation` | likert | 학습 동기 (의학·간호 진로 동기 등) | Phase 3 회귀, Phase 4 라벨링 |
| `anxiety` | likert | 평가 불안·상황 불안 | Phase 3 군집, Phase 4 라벨링 |
| `interest_chapters` | multiselect | 학생이 관심 있는 챕터·주제 | Phase 5 자유서술, Phase 6 카드 |
| `learning_strategies` | likert (optional) | 자기조절 학습 전략 사용 정도 | Phase 3 회귀 |
| `prior_biology` | likert (optional) | 사전 생물학 지식 자가평가 | Phase 3 군집 |
| `anxiety_freetext` | freetext (optional) | 불안 자유서술 원문 | Phase 5 NLP |

## Migration policy

- **추가**: 신규 axis 키는 매핑 YAML의 `axes.optional`로 먼저 도입 → 후속 Phase에서
  사용처 확인 후 다음 minor 릴리스에서 `axes.required`로 격상 가능.
- **이름 변경 / 제거**: `paideia_shared.schemas` 패키지 단위 MAJOR semver bump 필수
  (research.md §1). manifest의 `paideia_shared_version`이 산출 시점 버전을 박제하므로
  과거 산출도 사후 추적 가능하다.
- **새 교과목 적용**: 본 문서의 키 어휘에 따라 `config/{course-slug}.diagnostic.yaml`을
  작성한다. 모듈 코드 변경 0건. axis 키만 일치하면 동일 형태의 Silver 산출이 보장된다.

## Cross-link

- 권위 있는 데이터 계약: `paideia_shared.schemas`
- 매핑 YAML 형식: `specs/001-ingest-phase0/contracts/diagnostic_mapping.schema.yaml`
- 결정 근거: `specs/001-ingest-phase0/research.md` §1, §7
