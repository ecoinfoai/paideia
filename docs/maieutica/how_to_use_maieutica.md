# how_to_use_maieutica

> 🚧 **이 모듈은 아직 개발되지 않았습니다 (The module is under development).**
>
> 현재는 `idea/` 의 설계 문서로만 존재하며, 실행 가능한 CLI·코드는 없습니다.
> 아래는 계획된 방향이며 구현 시 본 문서로 사용법을 채웁니다.

---

## 무엇이 될 모듈인가

**maieutica**(그리스어 *μαιευτική*, 산파술) — 매주 진행할 **객관식 퀴즈
후보**와 **서술형 형성평가 후보**를 교재 텍스트로부터 생성하는 모듈.

| 항목 | 계획 |
|---|---|
| 입력 | 교재 챕터 텍스트 (PDF 추출 또는 Markdown) |
| 산출 | 챕터별 객관식 후보 N개 + 서술형 후보 M개 (Pydantic 검증 JSON) |
| 학기 시점 | 학기 전(전체) + 매주(점진) |
| 의존성 | 교재 |
| 코드 vs LLM | 텍스트 청킹·구조화 출력 검증 = 코드, 문항 생성 = LLM 필수 |
| 후속 소비자 | formative-analysis, examen |

LLM 출력은 반드시 Pydantic 스키마로 검증된 JSON 으로 받아(AutoQuizzer 패턴),
하류 모듈이 안전하게 소비하도록 한다.

## 현재 대안

모듈이 나오기 전까지는 다음 Claude Code 스킬로 유사한 산출을 만들 수 있다.

- **chapter-quiz-generator** — 챕터별 5지선다 퀴즈 20문항 생성
- **formative-test-creator** — 서술형 형성평가 문항 + 루브릭 생성

## 참고

- 설계 메모: `idea/paideia-idea.md` §1.2
- 전체 그림: [why_paideia](../why_paideia.md)
</content>
