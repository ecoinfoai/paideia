# how_to_use_immersio

> **immersio v0.1.x** — module for interpreting exam results and generating
> personalized student reports.
> (Latin *immersio*: immersion.)
> Takes OMR and grades, analyzes item quality, performs combined analysis with
> the needs-map diagnosis, builds a personalized report per student, and sends
> it by email.

This is paideia's result-interpretation module, run across several **Phases**
over a semester. All statistics, labels, and cards come from deterministic code;
only the natural-language phrasing of coaching comments is an LLM option.

---

## 1. At a glance

```bash
uv run --package immersio immersio <subcommand> [options]
```

- Console script: **`immersio`**
- Subcommands: `ingest` · `analyze` · `combine` · `email`
  (auxiliary: `email-init-test-fixtures` · `email-cleanup-log`)
- Data key: `{semester}-{course}` (e.g. `2026-1-anatomy`)

| Phase | Command | Role |
|---|---|---|
| 0 | `ingest` | Bronze → 4 Silver files |
| 1+2 | `analyze` | Exam quality analysis + student metrics + report |
| 3 | `combine` | needs-map × exam combined analysis |
| 6 | `email` | Send personalized student PDFs |

---

## 2. `ingest` — Phase 0 (Bronze → Silver)

Parses, validates, and integrates the survey, OMR, attendance roster, and exam
questions.

```bash
uv run --package immersio immersio ingest \
  --bronze-dir data/bronze \
  --mapping    data/bronze/매핑/anatomy.diagnostic.yaml \
  --output-key 2026-1-anatomy
```

| Flag | Required | Default |
|---|---|---|
| `--bronze-dir` | ✅ | — (contains `진단평가/` · `시험성적/` · `출석/` · `시험문제/` · `매핑/`) |
| `--mapping` | ✅ | — diagnostic mapping YAML |
| `--exam-yaml` | — | auto-detected from 시험문제/ |
| `--output-key` | — | `{semester}-{course}` |
| `--output-dir` | — | `data/silver/immersio/` |
| `--exam-result-pattern` | — | `*_{section}반*결과.xls(x)` (exclusion tokens: `(OX)`, `(문항분석)`, `결시`) |
| `--no-git-commit` | — | off |

**Output** (`data/silver/immersio/{key}/`): `student_master.parquet` ·
`diagnostic_response.parquet` · `exam_result.parquet` · `exam_item.parquet` ·
`manifest.json`.
(The first two are **inputs to needs-map**.)

---

## 3. `analyze` — Phase 1+2 (exam quality + student metrics)

```bash
uv run --package immersio immersio analyze \
  --semester 2026-1 --course anatomy
```

| Flag | Required | Default |
|---|---|---|
| `--semester` / `--course` | ✅ | — |
| `--silver-dir` / `--gold-dir` | — | `data/silver` / `data/gold` |
| `--legacy-xlsx` | — | `data/silver/legacy/중간고사_분석결과.xlsx` (diff skipped if absent) |
| `--created-at-utc` | — | computed from the input sha256 (byte-identical when specified) |
| `--seed` | — | `42` (env `PAIDEIA_RANDOM_SEED`) |
| `--no-needs-map` | — | off (when on, diagnostic-linked columns are N/A) |

**Output**:
- Silver: `문항통계.parquet` · `학생지표.parquet`
- Gold: `시험분석결과.xlsx` (7 sheets: 전체요약 [overall summary] · 메타데이터 [metadata] · 변별력 [discrimination] · 정답률 [correct-rate] · 학생성적 [student scores] · 히스토그램 [histogram] · 문항상세 [item detail]) ·
  `시험품질보고서.{md,pdf}` · `figs/fig{1,2}_*.png` · `legacy_diff.md`

> If the needs-map Silver
> (`data/silver/needs-map/{key}/factor_scores.parquet`) exists, the
> `관심챕터_*` and `비호감챕터_*` columns in the student-metrics sheet are
> populated. Otherwise they are N/A.

---

## 4. `combine` — Phase 3 (diagnosis × exam)

Combines the needs-map cluster and factor scores with exam results to analyze
correlations, regression, and cluster comparisons.

```bash
uv run --package immersio immersio combine \
  --semester 2026-1 --course anatomy \
  --silver-dir data/silver --gold-dir data/gold \
  --include-cluster --include-subgroup
```

| Flag | Required | Meaning |
|---|---|---|
| `--semester` / `--course` | ✅ | — |
| `--silver-dir` / `--gold-dir` | ✅ | No default — must be specified |
| `--include-cluster` | — | Enable cluster comparison (fig5 · §4 · sheet3) |
| `--include-subgroup` | — | Enable subgroup comparison (fig6 · §5 · sheet4) |

**Input**: 4 needs-map files (`factor_scores` · `cluster_assignment` ·
`cluster_names.json` · `manifest.json`) + 4 immersio files (`student_master` ·
`diagnostic_response` · `학생지표` · `manifest`).

**Output**:
- Silver: `진단×시험결합.parquet` · `manifest_phase3.json`
- Gold: `결합분석보고서.{md,pdf}` · `결합분석.xlsx` (2–4 sheets) · `figs/fig{3,4,5,6}_*.png`

---

## 5. `email` — Phase 6 (send personalized student PDFs)

Sends a per-student PDF via the Gmail API. The recommended order is
**dry-run → self-test → real send**.

```bash
# (1) dry-run — zero Gmail calls, .eml previews only
uv run immersio email --profile kjeong \
  --semester 2026-1 --course anatomy --exam-name "기말고사"

# (2) self-test — 5 messages to the operator only (zero student reach, --send required)
uv run immersio email --profile kjeong \
  --semester 2026-1 --course anatomy --exam-name "기말고사" --self-test 5 --send

# (3) real send — sends after a confirmation gate (yes/no)
uv run immersio email --profile kjeong \
  --semester 2026-1 --course anatomy --exam-name "기말고사" --send

# Retry only the failures
uv run immersio email --profile kjeong \
  --semester 2026-1 --course anatomy --exam-name "기말고사" --send --retry-failed
```

| Flag | Required | Default |
|---|---|---|
| `--profile` | ✅ | `~/.config/paideia/immersio_email/{profiles,test_profiles}/{name}.yaml` |
| `--semester` / `--course` | ✅ | — |
| `--exam-name` | ✅ | — (empty string rejected) |
| `--sent-date` | — | today (KST) |
| `--send` | — | off (= dry-run) |
| `--self-test N` | — | None (1–10, requires `--send`) |
| `--retry-failed` / `--retry-skipped` | — | (mutually exclusive) |
| `--rate-per-min` | — | profile (default 20, 1–30) |
| `--cohort` | — | `all` (or `low_score` / `rest`) |
| `--confirm-sample` | — | profile (default 3) |
| `--bronze-csv` | — | `data/bronze/진단평가/진단평가_1차_결과.csv` |
| `--gold-pdf-dir` | — | `data/gold/immersio/{key}/이메일_발송용` |

### dry-run vs send semantics (important)

| | dry-run (default) | `--send` |
|---|---|---|
| Gmail API calls | 0 | yes |
| Student reach | 0 | yes |
| Log file | `메일_발송로그_dryrun.csv` (truncated) | `메일_발송로그.csv` (appended) |
| Preview | `.eml` (To = student) | — |
| Confirmation gate | none | first N samples + yes/no |

> **The log files are kept separate** so that a dry-run never contaminates the
> real send log. Rows with `status=success` are automatically skipped on re-run
> (idempotent).

### Authentication

Place the Service Account JSON path in the env variable referenced by the
profile YAML's `secrets_ref.service_account_json_path_env`
(e.g. `PAIDEIA_GCP_SA_JSON_PATH_KJEONG`). Gmail DwD (domain-wide delegation)
is required. The key file should be 0400 (agenix-encrypted recommended).

### Auxiliary commands

- `immersio email-init-test-fixtures --profile <test>` — generate dummy test PDFs
- `immersio email-cleanup-log --semester ... --course ... --keep success,test_dummy [--dry-run]`
  — clean up the mixed send logs from the v0.1.0 era

---

## 6. Exit codes (summary)

| Command | 0 | Main non-zero |
|---|---|---|
| ingest | Success | 1 validation · 2 args/files · 3 IO · 4 integrity |
| analyze | Success | 1 validation · 2 pydantic · 3 missing data · 4 archival · 6 font |
| combine | Success | 1·2·3·4 · 5 schema mismatch · 6 font |
| email | Success | 1/2 input · 3 IO · 4 integrity · 5 auth · 7 lock · 8 partial failure |

---

## 7. Environment variables

| Variable | Meaning |
|---|---|
| `PAIDEIA_RANDOM_SEED` | analyze seed (`--seed` takes precedence) |
| `PAIDEIA_KR_FONT_PATH` / `_BOLD_PATH` | NanumGothic path (required for PDF/PNG) |
| `PAIDEIA_GCP_SA_JSON_PATH_{PROFILE}` | email Service Account JSON path |

---

## 8. Common pitfalls

| Symptom | Fix |
|---|---|
| `exit 6` / garbled Korean | Install NanumGothic |
| `semester` rejected | `YYYY-[12SW]` (e.g. `2026-1`), the hyphen is required |
| `course` rejected | lowercase kebab-case (`anatomy` OK, `Anatomy` rejected) |
| email exit 5 | Check the SA JSON path / DwD delegation |
| email exit 7 | Concurrent `--send`, or a cleanup-log lock conflict |
| `--cohort low_score` but exit 3 | `학생지표.parquet` is required |

---

## Related documents

- Prerequisite diagnosis: [needs-map](../needs-map/how_to_use_needs-map.md) (Phase 3 combined input)
- Exam authoring: [examen](../examen/how_to_use_examen.md)
- Retrospective feedback: [retro-mester](../retro-mester/how_to_use_retro-mester.md)
- Design philosophy: [why_paideia](../why_paideia.md)
