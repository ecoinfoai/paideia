# Tutorial — A Full Semester, Start to Finish

This tutorial uses a fictional course, **"Human Structure and Function"
(`2026-1-anatomy`)**, as an example and runs paideia's three completed
modules in **semester time order**.

```text
Term start   needs-map     pre-diagnostic analysis → semantic axes, clusters, one-card-per-student
Midterm      examen        textbooks, lectures, quizzes → final-exam draft
Post-exam    immersio      exam results → item analysis, student reports, email
Term end     retro-mester  (in development)
```

> This tutorial assumes you have completed the installation and font setup in
> [quickstart.md](quickstart.md). All commands are run from the repository
> root (`paideia/`).

---

## Shared Conventions

- Semester-course key: `2026-1-anatomy` (= `{semester}-{course}`)
- Data layers: `data/{bronze,silver,gold}/{module}/2026-1-anatomy/`
- Every module is **deterministic** — same input → same output.
- The LLM is an optional accelerator — without it, the deterministic stages still complete.

---

## Step 1 — needs-map: Pre-diagnostic Analysis Right After Term Start

Analyze the pre-diagnostic survey that students submit in the first week of
the semester to produce **learning-disposition semantic axes**, **clusters**,
and a **one-page feedback card per student**.

### 1.1 Place the Inputs

| Input | Location |
|---|---|
| Diagnostic responses (Silver) | `data/silver/immersio/2026-1-anatomy/diagnostic_response.parquet` |
| Student roster (Silver) | `data/silver/immersio/2026-1-anatomy/student_master.parquet` |
| Diagnostic mapping (YAML) | `data/bronze/매핑/anatomy.diagnostic.yaml` (`mapping_version: 2`) |

> The diagnostic-response and student-roster Silver files are produced by
> `immersio ingest` (Phase 0) from the survey CSV and attendance sheet. See
> Step 3.1.

### 1.2 Run

```bash
uv run --package needs-map paideia-needs-map run \
  --semester 2026-1 \
  --course   anatomy
```

For an air-gapped network or a fast run, turn off external calls:

```bash
uv run --package needs-map paideia-needs-map run \
  --semester 2026-1 --course anatomy --no-llm --no-roberta
```

### 1.3 Output

```text
data/silver/needs-map/2026-1-anatomy/
  scale_reliability.parquet   factor_scores.parquet
  cluster_assignment.parquet  free_text_categorization.parquet
data/gold/needs-map/2026-1-anatomy/
  group_distribution.pdf   cluster_summary.xlsx
  needs-map_manual.pdf     cards/{학번}.pdf      ← one card per student
```

`factor_scores.parquet` and `cluster_assignment.parquet` become the
**input to Step 3's immersio combined analysis (Phase 3)**. This is where the
flow continues.

➡ Detailed flags: [how_to_use_needs-map.md](needs-map/how_to_use_needs-map.md)

---

## Step 2 — examen: Final-Exam Draft

Deterministically produce a final-exam draft grounded in textbooks, lecture
transcripts (STT), formative assessments, and quizzes.

### 2.1 Place the Inputs (`data/bronze/examen/2026-1-anatomy/`)

```text
textbooks/8장 호흡계통.txt ...          # textbooks (filename must contain "N장")
formative/Ch08_FormativeTest.yaml ...   # formative assessment (optional)
formative/형성평가_실제_출제문제들.txt  # exact filename required
quiz/QuestionUploadExcel_9주차.xls ...  # quizzes (BIFF8 cp949, optional)
blueprint.yaml                          # exam specification (required)
curriculum_map.yaml                     # week→chapter→section mapping (required)
```

> **A typo in a filename = immediate failure (exit 2).** examen does not
> silent-skip.

### 2.2 Run

```bash
# Full pipeline (ingest → plan → generate → verify → output)
uv run --package examen examen build \
  --semester 2026-1 --course anatomy

# Or step by step (for debugging)
uv run --package examen examen ingest  --semester 2026-1 --course anatomy
uv run --package examen examen plan    --semester 2026-1 --course anatomy
uv run --package examen examen dry-run --semester 2026-1 --course anatomy  # bundle only, no LLM
uv run --package examen examen generate --semester 2026-1 --course anatomy # calls the LLM
uv run --package examen examen verify  --semester 2026-1 --course anatomy
```

### 2.3 Output

```text
data/gold/examen/2026-1-anatomy/runs/{run_id}/
  기말출제초안.xlsx   기말출제초안.yaml
  출제품질리포트.md   manifest_examen.json   ingest_report.json
```

The instructor reviews and edits `기말출제초안.xlsx` (the final-exam draft)
to finalize the actual exam.

➡ Detailed flags and blueprint schema: [how_to_use_examen.md](examen/how_to_use_examen.md)

---

## Step 3 — immersio: Post-Exam Result Interpretation and Feedback

After administering the exam, take the OMR results, analyze item quality,
produce per-student tailored reports, and send them by email. It also performs
a combined analysis with the needs-map diagnostics.

immersio is divided into four phases.

### 3.1 Phase 0 — ingest (Bronze → Silver)

Normalize the survey, OMR, attendance sheet, and exam questions into four
Silver files.

```bash
uv run --package immersio immersio ingest \
  --bronze-dir data/bronze \
  --mapping    data/bronze/매핑/anatomy.diagnostic.yaml \
  --output-key 2026-1-anatomy
```

Output: `data/silver/immersio/2026-1-anatomy/{student_master, diagnostic_response,
exam_result, exam_item}.parquet`
(of these, the first two are the **input to Step 1's needs-map**.)

### 3.2 Phase 1+2 — analyze (exam quality + student metrics)

```bash
uv run --package immersio immersio analyze \
  --semester 2026-1 --course anatomy
```

Output (Gold): `시험분석결과.xlsx` (exam-analysis results, 7 sheets) ·
`시험품질보고서.{md,pdf}` (exam-quality report) · `figs/fig{1,2}_*.png`

### 3.3 Phase 3 — combine (diagnostics × exam)

Join the clusters and factor scores from needs-map (Step 1) with the exam
results to analyze correlation and regression.

```bash
uv run --package immersio immersio combine \
  --semester 2026-1 --course anatomy \
  --silver-dir data/silver --gold-dir data/gold \
  --include-cluster --include-subgroup
```

Output (Gold): `결합분석보고서.{md,pdf}` (combined-analysis report) ·
`결합분석.xlsx` (combined analysis) · `figs/fig{3,4,5,6}_*.png`

### 3.4 Phase 6 — email (sending per-student reports)

Send each student's PDF via the Gmail API. The safe order is **dry-run
first**, then self-test, and finally the real send.

```bash
# (1) dry-run — zero Gmail calls, generates .eml previews only
uv run immersio email \
  --profile kjeong --semester 2026-1 --course anatomy \
  --exam-name "기말고사"

# (2) self-test — sends 5 messages to the operator only (zero reach to students)
uv run immersio email \
  --profile kjeong --semester 2026-1 --course anatomy \
  --exam-name "기말고사" --self-test 5 --send

# (3) real send — sends to students after passing the confirmation gate (yes/no)
uv run immersio email \
  --profile kjeong --semester 2026-1 --course anatomy \
  --exam-name "기말고사" --send
```

> A dry-run writes to `*_dryrun.csv/md` while a real send writes to `*.csv/md`,
> so the **log files are kept separate**. Contamination of the send log is
> blocked at the source.

➡ Detailed subcommands and email semantics: [how_to_use_immersio.md](immersio/how_to_use_immersio.md)

---

## Step 4 — retro-mester: Semester Retrospective (in development)

When the semester ends, retro-mester reflects on the needs-map (start) and
immersio (end) data and proposes **3–5 changes to next year's course design**,
along with their priorities. It is still in development, and its output is left
in a form that the following year's needs-map can cite.

➡ [how_to_use_retro-mester.md](retro-mester/how_to_use_retro-mester.md)

---

## End-to-End Flow Summary

```text
[설문 CSV·출석부]
   │ immersio ingest (Phase 0)
   ▼
student_master.parquet ─┐
diagnostic_response.parquet ─┤ paideia-needs-map run (Step 1)
   ▼                          ▼
exam_result/exam_item   factor_scores / cluster_assignment
   │ immersio analyze         │
   ▼ (Phase 1+2)              │
시험분석결과.xlsx             │
   │ immersio combine ◀───────┘ (Phase 3: 진단 × 시험)
   ▼
결합분석보고서 → immersio email (Phase 6) → 학생 발송
   │
   ▼ retro-mester (학기말)
차년도 수업 설계 제안 → (다음 학기 needs-map)
```

[examen](examen/how_to_use_examen.md) runs in parallel with this flow,
producing question drafts from textbooks and lecture materials **at the time
of generating** midterm/final exams.

---

## What to Read Next

- Per-module details: [needs-map](needs-map/how_to_use_needs-map.md) ·
  [examen](examen/how_to_use_examen.md) ·
  [immersio](immersio/how_to_use_immersio.md)
- Design philosophy: [why_paideia.md](why_paideia.md)
