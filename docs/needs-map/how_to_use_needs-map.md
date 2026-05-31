# how_to_use_needs-map

> **needs-map v0.1.x** — pre-diagnostic analysis module.
> Deterministically produces scale reliability, 8 quantitative semantic-axis
> scores, clustering, free-text classification/sentiment, a cohort distribution
> report, an operator manual, and **one feedback card per student**.

This is paideia's **first module**, run in the first one or two weeks of the
semester to derive cohort and individual patterns from pre-diagnostic (needs
survey) responses. Its outputs feed directly into immersio Phase 3 (combined
analysis) and the following year's retro-mester retrospective.

---

## 1. At a glance

```bash
uv run --package needs-map paideia-needs-map run \
  --semester 2026-1 \
  --course   anatomy
```

- Console script name: **`paideia-needs-map`** (pyproject `project.scripts`)
- Subcommand: `run`
- Input: `data/silver/immersio/{semester}-{course}/` + diagnostic mapping YAML
- Output: `data/{silver,gold}/needs-map/{semester}-{course}/`

---

## 2. Inputs (all 3 are Required)

If any one is missing or violates its contract, analysis stops (no partial
output).

| Input | Path | Contract |
|---|---|---|
| Diagnostic responses Silver | `data/silver/immersio/{semester}-{course}/diagnostic_response.parquet` | `DiagnosticResponse` |
| Student roster Silver | `data/silver/immersio/{semester}-{course}/student_master.parquet` | `StudentMaster` |
| Diagnostic mapping YAML | `data/bronze/매핑/{course}.diagnostic.yaml` | `DiagnosticMappingConfig` (**mapping_version: 2**) |

> The first two Silver files are produced by `immersio ingest` (Phase 0) from
> the survey CSV and the attendance roster.

### Mapping YAML v2 skeleton

```yaml
metadata:
  semester: '2026-1'
  course_slug: 'anatomy'
  course_name_kr: '인체구조와기능'
  mapping_version: 2            # ★ Required as of v0.1.1 (v1 rejected → exit 1)

columns:
  - source: 'student_id'
    kind: identity
  - source: 'Q1_digital_efficacy'
    kind: likert
    axis: digital_efficacy
    aggregate: mean
    ordinal_map: {'전혀 그렇지 않다.': 1, ..., '매우 그렇다.': 7}
  # ... motivation, time_availability, material_preference, study_strategy,
  #     study_environment, social_learning, feedback_seeking (all 8 axes required)
  - source: 'Q61_anxiety'
    kind: freetext
    axis: anxiety_freetext

axes:
  required:                     # Must contain exactly the 8 standard axes (both partial and extra are rejected)
    - digital_efficacy
    - motivation
    - time_availability
    - material_preference
    - study_strategy
    - study_environment
    - social_learning
    - feedback_seeking
  optional:
    - prior_readiness
    - anxiety_freetext
```

**Column kinds (`kind`)**: `identity` / `likert` / `single_select` /
`multiselect` / `freetext`. File size must be ≤ 256 KB (DoS protection).

---

## 3. CLI options

### Required

| Flag | Format | Example |
|---|---|---|
| `--semester` | `^\d{4}-[12SW]$` | `2026-1` |
| `--course` | `^[a-z][a-z0-9-]{1,39}$` | `anatomy` |

### Phase / analysis control

| Flag | Default | Meaning |
|---|---|---|
| `--phases` | `all` | Execution scope. `A-B` · `A-C` · `A-D` · `A-E` · `A-F` · `all` |
| `--k` | (auto) | Force the number of clusters (2–6). When unset, silhouette auto-recommends. **k=1 rejected** |
| `--no-llm` | off | Disable the LLM — use rule/dictionary/template fallback |
| `--no-roberta` (alias `--no-sentiment`) | off | Disable RoBERTa sentiment analysis — keyword dictionary only |

### LLM settings (also settable via env)

| Flag | Default / env |
|---|---|
| `--llm-provider` | `PAIDEIA_LLM_PROVIDER` / `anthropic` |
| `--llm-model` | `PAIDEIA_LLM_MODEL` / `claude-sonnet-4-6` |
| `--llm-timeout-seconds` | `30.0` |
| `--llm-retries` | `1` |

### Paths / utilities

| Flag | Default | Meaning |
|---|---|---|
| `--input-root` | `./data` | Bronze/Silver input root |
| `--output-root` | `./data` | Silver/Gold output root |
| `--keyword-language` | `ko` | Keyword dictionary language |
| `--seed` | `PAIDEIA_RANDOM_SEED` / `42` | Random seed |
| `--dry-run` | off | Validate inputs and plan only, produce no output |
| `--verbose` | off | DEBUG logging |

### Environment variables

| Variable | Meaning |
|---|---|
| `PAIDEIA_KR_FONT_PATH` / `_BOLD_PATH` | Absolute path to NanumGothic Regular/Bold (takes precedence over `fc-match`) |
| `PAIDEIA_ROBERTA_CACHE_DIR` | RoBERTa weights cache |
| `ANTHROPIC_API_KEY` | Required when the LLM is enabled |

---

## 4. Processing pipeline (6 phases)

| Phase | Output (Silver) | Algorithm |
|---|---|---|
| **A** | `scale_reliability.parquet` | Cronbach's α (per-axis reliability, n_items≥3) |
| **B** | `factor_scores.parquet` | Mean aggregation → missing-value policy → z-score |
| **C** | `cluster_assignment.parquet` | silhouette → KMeans → rule-based cluster naming |
| **D** | `free_text_categorization.parquet` | Keyword dictionary matching → LLM fallback |
| **D+** | `freetext_audit.parquet` | RoBERTa sentiment + token-decomposition audit |
| **E** | (Gold) cohort distribution PDF, cluster summary xlsx, long/summary export, operator manual PDF | Distribution computation + matplotlib/reportlab |
| **F** | (Gold) `cards/{학번}.pdf` | 8-axis radar + cohort-mean overlay + coaching |

The `factor_scores` from B and the `cluster_assignment` from C are **inputs to
immersio Phase 3/4**. C, E, and F require B's output, and synthesize it
automatically if B has not been run.

---

## 5. Output files

### Silver (`data/silver/needs-map/{semester}-{course}/`)
`scale_reliability.parquet` · `factor_scores.parquet` ·
`cluster_assignment.parquet` · `free_text_categorization.parquet` ·
`freetext_audit.parquet` · `manifest.json`

### Gold (`data/gold/needs-map/{semester}-{course}/`)
- `group_distribution.pdf` — 8-axis distribution histograms + cluster overlay
- `cluster_summary.xlsx` — per-cluster summary
- `factor_scores_long.{csv,yaml}` — per-student long form (the CSV is UTF-8 BOM)
- `axis_summary.{csv,yaml}` — per-axis summary
- `needs-map_manual.pdf` — operator manual (deterministically generated)
- `cards/{학번}.pdf` — **one card per student** (8-axis radar + coaching)
- `manifest.json`

On re-run, the previous output is moved losslessly to
`_archive/{ISO8601_UTC}__v{schema}/`.

---

## 6. Usage examples

```bash
# Full run (RoBERTa + LLM)
uv run --package needs-map paideia-needs-map run --semester 2026-1 --course anatomy

# Air-gapped / fast (zero external calls)
uv run --package needs-map paideia-needs-map run \
  --semester 2026-1 --course anatomy --no-llm --no-roberta

# Quickly prepare only the immersio Phase 3 inputs (A-B)
uv run --package needs-map paideia-needs-map run \
  --semester 2026-1 --course anatomy --phases A-B --no-llm

# Fix the number of clusters
uv run --package needs-map paideia-needs-map run \
  --semester 2026-1 --course anatomy --k 4

# Validate inputs only
uv run --package needs-map paideia-needs-map run \
  --semester 2026-1 --course anatomy --dry-run
```

To use RoBERTa sentiment analysis, install the optional dependency:

```bash
uv sync --extra roberta --package needs-map
```

---

## 7. Exit codes

| Code | Condition | Output |
|---|---|---|
| 0 | Success (LLM/RoBERTa fallback is also normal → 0) | Complete |
| 1 | Argument error (`--k=1`, invalid semester, mapping v1) | None |
| 2 | Missing input file or contract violation | None |
| 3 | Archival failure | None (atomic) |
| 4 | Output write failure (permissions / disk) | Partial |
| 6 | **NanumGothic not installed** (Regular/Bold) | None (pre-flight) |
| 99 | Internal bug | Partial |

---

## 8. Common pitfalls

| Symptom | Fix |
|---|---|
| `exit 6: Required Korean font 'NanumGothic'` | `sudo apt install fonts-nanum`, or set `PAIDEIA_KR_FONT_PATH` |
| `ImportError: torch` followed by a normal completion | RoBERTa not installed → fallback behavior (normal). To use it, run `uv sync --extra roberta` |
| Mapping YAML v1 rejected (exit 1) | Set `mapping_version: 2` and list all 8 axes under `axes.required` |
| Garbled Korean in CSV | `factor_scores_long.csv` is UTF-8 BOM. Verify the first 3 bytes are `EF BB BF` |
| Two runs differ byte-for-byte | Compare `font_resolution` · `sentiment.model_sha256` · `seed` in `manifest.json` |

---

## Related documents

- Next step: [immersio](../immersio/how_to_use_immersio.md) Phase 3 combined analysis
- Retrospective feedback: [retro-mester](../retro-mester/how_to_use_retro-mester.md)
- Design philosophy: [why_paideia](../why_paideia.md)
