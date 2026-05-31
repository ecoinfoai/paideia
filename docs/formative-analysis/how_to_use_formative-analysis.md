# how_to_use_formative-analysis

> 🚧 **이 모듈은 paideia 저장소에 아직 통합되지 않았습니다 (The module is under development / pending integration).**
>
> 코드 자체는 별도 저장소(`~/localgit/formative-analysis/`)에 **완성**되어
> 있으나, paideia umbrella workspace 의 `modules/` 로 이전·통합되지 않았습니다.
> 통합 후 본 문서에 paideia 규약(Bronze/Silver/Gold·CLI)에 맞춘 사용법을 채웁니다.

---

## 무엇이 될 모듈인가

매 주차 **형성평가 시험지 생성 + 응답 결과 분석 + 개인별 보고서**를 만드는 모듈.

| 항목 | 계획 |
|---|---|
| 입력 | maieutica 가 생성한 서술형 후보 + 학생 응답 |
| 산출 | 시험지 PDF + 학생별 분석 보고서 |
| 학기 시점 | 학기 중 매주 |
| 의존성 | maieutica (또는 수기 입력) |
| 상태 | 코드 완성, paideia 통합 대기 |

## 통합 로드맵

`idea/paideia-idea.md` 에 따르면 formative-analysis 는 별도 선행 프로젝트로
완성된 뒤 paideia `modules/` 로 흡수될 예정이다. retro-mester 의 주차별 궤적
보강(enrichment) 입력도 이 통합 이후 더해진다.

## 현재 대안

통합 전까지는 다음으로 유사 산출을 만들 수 있다.

- **formative-test-creator** 스킬 — 서술형 형성평가 문항 + 루브릭 + 지원 계획
- 별도 저장소 `~/localgit/formative-analysis/` 의 기존 도구

## 참고

- 설계 메모: `idea/paideia-idea.md` §1.3
- 전체 그림: [why_paideia](../why_paideia.md)
</content>
