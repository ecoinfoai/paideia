<p align="center">
  <img src="idea/paideia_pipeline_eng.svg" alt="paideia pipeline: diagnose → teach → assess → reflect" width="100%">
</p>

# paideia

> **paideia (παιδεία)** — the ancient Greek word for the all-round formation and
> education of a person. The project takes a single university course through one
> full semester — **diagnose, teach, assess, reflect** — and feeds the results
> back into the next semester.

A full-cycle data system for running a single course over one semester. It
connects pre-diagnosis → exam authoring → result interpretation → retrospective
into a single closed data loop, automating and standardizing work that
instructors would otherwise repeat by hand every term.

📖 **Documentation:** https://ecoinfoai.github.io/paideia/

---

## Why paideia

Running a course for one semester scatters a lot of data — pre-diagnosis surveys,
lecture transcripts, formative tests and quizzes, exam scores and OMR sheets,
student feedback, and retrospective notes. In practice most of it is never
analyzed. paideia automates the whole flow and gives every student tailored
feedback that an instructor rarely has time to produce by hand.

See [docs/why_paideia.md](docs/why_paideia.md) for the full rationale.

---

## Design principles

Every module shares these five principles:

1. **Determinism** — the same input produces byte-identical output. All random
   seeds are fixed and timestamps are injected explicitly, so results are
   reproducible and auditable.
2. **Bronze → Silver → Gold data layers** — Bronze is raw input (survey CSVs, OMR
   `.xls`, textbook `.txt`, lecture STT); Silver is normalized intermediate output
   (`*.parquet`, the inter-module exchange format); Gold is human-facing final
   output (`xlsx` / `md` / `pdf` / `png`).
3. **Module independence** — each module runs standalone and degrades gracefully
   when another module's output is missing.
4. **Korean-first output** — all reports (PDF/xlsx/md) are in Korean; NanumGothic
   is required.
5. **Single uv-workspace monorepo** — one repository, independent per-module
   packages, dependencies managed by the umbrella.

---

## Modules

The modules mirror the timeline of a semester.

| Order | Module | Role | Status |
|---|---|---|---|
| 1 | **needs-map** | Pre-diagnosis analysis (semantic axes · clustering · one-page-per-student cards) | ✅ Shipped |
| 2 | **examen** | Deterministic drafting of final-exam questions | ✅ Shipped |
| 3 | **immersio** | Exam result interpretation + personalized student reports + email | ✅ Shipped |
| 4 | **maieutica** | Weekly quiz / formative-assessment candidate generation | 🚧 In development |
| 5 | **formative-analysis** | Weekly formative-assessment delivery and analysis | 🚧 Pending integration |
| 6 | **retro-mester** | Semester retrospective → next-year course design | 🚧 In development |
| — | **metric-codex** | Student-centric learning-record accumulation and query (downstream project) | 🚧 In development |

### Data flow over one semester

```text
[pre-diagnosis survey]
     │ needs-map
[semantic axes · clusters · cards] ─────┐
     │                                  │
[textbook · lectures · quizzes]         │
     │ examen                           │
[final-exam draft]                      │
     │                                  │
[midterm / final exams administered]    │
     │ immersio                         │
[item analysis · student reports · email] ◀┘
     │
     ▼ retro-mester
[retrospective · next-year improvements]
     │ (next semester)
     ▼
[needs-map ...]
```

---

## Tech stack

- **Python 3.11** (uv workspace, paideia umbrella)
- **Contracts**: pydantic ≥ 2.6
- **Data**: pandas ≥ 2.0 + pyarrow ≥ 15 (Silver parquet, deterministic options pinned)
- **Statistics**: scipy · scikit-learn · statsmodels
- **Figures**: matplotlib (dpi=150, `Software=paideia` metadata)
- **Document output**: reportlab (PDF) · openpyxl (xlsx)
- **LLM**: anthropic SDK + instructor (structured output; with fallback and cache)
- **Storage**: local filesystem (Bronze → Silver → Gold)

The LLM is an **optional accelerator** — the deterministic stages run to completion
even when no external LLM is reachable.

---

## Quick start

```bash
# Prerequisites: Python 3.11, uv, and the NanumGothic font (required for PDF/PNG output)
sudo apt install fonts-nanum && fc-cache -fv      # Ubuntu/Debian

git clone git@github.com:ecoinfoai/paideia.git
cd paideia
uv sync

# Verify the module CLIs
uv run --package examen   examen   --help
uv run --package immersio immersio --help
uv run --package needs-map paideia-needs-map --help
```

See [docs/quickstart.md](docs/quickstart.md) for a 5-minute first run, and
[docs/tutorial.md](docs/tutorial.md) to follow a full semester end to end.

---

## Repository layout

```text
paideia/
├── modules/
│   ├── needs-map/     # pre-diagnosis analysis
│   ├── immersio/      # result interpretation + reports + email
│   └── examen/        # exam authoring
├── shared/
│   └── paideia_shared/   # Pydantic schemas (Silver/Gold contracts), fonts, LLM utils
├── docs/              # documentation site (MkDocs Material → GitHub Pages)
├── idea/              # design notes for current and planned modules
├── mkdocs.yml
└── pyproject.toml     # uv workspace umbrella
```

---

## Documentation

The docs are built with MkDocs Material and published to GitHub Pages on every
push to `master` (see `.github/workflows/docs.yml`).

```bash
# Local preview
pip install -r docs/requirements.txt
mkdocs serve            # http://127.0.0.1:8000
```

Per-module usage guides live under `docs/<module>/how_to_use_<module>.md`.

---

## Status

Operated at Busan Health University (bhug.ac.kr), piloted on a single course
(Human Structure and Function), with multi-course expansion planned.
</content>
