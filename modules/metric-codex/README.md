# metric-codex

**metric-codex** is a paideia downstream module that accumulates per-student learning-competency records from school grade/attendance data and upstream paideia Silver (immersio, needs-map), enables structured evidence queries for academic advisors, and distributes per-advisor bundles as Gold markdown/yaml files.  The module never auto-sends anything — advisors receive their bundles through a manual, operator-controlled delivery step (v1 design principle).

All personally identifiable information (PII) is pseudonymized before it reaches any LLM.  Student IDs and Korean names are stored only in a local-only `pseudonym_map.parquet` (inside `data/`, which is gitignored); the re-identification step runs locally after generation.

---

## Commands

Run with `metric-codex <subcommand> --semester SEMESTER --course COURSE [options]`.

| Subcommand | Purpose | Key flags |
|---|---|---|
| `ingest` | Bronze→Silver: parse school Excel + consume immersio/needs-map Silver into `codex_entry.parquet` | `--school-excel`, `--school-map`, `--blueprint`, `--curriculum-map`, `--now` |
| `query` | Evidence retrieval in pseudonym space for a single student | `--student` (ID or S001), `--question-id` or `--text`, `--question-set`, `--reveal`, `--json` |
| `dry-run` | Deterministic staging bundle generation; no LLM call, no PII output (constitution §I) | `--question-set` |
| `generate` | Render per-student narrative (template or LLM polish) | `--backend` (`none`/`subscription`/`api`), `--model`, `--question-set`, `--require-llm`, `--responses-dir`, `--now` |
| `distribute` | Group Gold student files by advisor; write per-advisor bundles and unassigned report | `--roster`, `--now` |
| `verify` | Read-only post-hoc invariant check (completeness, provenance, PII boundary) | `--question-set`, `--roster` |
| `build` | Full pipeline: `ingest` → `generate` → `distribute` → `verify` in one shot | all flags of the four stages combined |

---

## Directory layout

### Bronze (operator-supplied inputs)

```
data/bronze/metric-codex/{semester}-{course}/
├── 성적출석.xlsx          # school grade + attendance workbook (학교 LMS 내보내기)
├── 성적출석_map.yaml      # column mapping config → templates/성적출석_map.example.yaml
├── 지도교수배정.yaml      # advisor roster → templates/지도교수배정.example.yaml
├── question_set.yaml      # advisor query definitions → templates/question_set.example.yaml
├── blueprint.yaml         # (optional) examen blueprint Bronze copy — provenance only
└── curriculum_map.yaml    # (optional) curriculum map Bronze copy — provenance only
```

Upstream Silver consumed during `ingest` (read-only; never written by metric-codex):

```
data/silver/immersio/{semester}-{course}/       # rich learning-axis entries
data/silver/needs-map/{semester}-{course}/      # survey + freetext entries
```

### Silver (pipeline intermediates, gitignored)

```
data/silver/metric-codex/{semester}-{course}/
├── codex_entry.parquet        # accumulated CodexEntry rows (deterministic: use_dictionary=False)
├── source_ledger.parquet      # SourceRecord provenance log
├── pseudonym_map.parquet      # LOCAL ONLY — student_id ↔ S001 mapping (PII)
├── manifest_metric-codex.json # run provenance + bundle summary
└── staging/                   # dry-run + generate staging bundles (pseudonymized JSON)
```

### Gold (advisor deliverables, gitignored)

```
data/gold/metric-codex/{semester}-{course}/
├── 학생별/
│   └── {student_id}_{name_kr}.md    # per-student narrative (re-identified, advisor-ready)
├── 지도교수별/
│   └── {advisor_id}/
│       └── {student_id}_{name_kr}.md  # per-advisor copy (no cross-advisor leak)
└── 미배정.md                          # students with no advisor assignment
```

---

## Privacy / 가명화 boundary

```
Bronze PII (학번, 성명)
        │
        ▼ ingest
Silver  pseudonym_map.parquet  [LOCAL ONLY — never leaves data/]
        │
        ▼ generate (dry-run / generate)
        Pseudonymized evidence → LLM prompt contains only S001, not real names
        │
        ▼ reidentify (generate stage, after LLM response)
Gold    {student_id}_{name_kr}.md  [data/ — gitignored]
        │
        ▼ distribute (manual operator step)
Advisor receives their bundle via email / USB / portal — NOT auto-sent by metric-codex
```

- PII (student_id, name_kr) is replaced by pseudonyms (`S001`, `S002`, …) **before** any LLM call.
- `pseudonym_map.parquet` lives inside `data/` (gitignored); it is never committed and never sent over the network.
- `data/` is covered by the repo-root `.gitignore`; `templates/` (example configs) is tracked.
- In v1 there is no auto-send or email integration — the operator manually delivers per-advisor directories.

---

## Exit codes

| Code | Meaning |
|---|---|
| `0` | Success |
| `2` | Input / configuration validation failure (located error, fixable by operator) |
| `3` | Pipeline step failure (invariant violation, missing Silver, etc.) |
| `4` | LLM backend unreachable (`--backend api` + `--require-llm` only) |

---

## Determinism

Identical inputs produce byte-identical Silver and Gold outputs.  The only
non-deterministic injection point is `--now` (ISO-8601 UTC timestamp); when
omitted the manifest/ledger timestamps use wall-clock time.  Parquet files are
written with `use_dictionary=False` / `write_statistics=False` for reproducible
byte output.

---

## Run

```bash
# Full test suite
LD_LIBRARY_PATH=/run/current-system/sw/share/nix-ld/lib \
  uv run --package metric-codex pytest modules/metric-codex/tests -q

# Lint
LD_LIBRARY_PATH=/run/current-system/sw/share/nix-ld/lib \
  uv run ruff check modules/metric-codex
```
