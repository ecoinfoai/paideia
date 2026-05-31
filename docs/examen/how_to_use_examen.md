# how_to_use_examen

> **examen v0.1.0** — module for deterministically drafting exam questions.
> (Latin *examen*: the tongue/needle of a balance → to weigh, to test; the
> origin of the English word "exam". Formerly named `gen-test`.)
> Builds a **final-exam draft** grounded in the textbook, lecture transcripts
> (STT), formative assessments, and quizzes.

The numeric, matching, and rule stages are all handled by deterministic code;
only question generation optionally uses an LLM. **Even when the external LLM is
unreachable, the deterministic stages run all the way to completion.**

---

## 1. At a glance

```bash
uv run --package examen examen build \
  --semester 2026-1 \
  --course   anatomy
```

- Console script: **`examen`**
- Subcommands: `ingest` · `plan` · `dry-run` · `generate` · `verify` · `build`
- Input: `data/bronze/examen/{semester}-{course}/`
- Output: `data/gold/examen/{semester}-{course}/runs/{run_id}/`

---

## 2. Subcommands

| Command | Stage | LLM | Description |
|---|---|---|---|
| `ingest` | Bronze→Silver | ✗ | Load textbook/STT/formative/quiz + aggregate emphasis |
| `plan` | Planning | ✗ | blueprint solver → slot allocation |
| `dry-run` | Bundle | ✗ | Produce generation-request bundles only (constitution check) |
| `generate` | Generation | ✓ | Bundle → question generation (cached) |
| `verify` | Verification | ✗ | format · groundedness · answer-key balance |
| `build` | Full | ✓ | ingest→plan→generate→verify→output |

### Common options

| Option | Required | Default |
|---|---|---|
| `--semester` | ✅ | — (e.g. `2026-1`) |
| `--course` | ✅ | — (e.g. `anatomy`) |
| `--blueprint` | — | `data/bronze/examen/{sem}-{course}/blueprint.yaml` |
| `--curriculum-map` | — | `data/bronze/examen/{sem}-{course}/curriculum_map.yaml` |
| `--backend` | — | `subscription` (or `api`) |
| `--no-emphasis` | — | off (ignore emphasis material — degrade test) |

### `build`-only

| Option | Default | Meaning |
|---|---|---|
| `--stt` | `data/stt` (when present) | Lecture-transcript STT directory |

**Backends**:
- `subscription` — via a Claude Code session (no env needed). Writes the bundle
  to staging and reads back the response.
- `api` — direct Anthropic SDK call (requires `ANTHROPIC_API_KEY`, temp=0).

---

## 3. Inputs (Bronze layout)

```text
data/bronze/examen/{semester}-{course}/
├── textbooks/                  # Textbook .txt — filename must contain "N장"
│   ├── 8장 호흡계통.txt
│   └── 9장 근육계통.txt ...
├── formative/                  # Formative assessment (required when source_mix.formative>0)
│   ├── Ch08_FormativeTest.yaml # glob: Ch*_FormativeTest.yaml
│   └── 형성평가_실제_출제문제들.txt   # ★ exact filename required
├── quiz/                       # Quizzes (required when source_mix.quiz>0)
│   └── QuestionUploadExcel_9주차.xls  # BIFF8 cp949, read with xlrd
├── blueprint.yaml              # ★ Required — exam specification
└── curriculum_map.yaml         # ★ Required — week→chapter→section mapping
```

STT (optional) lives at `data/stt/{분반}_{주차}_{차시}.txt`
(e.g. `1C_9주차_1차시.txt`). Some missing files only trigger a warning
(emphasis disabled), not a failure.

### blueprint.yaml

```yaml
semester: "2026-1"
course_slug: "anatomy"
exam_name: "2026-1학기 기말고사"
total_items: 48                 # range [40, 50] — out of range → exit 2
chapters:                       # chapter names must match curriculum_map
  - "8장. 호흡계통"
  - "9장. 근육계통"
difficulty_targets:             # sum ≈ 1.0
  easy: 0.45
  medium: 0.35
  hard: 0.20
source_mix:                     # sum = total_items; formative must match exactly
  formative: 12
  quiz: 15
  textbook: 21
answer_key_balance: true        # answer numbers 1–5 balanced + ≤2 in a row
```

### curriculum_map.yaml

```yaml
semester: "2026-1"
course_slug: "anatomy"
entries:
  - week: 9
    chapter_no: 8
    chapter: "8장. 호흡계통"
    sections: ["호흡기의 구조와 기능", "호흡운동", "가스교환과 운반"]
```

> **A filename typo is not a silent skip — it fails immediately (exit 2).**
> A textbook file `호흡계통.txt` (no chapter number), a formative file
> `형성평가_실제문제.txt` (typo), a quiz file `9주차_퀴즈.xls` (pattern
> mismatch), and the like are all unrecognized.

---

## 4. Pipeline

```text
[1] INGEST (deterministic)  textbook clean·chunk·EvidenceIndex / formative·quiz parse / STT emphasis aggregation
                            → ingest_report.json
[2] PLAN (deterministic)    blueprint solver → slot allocation (greedy) + curriculum_map join
[3] GENERATE (LLM)          formative→choices / quiz→variants / textbook→new. SHA256 cache
[4] VERIFY (deterministic)  groundedness anchors / choice length / duplicates / explanation length / answer-key balance
[5] OUTPUT (deterministic)  xlsx·yaml·manifest·quality report (atomic write)
```

**Cache**: `data/silver/examen/{semester}-{course}/cache/{sha256}.json`.
On a cache hit the LLM is not called → re-runs are byte-identical.

---

## 5. Output (`data/gold/examen/{semester}-{course}/runs/{run_id}/`)

`run_id` = the first 16 characters of the input-bundle SHA-256 (same input →
same path, idempotent).

| File | Contents |
|---|---|
| `기말출제초안.xlsx` | Flattened for review (28 columns: number · source · chapter · difficulty · question · choices 1–5 · answer · evidence, etc.) |
| `기말출제초안.yaml` | Full version (nested, including per-choice distractor rationale and textbook-evidence locations) |
| `출제품질리포트.md` | Measured vs. target (chapter · difficulty · answer-number · evidence distributions) |
| `manifest_examen.json` | Input hashes · cache rate · backend · distribution statistics |
| `ingest_report.json` | STT/formative/quiz/textbook loading results |

---

## 6. Usage examples

```bash
# Everything at once (recommended)
uv run --package examen examen build --semester 2026-1 --course anatomy --stt data/stt

# Step-by-step debugging
uv run --package examen examen ingest  --semester 2026-1 --course anatomy
uv run --package examen examen plan    --semester 2026-1 --course anatomy
uv run --package examen examen dry-run --semester 2026-1 --course anatomy   # without the LLM
uv run --package examen examen generate --semester 2026-1 --course anatomy
uv run --package examen examen verify  --semester 2026-1 --course anatomy

# API backend (fast on a cache hit)
uv run --package examen examen build --semester 2026-1 --course anatomy --backend api

# Reset the cache
rm -rf data/silver/examen/2026-1-anatomy/cache/
```

---

## 7. Exit codes

| Code | Condition |
|---|---|
| 0 | Success |
| 2 | Input/configuration validation failed (missing required input, blueprint range violation, textbook file not found) |
| 3 | Generation/verification failed (subscription response not provided, LLM error) |
| 4 | Failed to reach the LLM backend (`--backend api` only) |

---

## 8. Common pitfalls

| Symptom | Cause | Fix |
|---|---|---|
| `FileNotFoundError` (exit 2) | Textbook/formative/quiz filename typo or missing | Recheck the filename conventions (§3) |
| blueprint rejected (exit 2) | `total_items` ∉ [40,50], or `source_mix.formative` ≠ actual formative count | Edit blueprint.yaml |
| generate hangs (exit 3/4) | Subscription response not provided / no API key | Generate the bundle response, or set `ANTHROPIC_API_KEY` |
| Quiz not read | `.xlsx` / wrong encoding | BIFF8 `.xls` + cp949 are required |
| Emphasis not applied | STT missing or `--no-emphasis` | Point to the path with `--stt data/stt` |

---

## Related documents

- Prerequisite diagnosis: [needs-map](../needs-map/how_to_use_needs-map.md)
- Post-exam analysis: [immersio](../immersio/how_to_use_immersio.md)
- Design philosophy: [why_paideia](../why_paideia.md)
