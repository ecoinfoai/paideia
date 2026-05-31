# Why paideia (why_paideia)

> **paideia (παιδεία)** — an ancient Greek word meaning the cultivation of
> the whole person, the formation of character and culture through education.
> It captures, in a single word, the educational cycle of **diagnosing,
> teaching, assessing, and reflecting on** students over a semester in order
> to prepare for the next one.

---

## 1. What Problem Does It Solve?

Running a single university course for one semester generates the following
data, which tends to pile up scattered and disconnected:

- Pre-diagnostic survey responses
- Lecture transcripts (STT) and teaching materials
- Formative assessments and quizzes
- Midterm and final exam scores and OMR sheets
- Student feedback and grading materials
- Retrospective notes for improving the course next year

In practice, most of this data ends up **buried, never analyzed**. Every
semester the instructor repeats the same manual work (tallying scores,
analyzing items, writing reports, sending emails) and never has time to give
each individual student tailored feedback.

**paideia automates and standardizes this entire flow.**

---

## 2. Core Design Principles

Every module in paideia shares the following five principles.

### (1) Determinism
Same input → same output (byte-identical). All random seeds are fixed, and
timestamps are injected explicitly. Because results don't drift when you run
it twice, the outputs are **reviewable, reproducible, and auditable**.

### (2) Data Lake Layering (Bronze → Silver → Gold)
- **Bronze** — raw as-is (survey CSVs, OMR `.xls`, textbook `.txt`, lecture STT).
- **Silver** — normalized intermediate output (`*.parquet`). The exchange format between modules.
- **Gold** — final, human-facing output (`xlsx` / `md` / `pdf` / `png`).

Each module takes the Silver/Gold output of a previous module as input and
produces the next set of outputs.

### (3) Module Independence
Each module is **runnable on its own** and operates in a degraded mode even
when another module's output is absent. (For example, even without needs-map
results, immersio still completes its exam analysis end-to-end and simply
leaves the diagnostic-linkage columns as N/A.)

### (4) Korean First
All outputs (PDF, xlsx, md) are in Korean. The NanumGothic font is required.
No output is produced with broken Korean glyphs.

### (5) A Single uv-workspace Monorepo
One repository, with an independent package per module. Dependencies are
managed centrally from the umbrella.

---

## 3. The Semester's Timeline = the Module Lineup

paideia maps the **temporal flow** of a semester directly onto its modules.

| Order | Module | Role | Input | Output | Status |
|---|---|---|---|---|---|
| 1 | **needs-map** | Pre-diagnostic analysis | Diagnostic survey responses | Semantic-axis scores, clusters, one-card-per-student | ✅ Shipped |
| 2 | **examen** | Final-exam generation | Textbooks, STT, formative assessments, quizzes | Final-exam draft | ✅ Shipped |
| 3 | **immersio** | Exam result interpretation + per-student reports | Exam scores, items | Item analysis, student reports, email | ✅ Shipped |
| 4 | **metric-codex** | Standard dictionary of assessment metrics | (Shared reference across modules) | Metric definitions, calculation-rule dictionary | 🚧 Idea stage |
| 5 | **retro-mester** | Semester retrospective, next-year improvement | Output of all modules | Retrospective report, improvement proposals | 🚧 Idea stage |

---

## 4. Data Flow (Over One Semester)

```text
    [사전진단 설문]
         ↓ needs-map
    [의미축·군집·카드] ──────────────┐
         ↓                          │
    [강의·형성평가·퀴즈]              │
         ↓ examen                    │
    [기말 출제 초안]                 │
         ↓                          │
    [중간·기말고사 시행]              │
         ↓ immersio                  │
    [문항분석·학생보고서·이메일] ◀────┘
         ↓
    [학기 종료]
         ↓ retro-mester
    [회고·차년도 개선 제안]
         ↓ (다음 학기)
    [needs-map ...]
```

The **causal chain** of diagnosis (needs-map) → question generation (examen)
→ results (immersio) runs in a single line, and when the semester ends,
retro-mester reflects on all of it and loops back to the input design for the
next semester's needs-map. The cycle is closed.

---

## 5. Tech Stack

- **Python 3.11** (uv workspace, paideia umbrella)
- **Contracts**: pydantic ≥ 2.6
- **Data**: pandas ≥ 2.0 + pyarrow ≥ 15 (Silver parquet, with determinism options fixed)
- **Statistics**: scipy · scikit-learn · statsmodels
- **Visualization**: matplotlib (figs, dpi=150, `Software=paideia` metadata)
- **Document output**: reportlab (PDF) · openpyxl (xlsx)
- **LLM**: anthropic SDK + instructor (structured output; with fallback and caching)
- **Storage**: local filesystem (Bronze → Silver → Gold)

The LLM is an **optional accelerator**. The system is designed so that the
deterministic stages run to completion even when an external LLM cannot be
reached.

---

## 6. Who Uses It

- **Operated by**: Busan Health University (bhug.ac.kr)
- **Pilot**: a single course, "Human Structure and Function"
- **Expansion**: multi-course rollout planned

---

## Further Reading

- New here? → [quickstart.md](quickstart.md) (your first output in 5 minutes)
- Want to follow a full semester start to finish? → [tutorial.md](tutorial.md)
- Detailed per-module usage → each module folder's `how_to_use_*.md`
