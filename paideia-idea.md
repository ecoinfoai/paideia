# Paideia — 한 교과목의 학기 전 주기 데이터 시스템

> 한 교수자가 한 교과목을 데이터로 닫힌 루프(closed-loop)로 운영하면서,
> 학생 개개인의 형성(παιδεία, formation)에 환류하는 통합 시스템.

---

## 0. 프로젝트 정체성

### 0.1 한 줄 정의
**사전진단 → 출제 → 형성평가 → 시험 → 결과해석 → 학기회고**를 하나의 데이터 사이클로 연결하는 6개 모듈의 통합 도구.

### 0.2 이름의 유래
**Paideia**(παιδεία)는 그리스 고전어로 "한 인간을 인간답게 형성하는 교육 전체"를 의미한다. 베르너 예거(Werner Jaeger)의 『Paideia』로 정전화. 본 프로젝트가 점수·정답률만이 아니라 학생의 동기·불안·생활맥락까지 보고 형성에 환류하려는 지향과 부합한다. 모듈명 **maieutica**(산파술), **immersio**(몰입)와 같은 고전어 톤을 유지한다.

### 0.3 차별점 (기존 도구 대비)
가장 가까운 사례인 **OnTask**(Apereo, 오픈소스), **Open Education Analytics**(Microsoft), **Formative.com**(상용)을 조사한 결과 paideia만의 위치는 다음과 같다:

1. **사전진단(non-cognitive)와 시험성적 결합 분석** — motivation·anxiety·perceived control이 학업성취의 강력한 예측변수임은 학술적으로 입증되었으나(Tandfonline 2023 longitudinal 등), 이를 한 학기 운영 도구로 통합한 오픈 시스템은 발견되지 않음
2. **1인 1장 PDF 카드** — OnTask는 메시지(텍스트), paideia는 시각적 카드 산출물
3. **한국어 자유서술 분석** 내장
4. **6개 모듈로 학기 전 주기를 닫음** — 기존 도구는 모두 단일 단계만 다룸
5. **출제(maieutica·gen-test)부터 회고(retro-mester)까지** 하나의 시스템으로 묶음

### 0.4 명시적 비목표 (Non-Goals)
- LMS 자체 구현 안 함 → CSV/Excel로 데이터 받음 (Moodle/Canvas와 경쟁 안 함)
- 학생 직접 인터페이스 없음 → 산출은 교수자가 해석/전달
- 실시간 메시지 발송 안 함 → 필요하면 OnTask와 연계
- 기관 단위 분석 안 함 → 한 교수자/한 교과목 단위 (OEA가 잘함)

이 비목표 선언이 scope creep을 막는다.

### 0.5 운영 철학
1. **수치·통계·매칭·룰 기반 분류는 전부 코드로 결정론적 처리** — 재현성·감사가능성 확보
2. **LLM은 "자연어를 다듬는 단계"에서만 선택적으로 사용** — 없어도 분석은 끝까지 완주
3. **LLM이 하던 일은 사전 정의된 룰 템플릿/키워드 사전으로 대체 가능**한 구조로 설계
4. **학생 맞춤형 산출물이 최종 목적**, 집단 통계는 그 보조

---

## 1. 6개 모듈 정의

### 1.1 needs-map — 사전진단 분석
- **무엇**: 수업 사전진단평가(요구조사)로 확보한 데이터를 분석해 학생 집단·개인 패턴 도출
- **입력**: 진단평가 응답 CSV (Likert·다중선택·자유서술 혼합)
- **출력**: 학생×변수 매트릭스, 군집 결과, 개인 카드 1차 자료
- **학기 시점**: 개강 직후 1–2주
- **의존성**: 없음 (학기 첫 모듈)
- **코드 vs LLM**: 척도 코딩·요인분석·군집화 = 코드. 자유서술 카테고리 분류 = 키워드 사전(코드) + LLM 옵션
- **상태**: 📋 계획 (immersio Phase 0–4의 진단 처리 부분이 prototype)

### 1.2 maieutica — 매주 퀴즈/형성평가 후보 생성
- **무엇**: 교재 텍스트로부터 매주 진행할 객관식 퀴즈 후보와 서술형 형성평가 후보 생성
- **입력**: 교재 챕터 텍스트 (PDF 추출 또는 마크다운)
- **출력**: 챕터별 객관식 후보 N개 + 서술형 후보 M개 (JSON, Pydantic 스키마 검증)
- **학기 시점**: 학기 전(전체) + 매주(점진)
- **의존성**: 교재
- **코드 vs LLM**: 텍스트 청킹·구조화 출력 검증 = 코드. 문항 생성 = LLM 필수
- **상태**: 📋 계획

### 1.3 formative-analysis — 매주 형성평가 시행·분석 ✅
- **무엇**: 매 주차 형성평가 시험지 생성 + 응답 결과 분석 + 개인별 보고서
- **입력**: maieutica가 생성한 서술형 후보 + 학생 응답
- **출력**: 시험지 PDF + 학생별 분석 보고서
- **학기 시점**: 학기 중 매주
- **의존성**: maieutica (또는 수기 입력)
- **위치**: `~/localgit/formative-analysis/`
- **상태**: ✅ 완성 (paideia 통합 시 모듈 디렉터리로 이전 예정)

### 1.4 gen-test — 시험 문제 초안 출제
- **무엇**: 교재 텍스트 + 강의 녹취록(분반별) 등을 활용해 시험범위 문제 초안 출제
- **입력**: 교재 + 분반별 녹취록 + 출제 사양(블룸 단계·난이도·문항수)
- **출력**: 시험 문제 초안 + 정답 + 출제 의도 메모
- **학기 시점**: 중간고사 전, 기말고사 전
- **의존성**: 교재, 녹취록
- **코드 vs LLM**: 출제 사양 검증·중복 검사 = 코드. 문제 생성 = LLM 필수
- **상태**: 📋 계획

### 1.5 immersio — 시험 결과 해석 + 맞춤형 보고서
- **무엇**: 시험 결과를 needs-map의 학생 개인 데이터와 결합 분석 → 시험문제 품질관리 + 학생별 상담지원 자료 + 시험결과 보고서 생성
- **입력**: 시험성적, needs-map 결과, 출석부, 시험 메타데이터
- **출력**: 1인 1장 PDF 카드 + 시험 품질 보고서 + 라벨링된 학생 명단(상담 우선순위)
- **학기 시점**: 중간고사 직후, 기말고사 직후
- **의존성**: needs-map, 시험 결과 데이터
- **코드 vs LLM**: 통계·라벨·카드 생성 = 코드. 코칭 멘트 자연어화 = LLM 옵션 (템플릿 폴백)
- **상태**: 🚧 v0.1 개발 시작 — **2026 1학기 중간고사부터 적용**

### 1.6 retro-mester — 학기 회고
- **무엇**: 한 학기 전체 결과로 수업 내용을 분석하고 차년도 수업 준비 시 고려사항 제시
- **입력**: 6개 모듈의 학기 산출물 일체
- **출력**: 3컬럼 회고 보고서(Do More / Changes to Prioritize / Issues to Consider) + 차학기 출제계획 시드
- **학기 시점**: 학기 종료 후
- **의존성**: 5개 모듈 모두
- **코드 vs LLM**: 데이터 집계·연도간 비교 = 코드. 회고 텍스트 = LLM 옵션
- **상태**: 📋 계획

### 1.7 모듈 의존성 그래프

```
needs-map ─────────────────────────────────────┐
                                                │
교재 ── maieutica ──── formative-analysis ─────┤
                                                │
녹취록 ── gen-test ──── (시험 시행) ──────── immersio
                                                │
                                                ↓
                                          retro-mester
                                                │
                                                ↓
                                       (차학기 시드 데이터)
```

---

## 2. 데이터 흐름 — Bronze / Silver / Gold

Open Education Analytics(OEA)의 데이터 레이어 명명을 차용한다.

| 레이어 | 의미 | 예시 |
|---|---|---|
| **Bronze** | 원시 데이터, 불변 | 진단평가 응답 CSV, 시험성적 Excel, 출석부, 교재 PDF, 녹취록 텍스트 |
| **Silver** | 정제·표준화된 분석 가능 형태 | Likert 정수화, 학번 매칭된 학생×변수 매트릭스, 청킹된 교재 텍스트, 구조화된 문항 후보 JSON |
| **Gold** | 운영 가능한 최종 산출물 | 학생 라벨, 1인 1장 PDF 카드, 시험 품질 보고서, 회고 문서 |

**원칙**:
- 각 모듈은 다른 모듈의 Silver/Gold를 입력으로 받을 수 있다. Bronze는 직접 공유하지 않는다
- 모듈 간 계약은 **Pydantic 스키마**로 명시한다
- 디렉터리 구조도 `data/bronze/`, `data/silver/`, `data/gold/` 로 일관

---

## 3. 채택한 외부 아이디어 (v0.1)

조사 결과 4가지 아이디어를 채택한다. 모두 비용이 작고 6개 모듈의 기반 골격에 직접 기여한다.

### 3.1 OnTask식 "룰 + 미리보기" UX (immersio Phase 4)
교수자가 라벨 룰을 작성/조정할 때 "이 룰에 해당하는 학생 N명, 무작위 3건 미리보기" 출력. 룰 변경의 영향을 즉시 확인 가능. CLI 한 함수로 구현.

### 3.2 Bronze / Silver / Gold 데이터 레이어 (전 모듈)
2장에서 정의. 모듈 간 데이터 계약을 명료하게.

### 3.3 non-cognitive predictors 학술 근거 (needs-map 문서)
needs-map 항목 설계가 임의가 아닌 학술적 근거 위에 있음을 명시한다. 핵심 인용:
- *Cognitive and non-cognitive predictors of academic success in higher education* (Tandfonline 2023, longitudinal n=1681): motivation·learning strategies·domain knowledge가 가장 강력한 예측변수
- *Student Anxiety and Perception of Difficulty Impact Performance and Persistence* (CBE Life Sci Educ): 사전 불안 측정의 학업 성과 예측력

### 3.4 AutoQuizzer 패턴 — Pydantic JSON 구조화 출력 (maieutica)
maieutica의 LLM 출력은 반드시 Pydantic 스키마로 검증된 JSON. `instructor` 또는 LangChain `with_structured_output` 사용. 후속 모듈(formative-analysis, gen-test)이 안전하게 받을 수 있도록.

---

## 4. 향후 검토 (v0.2 이후)

| 시기 | 아이디어 | 도입 트리거 |
|---|---|---|
| v0.2 | Planning First, Question Second 2단계 출제 (출제 계획 → 문제 생성) | maieutica v0.1 운영 후 출제 품질 부족 확인 시 |
| v0.2 | Notre Dame 3컬럼 회고 양식 (Do More / Changes / Issues) | retro-mester 1차 가동 시 |
| v0.2 | OEA Responsible AI 원칙 5개 발췌 | 라벨 오해·민감 데이터 사고 사례 발생 시 |
| v0.3+ | py-irt — IRT 기반 시험 분석 | 시험 데이터 2–3학기 누적 후 |
| 보류 | ESM(Experience Sampling Method) | needs-map v0.1 효과 검증 후 |
| 보류 | 3-2-1 학생 회고 양식 | retro-mester 정착 후 |

---

## 5. 개발 로드맵

### v0.1 — 2026년 4–6월 (즉시 시작)
**목표**: 이번 중간고사 분석으로 immersio 가동 + needs-map 통합 입증

| 모듈 | v0.1 범위 |
|---|---|
| immersio | 중간고사 1회 분석 완주: Phase 0–6 (1인 1장 PDF 카드 184장 생성) |
| needs-map | immersio Phase 0의 진단 처리부를 분리한 prototype |
| formative-analysis | (이미 완성, 변경 없음) |
| maieutica | 초안 (한 챕터 객관식 10문항 후보 생성 가능) |
| gen-test | 보류 |
| retro-mester | 보류 |

**완료 기준**:
- 중간고사 카드 184장 출력
- 상담 신청자 라벨 대조 운영 가동
- 학생 5개 라벨(🔴🟡🟢⚪🔵) 분류 결과 검토

### v0.2 — 2026년 2학기
**목표**: 학기 전 주기 가동 (한 과목으로 6개 모듈 풀세트 운영)

| 모듈 | v0.2 범위 |
|---|---|
| needs-map | 정식 모듈화, CLI 제공, 다른 과목 적용 가능한 일반화 |
| maieutica | Planning First 2단계 출제, 매주 퀴즈 후보 자동 생성 |
| formative-analysis | maieutica 출력과 직접 연동 |
| gen-test | 초안 — 교재 + 녹취록 → 중간/기말 시험 초안 |
| immersio | 기말고사 + 중간고사 비교 분석, 학기 누적 추세 |
| retro-mester | 초안 — Notre Dame 3컬럼 회고 + 차학기 출제계획 시드 |

**완료 기준**: 한 과목의 학기 전체가 paideia만으로 운영됨

### v0.3 — 2027년 1학기
**목표**: 다과목 일반화 + 학기간 비교

- 과목·학기 메타데이터 표준화
- retro-mester가 학기간 비교 보고서 생성
- 학생 카드 양식 다양화
- Responsible AI 가드레일 도입 (학생 라벨 비공개 원칙·익명화·결정 근거 추적)

### v1.0 — 2027년 2학기 또는 2028년
**목표**: 외부 교수자 사용 가능한 안정화 + 문서화

- 다른 교수자가 매뉴얼만 보고 한 과목을 운영 가능
- IRT(py-irt) 도입 — 학기 누적 데이터 충분
- 패키지 배포 (PyPI) 또는 Docker 이미지
- Nix flake 공식화

### v2.0+ (장기 비전)
- 학과 단위 적용 (간호학과 전 과목)
- 다른 대학 적용 사례
- 학술 논문화 (한국 고등교육 학습분석 사례 연구)
- RISE 사업 성과로 연계

---

## 6. 기술 스택

- **Python 3.11** (uv) — 주 언어
- **Julia 1.10+** — 통계·군집화 일부 (선택)
- **Pydantic v2** — 모듈 간 데이터 계약
- **pandas / polars** — 표 처리
- **scikit-learn** — 군집화·회귀
- **matplotlib / plotnine** — 그래프
- **reportlab / weasyprint** — PDF 생성
- **anthropic / openai SDK** + `instructor` — LLM 호출 (모듈별 옵션)
- **flake.nix devShell** — 모든 환경
- **pytest** + **hypothesis** — 테스트
- **agenix** — 비밀키 관리 (하드코딩·커밋 금지)

코딩 규칙은 사용자 글로벌 CLAUDE.md를 따른다 (TDD, Fail-Fast, 타입 어노테이션, Conventional Commits 등).

---

## 7. 디렉터리 구조 (제안)

monorepo로 시작, v0.3에서 모듈별 독립성 평가:

```
paideia/
├── paideia-idea.md            # 본 문서
├── flake.nix
├── pyproject.toml             # uv workspace
├── modules/
│   ├── needs-map/
│   ├── maieutica/
│   ├── formative-analysis/    # ~/localgit/formative-analysis/ 흡수
│   ├── gen-test/
│   ├── immersio/
│   └── retro-mester/
├── shared/
│   ├── schemas/               # Pydantic 모델 (Silver/Gold 계약)
│   ├── data-layers/           # Bronze/Silver/Gold 디렉터리 규약
│   └── llm-utils/             # 구조화 출력·캐싱·재시도
└── docs/
    ├── responsible-ai.md      # v0.2 이후
    └── academic-references.md # non-cognitive 근거 등
```

현재는 작업 디렉터리가 `~/localgit/immersio/`이므로 immersio 모듈을 먼저 개발하고, **v0.2 시점에 `~/localgit/paideia/` 우산 디렉터리로 통합 이전**한다.

---

## 8. 즉시 다음 단계

1. **immersio v0.1 idea.md 갱신** — 본 paideia-idea.md를 기반으로 immersio 모듈 명세 재작성 (`idea/idea.md` → paideia 위상 반영하여 갱신)
2. **이번 중간고사 분석 가동** — immersio Phase 0–6 구현, 학생 184명 카드 출력
3. **needs-map 프로토타입 분리** — immersio Phase 0의 진단 처리부를 별도 모듈로 분리할 수 있는지 평가 (v0.2 분리를 염두)
4. **maieutica·gen-test·retro-mester는 v0.2로 연기**

---

이 문서는 paideia v0.1 시작 시점의 비전이며, **매 학기 운영 후 갱신한다**.

---
*작성: 2026-04-26*
