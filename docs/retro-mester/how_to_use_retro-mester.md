# how_to_use_retro-mester

> 🚧 **이 모듈은 아직 개발되지 않았습니다 (The module is under development).**
>
> 현재는 `idea/retro-mester-v0.1.0.md` 설계 문서로만 존재합니다.
> 실행 가능한 CLI·코드는 없으며, 구현 시 본 문서로 사용법을 채웁니다.

---

## 무엇이 될 모듈인가

**retro-mester** — 한 학기 운영을 마친 뒤 그 학기 데이터로
**"내년 같은 수업을 어떻게 가르칠까"** 의 짧고 우선순위 매겨진
**수업 설계 변경 목록(3~5개)** 을 산출하는 CQI(지속적 개선) 도구.
paideia 6모듈 사이클의 **마지막 고리**다.

| 항목 | 계획 |
|---|---|
| 입력 | needs-map(출발) + immersio(도착) 산출 (v0.1.0 은 양 끝만) |
| 산출 | 우선순위 매겨진 내년 수업 변경 3~5개 + 단원별 진단 보고서 |
| 학기 시점 | 학기 종료 후(방학 중) 1회 |
| 의존성 | needs-map, immersio (이후 formative-analysis 보강) |
| 코드 vs LLM | 지점 찾기·묶기·원인 분류·크기 산정 = 코드, 서사 문장화만 LLM 옵션 |

## 핵심 설계 방향 (요약)

- 대상은 **개별 학생 지원이 아니라 내년 수업 설계**다. 출력의 주어는
  "이런 성향 유형 → 이런 패턴 → 내년 수업은 이렇게".
- 평균을 믿지 않고 **이질적 혼합**(저노력 다수 + 소수 고노력 성인학습자)을
  성향 유형으로 분해한다.
- 단원별로 **"어려워서 막힘(내용·기초) vs 안 해서 막힘(동기)"** 을 구분한다.
- 보고서를 needs-map 성향 언어로 표현해 **다음 해 needs-map 이 인용**하게 한다.
- 결정론: 같은 입력 → 같은 보고서(서사 제외 코어).

## 참고

- 설계 메모: `idea/retro-mester-v0.1.0.md`, `idea/paideia-idea.md` §1.6
- 입력 모듈: [needs-map](../needs-map/how_to_use_needs-map.md) ·
  [immersio](../immersio/how_to_use_immersio.md)
- 전체 그림: [why_paideia](../why_paideia.md)
</content>
