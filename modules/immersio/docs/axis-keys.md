# Axis Key Vocabulary (immersio Phase 0)

매핑 YAML(`config/{course-slug}.diagnostic.yaml`)이 학생 응답 컬럼을 의미축에
사상할 때 사용하는 표준 axis 키 어휘. 본 문서는 paideia 우산 모듈 사이의 안정성
계약(헌장 III "Variability via Configuration")을 박제한다.

## Standard axis keys (paideia v0.1.0)

paideia v0.1.0 표준 어휘는 **6 키**로 고정된다(spec `002-needs-map-v0-1-0` FR-AXIS-001,
Clarifications §2). 새 axis 추가는 paideia minor 버전 bump 사안이며,
`paideia_shared.schemas.diagnostic_mapping` v6 검증자가 비표준 axis를 차단한다.

| axis | 권장 kind | 정의 | 후속 Phase 사용 |
|------|-----------|------|-----------------|
| `motivation` | likert | 학습 동기 (의학·간호 진로 동기 등) | Phase 3 회귀, Phase 4 라벨링 |
| `anxiety` | likert + (optional) freetext | 평가 불안·상황 불안 + 자유서술 | Phase 3 군집, Phase 4 라벨링, needs-map Phase D 자유서술 분류 |
| `self_efficacy` | likert | 자기 효능감 | needs-map Phase B/C |
| `interest` | multiselect 또는 freetext | 관심 있는 챕터·주제 | needs-map Phase B, Phase 5 자유서술 |
| `prior_knowledge` | multiselect (sum) | 사전 지식 (예: 고교 생물 이수 여부) | needs-map Phase B/C, partition 후보 |
| `life_context` | multiselect 또는 freetext | 생활 맥락 (직업·시간 가용성 등) | needs-map Phase B/E, partition 후보 |

**같은 axis에 likert + freetext 동시 매핑** 가능 (`paideia_shared.schemas.diagnostic_mapping`
v4 freetext 면제, contracts/diagnostic_mapping_extension.md). 점수 산출은 likert만,
자유서술은 needs-map Phase D dictionary/LLM 분류로 별도 사용.

## Migration policy

- **신규 axis 추가**: paideia minor 버전 bump가 필요하다. `paideia_shared.schemas.
  diagnostic_mapping` v6 + `_common.StandardAxisKey` 두 곳을 동시에 갱신.
- **이름 변경 / 제거**: `paideia_shared.schemas` 패키지 단위 MAJOR semver bump 필수.
  manifest의 `paideia_shared_version`이 산출 시점 버전을 박제하므로 과거 산출도
  사후 추적 가능하다.
- **새 교과목 적용**: 본 문서의 키 어휘에 따라 `config/{course-slug}.diagnostic.yaml`을
  작성한다. 모듈 코드 변경 0건. axis 키만 일치하면 동일 형태의 Silver 산출이 보장된다.
- **6 키 미충족 허용**: 매핑 YAML이 6 키 모두를 채울 필요는 없다(FR-AXIS-002). 누락 axis는
  needs-map 산출의 해당 축이 None으로 일관 처리되고 manifest `standard_axes_skipped`에 기록된다.

## Cross-link

- 권위 있는 데이터 계약: `paideia_shared.schemas`
- 매핑 YAML 형식: `specs/001-ingest-phase0/contracts/diagnostic_mapping.schema.yaml`
- 결정 근거: `specs/001-ingest-phase0/research.md` §1, §7
