# paideia Documentation (docs)

The official documentation for a suite of modules that connects the full
lifecycle of running a semester-long course — **pre-diagnostic → question
generation → result interpretation → retrospective** — into a closed,
data-driven loop.

## Getting Started

| Document | Who it's for |
|---|---|
| [why_paideia.md](why_paideia.md) | What paideia is and why it was built — for first-time readers |
| [quickstart.md](quickstart.md) | See your first output in 5 minutes — install and run |
| [tutorial.md](tutorial.md) | A hands-on walkthrough of a full semester, start to finish |

## Module Usage Guides

| Module | Role | Status | Docs |
|---|---|---|---|
| **needs-map** | Pre-diagnostic analysis (semantic axes, clusters, one-card-per-student) | ✅ Shipped | [how_to_use_needs-map.md](needs-map/how_to_use_needs-map.md) |
| **examen** | Deterministic generation of final-exam question drafts | ✅ Shipped | [how_to_use_examen.md](examen/how_to_use_examen.md) |
| **immersio** | Exam result interpretation + per-student reports + email | ✅ Shipped | [how_to_use_immersio.md](immersio/how_to_use_immersio.md) |
| **maieutica** | Weekly quiz / formative-assessment candidate generation | 🚧 In development | [how_to_use_maieutica.md](maieutica/how_to_use_maieutica.md) |
| **formative-analysis** | Weekly formative-assessment administration and analysis | 🚧 Integration planned | [how_to_use_formative-analysis.md](formative-analysis/how_to_use_formative-analysis.md) |
| **retro-mester** | Semester retrospective → next-year course design | 🚧 In development | [how_to_use_retro-mester.md](retro-mester/how_to_use_retro-mester.md) |
| **metric-codex** | Student-centered learning-competency accumulation and querying (downstream project) | 🚧 In development | [how_to_use_metric-codex.md](metric-codex/how_to_use_metric-codex.md) |

## Data Flow at a Glance

```text
사전진단 ─needs-map→ 의미축·군집·카드 ─┐
교재·강의·퀴즈 ─examen→ 기말 출제 초안   │
시험 시행 ─immersio→ 문항분석·학생보고서·이메일 ◀┘
학기 종료 ─retro-mester→ 차년도 개선 제안 → (다음 학기)
```

Every module shares the **Bronze → Silver → Gold** data layering and the
principle of **determinism** (same input → same output). For the full
background, see [why_paideia.md](why_paideia.md).
