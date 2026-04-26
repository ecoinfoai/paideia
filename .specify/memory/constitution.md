<!--
SYNC IMPACT REPORT
==================
Version change: (template, unversioned) → 1.0.0
Bump rationale: MAJOR — initial ratification; all principles are newly defined,
                no prior version exists to amend.

Modified principles: n/a (initial ratification)

Added sections:
  - Core Principles (5 principles)
  - Technical Standards & Constraints
  - Development Workflow & Quality Gates
  - Governance

Removed sections: n/a (placeholders only in template)

Templates aligned:
  ✅ .specify/templates/plan-template.md — "Constitution Check" section reads
     constitution dynamically; no edit needed.
  ✅ .specify/templates/spec-template.md — user-value focus; no principle-specific
     edit needed.
  ✅ .specify/templates/tasks-template.md — generic task structure; aligned.
  ✅ .specify/templates/checklist-template.md — generic; aligned.
  ✅ .specify/templates/agent-file-template.md — generic; aligned.

Follow-up TODOs: none.
-->

# Paideia Constitution

Paideia는 한 교수자가 한 교과목의 학기 전 주기(사전진단 → 출제 → 형성평가 → 시험 →
결과해석 → 회고)를 데이터로 닫힌 루프로 운영하기 위한 6개 모듈 통합 시스템이다.
본 헌장은 paideia 우산과 모든 모듈(needs-map · maieutica · formative-analysis ·
gen-test · immersio · retro-mester)에 공통 적용되며, 모듈별 idea 문서 또는 spec과
충돌할 경우 본 헌장이 우선한다.

## Core Principles

### I. Deterministic-First with Optional LLM (NON-NEGOTIABLE)

수치·통계·매칭·룰 기반 분류는 모두 결정론적 코드로 구현해야 한다(MUST). LLM 사용은
사전에 결정론적으로 산출된 결과를 자연어로 다듬는 단계에 한정한다. LLM이 관여하는
모든 산출물은 룰 기반 또는 템플릿 폴백을 동반해야 하며(MUST), 어떤 환경에서 LLM API에
도달할 수 없어도 파이프라인이 끝까지 완주해야 한다.

**Rationale**: 학생 면담 우선순위·1인 1장 카드 등 학습자 운영 결정의 사실 근거가
재현·감사 가능해야 한다. 또한 학내 망·예산·API 가용성 등 외부 요인이 분석을 막지
않도록 운영 독립성을 보장해야 한다.

### II. Bronze → Silver → Gold with Pydantic Contracts (NON-NEGOTIABLE)

모든 데이터는 세 레이어를 따라 흐른다: **Bronze**(원시·불변·gitignored),
**Silver**(정제·표준화), **Gold**(운영 산출물). 모듈은 다른 모듈의 Silver/Gold만
소비해야 하며(MUST) Bronze를 직접 공유해서는 안 된다(MUST NOT). 모듈 간 데이터
계약은 `paideia_shared.schemas`(Pydantic v2)에서 권위 있게 관리되며, 입력·출력은
모듈 경계에서 명시적으로 검증되어야 한다(MUST). 검증 실패 시 보고는 위반 위치(파일·
행·컬럼·기대값/실제값)를 포함해야 한다(MUST).

**Rationale**: 6개 모듈이 닫힌 루프로 결합하려면 계약이 안정적이고 검증이 모듈
경계에서 이루어져야 한다. 침묵 누락이 학생 진단 결과로 흘러들면 신뢰가 붕괴된다.

### III. Variability via Configuration, Not Code

교과목·교수자·평가 도구별 변동성은 외부 설정(YAML 매핑, 템플릿 파일)으로 흡수해야
한다(MUST). 코드는 교과목별 컬럼명, 문항 텍스트, 분반 라벨, 시트명 등 가변 식별자를
하드코딩해서는 안 된다(MUST NOT). 새 교과목·새 학기 적용은 설정 추가만으로
가능해야 하며, 코드 분기·복제는 변동성 흡수 수단으로 허용되지 않는다.

**Rationale**: 한 교과목에서 검증된 모듈을 다른 교과목·다른 교수자가 재사용할 수
있어야 paideia가 도구로서 의미를 갖는다. 코드 분기로 변동성을 처리하면 매 학기
모듈이 갈라져 유지비용이 폭증한다.

### IV. Student-Individual as the Terminal Output

각 모듈의 종착 산출물은 학생 개인 단위여야 한다(MUST): 1인 1장 카드, 학생별 라벨,
개인 코칭 멘트, 개인 회고 시드. 집단·문항·챕터 통계는 중간 산출이거나 개인 단위
판단을 보조하는 부속 산출이며 단독 종착 산출물이 아니다. 단, 시험 품질 보고서·
출제 캘리브레이션 보고서 등 교수자 자기 점검을 목적으로 한 집단·문항 단위 산출은
허용된다.

**Rationale**: paideia가 OEA(기관 단위)·OnTask(메시지)와 구분되는 핵심은 "한 학생
한 학생의 형성"에 환류하는 것이다. 종착이 학생 개인이어야 모듈 설계가 그 방향으로
정렬된다.

### V. Privacy, Reproducibility, and Audit Stewardship

학생 PII(학번·이름·자유서술 응답·진단 응답)는 버전 관리에 포함되어서는 안 된다
(MUST NOT). `data/`는 gitignored여야 한다(MUST). 비밀키·API 토큰·기관 식별자는
agenix로 관리하며 하드코딩·커밋이 금지된다(MUST NOT). 모든 Silver/Gold 산출물은
manifest(입력 식별자·해시, 매핑/설정 식별자, 생성 시각, 산출 행수 요약)를 동반해야
하며(MUST), 사후에 어떤 입력으로부터 어떤 변환을 거쳐 생성되었는지 추적 가능해야
한다.

**Rationale**: 한국 개인정보보호법(PIPA)·교내 RISE 사업 거버넌스·학습자 보호 윤리
모두 충족이 필수. 또한 학기 회고·차년도 출제 의사결정에 산출이 사용되므로 산출의
출처가 사후 추적 가능해야 한다.

## Technical Standards & Constraints

**언어 표준**:
- 주 언어: **Python 3.11** (uv로 패키지 관리, pyproject.toml workspace)
- 보조 언어: **Julia 1.10+** (통계·군집 일부에 한해 선택)
- 환경: 모든 모듈 **flake.nix devShell**(NixOS·Gentoo 친화). 시스템 패키지 관리자
  의존 명령(apt/dnf/yum 등) 금지

**핵심 의존성**:
- **Pydantic v2** — 모듈 간 데이터 계약. 신규 계약은 `paideia_shared.schemas`에 추가
- **pandas / polars** — 표 처리
- **scikit-learn** — 군집·회귀
- **matplotlib / plotnine** — 그래프
- **reportlab / weasyprint** — PDF 생성
- **anthropic / openai SDK + instructor** — LLM 호출(모듈별 옵션, 폴백 필수)
- **pytest + hypothesis** — 테스트
- **agenix** — 비밀키 관리

**디렉터리 규약**:
- `data/{bronze,silver,gold}/` — 데이터 레이어. 전체 gitignored
- `modules/{module-name}/` — 모듈 코드·문서·템플릿
- `shared/paideia_shared/schemas/` — 공유 데이터 계약(Pydantic 모델)
- `specs/{NNN-feature}/` — speckit 사양·계획·태스크
- `.specify/memory/constitution.md` — 본 헌장(권위 있는 위치)

**산출 결정론**:
- 동일 Bronze + 동일 설정 → 동일 Silver/Gold 산출(byte-level reproducibility 지향)
- 비결정 요소(난수·시각·환경 의존)는 명시적 seed 또는 manifest에 기록
- 부분 산출 금지: 검증 실패 시 산출은 일절 작성하지 않는다(원자성)

## Development Workflow & Quality Gates

**테스트 정책**:
- 테스트 우선(TDD) 필수: 실패하는 테스트 → 최소 구현(GREEN) → 리팩터(MUST)
- 모든 함수 파라미터·반환에 type annotation
- 에러 메시지·docstring(Google 스타일)은 영어, 변수·주석은 한글 허용

**페일패스트(Fail-Fast)**:
- 함수 진입에서 입력 검증
- `except: pass`, silent return 금지(MUST NOT)
- 위반 보고는 위치(파일·행·컬럼)·기대값/실제값 포함

**커밋·리뷰**:
- Conventional Commits: `type(scope): description`
- 비밀키·PII 커밋 금지(pre-commit 훅으로 차단 권장)
- 헌장에 영향이 있는 변경(설계 원칙·계약·디렉터리 규약)은 PR 본문에 헌장 조항 인용

**Speckit 통합**:
- `/speckit.specify` → spec 작성
- `/speckit.clarify` → 모호성 해소(plan 전 권장)
- `/speckit.plan` → 구현 계획. **Constitution Check** 게이트 필수: plan 생성 전·후
  본 헌장 5개 원칙 위반 여부 검토
- 헌장 위반이 정당화되어야 하는 경우 plan의 Complexity Tracking에 명시(이유 + 더
  단순한 대안이 거부된 근거)

## Governance

**권위 (Authority)**:
- 본 헌장은 paideia 우산과 모든 모듈에 우선 적용된다
- 사용자 글로벌 CLAUDE.md(언어 선호·도구 환경)는 본 헌장과 직교적으로 적용
- 모듈별 idea/spec과 충돌 시 본 헌장이 우선

**개정 절차 (Amendment Procedure)**:
- 모든 개정은 PR 형태로 제출하며 PR 설명에 (1) 변경 동기, (2) 영향 범위, (3) 후속
  조치(템플릿·문서·진행 중 plan)를 명시
- 최소 1인 검토 후 머지(현재는 단일 사용자 운영이므로 자기 검토 시 24시간 숙성 권장)
- 머지 시 `Last Amended` 갱신 + Sync Impact Report(헌장 상단 HTML 주석) 갱신

**버전 정책 (Versioning)**:
- 시맨틱 버전(MAJOR.MINOR.PATCH)
  - **MAJOR** — 원칙 제거·재정의·역호환 깨는 거버넌스 변경
  - **MINOR** — 신규 원칙·신규 섹션·실질적 가이드 확장
  - **PATCH** — 명료화·문구 수정·오타·비의미적 정련
- 버전 분류가 모호하면 PR 설명에 분류 근거 명시 후 머지

**컴플라이언스 검토**:
- 모든 PR 리뷰 시 영향 범위가 본 헌장과 교차하면 명시적으로 원칙 준수를 확인
- `/speckit.plan`은 Constitution Check 게이트를 반드시 수행
- 위반 정당화는 Complexity Tracking 표에 기록

**개정 이력**:
- 본 헌장의 모든 변경은 git history와 Sync Impact Report(상단 주석)로 추적

**Version**: 1.0.0 | **Ratified**: 2026-04-26 | **Last Amended**: 2026-04-26
