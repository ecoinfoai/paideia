# paideia 문서 (docs)

한 학기 교과목 운영의 전 주기 — **사전진단 → 출제 → 결과해석 → 회고** — 를
데이터로 닫힌 루프로 연결하는 모듈 모음의 공식 문서.

## 시작하기

| 문서 | 누구를 위한 것 |
|---|---|
| [why_paideia.md](why_paideia.md) | paideia 가 무엇이고 왜 만들었는지 — 처음 오는 사람 |
| [quickstart.md](quickstart.md) | 5분 안에 첫 산출물 보기 — 설치·실행 |
| [tutorial.md](tutorial.md) | 한 학기를 처음부터 끝까지 따라가는 실습 |

## 모듈별 사용법

| 모듈 | 역할 | 상태 | 문서 |
|---|---|---|---|
| **needs-map** | 사전진단 분석 (의미축·군집·1인 1장 카드) | ✅ 출하 | [how_to_use_needs-map.md](needs-map/how_to_use_needs-map.md) |
| **examen** | 기말 시험 문제 초안 결정론적 출제 | ✅ 출하 | [how_to_use_examen.md](examen/how_to_use_examen.md) |
| **immersio** | 시험 결과 해석 + 학생 맞춤 보고서 + 이메일 | ✅ 출하 | [how_to_use_immersio.md](immersio/how_to_use_immersio.md) |
| **maieutica** | 매주 퀴즈/형성평가 후보 생성 | 🚧 개발 중 | [how_to_use_maieutica.md](maieutica/how_to_use_maieutica.md) |
| **formative-analysis** | 매주 형성평가 시행·분석 | 🚧 통합 예정 | [how_to_use_formative-analysis.md](formative-analysis/how_to_use_formative-analysis.md) |
| **retro-mester** | 학기 회고 → 차년도 수업 설계 | 🚧 개발 중 | [how_to_use_retro-mester.md](retro-mester/how_to_use_retro-mester.md) |
| **metric-codex** | 학생 중심 학습역량 누적·질의 (하류 프로젝트) | 🚧 개발 중 | [how_to_use_metric-codex.md](metric-codex/how_to_use_metric-codex.md) |

## 데이터 흐름 한눈에

```text
사전진단 ─needs-map→ 의미축·군집·카드 ─┐
교재·강의·퀴즈 ─examen→ 기말 출제 초안   │
시험 시행 ─immersio→ 문항분석·학생보고서·이메일 ◀┘
학기 종료 ─retro-mester→ 차년도 개선 제안 → (다음 학기)
```

모든 모듈은 **Bronze → Silver → Gold** 데이터 계층과 **결정론**(같은 입력 →
같은 산출) 원칙을 공유한다. 자세한 배경은 [why_paideia.md](why_paideia.md) 참조.
</content>
