# retro-mester

**paideia module** — 학기 회고(retrospective) 분석 파이프라인.

Consumes immersio Phase 3 Silver output and produces:

- A prioritised list of 3–5 instructional changes with cause hypotheses (CQI report)
- Group-differentiated prescriptions for 학령기 / 만학도 cohorts
- A forward contract (차년도방향.yaml) for year-on-year audit

## Purpose

retro-mester closes the CQI loop for a single course-semester. Given immersio's
combined analysis (student × diagnostic × exam) it identifies which chapters failed,
why (root-cause classification), and which instructional changes have the largest
expected impact. All deterministic analysis completes without an LLM; an optional
LLM layer adds narrative interpretation.

## Quick start

```
retro-mester run \
  --semester 2026-1 \
  --course anatomy \
  --data-root data/
```

With a prior-year forward contract for audit:

```
retro-mester run \
  --semester 2026-1 \
  --course anatomy \
  --prior-year data/gold/retro-mester/2025-1-anatomy/차년도방향.yaml
```

With LLM narrative (requires `claude` CLI and active subscription):

```
retro-mester run \
  --semester 2026-1 \
  --course anatomy \
  --llm-mode subscription
```

## CLI reference

```
retro-mester run --semester SEMESTER --course COURSE [options]

Required:
  --semester SEMESTER   학기 코드 (예: 2026-1)
  --course   COURSE     과목 슬러그 (예: anatomy)

Optional:
  --data-root DIR       Data root (default: data/)
  --config PATH         retro_config.yaml override
  --prior-year PATH     Path to a prior 차년도방향.yaml for forward-contract audit.
                        When omitted, cold-start mode (no audit section emitted).
  --llm-mode {off,subscription,api}
                        off (default) | subscription (claude CLI) | api (anthropic SDK)
  --require-llm         Exit 5 if LLM unreachable instead of degrading gracefully

Exit codes: 0 success · 2 input/config error · 3 integrity error · 5 LLM required fail
```

## Inputs

All inputs are read from the data hierarchy under `data-root`:

| Role | Path | Description |
|------|------|-------------|
| `combined` | `silver/immersio/{semester}-{course}/진단×시험결합.parquet` | immersio Phase 3 Silver output |
| `items` | `silver/immersio/{semester}-{course}/문항통계.parquet` | Item-level CTT statistics |
| `config` | `bronze/retro-mester/{semester}-{course}/retro_config.yaml` | Pipeline config (groups, thresholds) |
| `blueprint` | `bronze/retro-mester/{semester}-{course}/blueprint.yaml` | Exam blueprint |
| `curriculum_map` | `bronze/retro-mester/{semester}-{course}/curriculum_map.yaml` | Chapter–week map |

## Outputs

| File | Tier | Description |
|------|------|-------------|
| `빈틈표.parquet` | Silver | One row per UnitGap (chapter × segment) |
| `변경권고.parquet` | Silver | One row per ChangeRecommendation, ranked |
| `CQI회고보고서.md` | Gold | Markdown CQI report |
| `CQI회고보고서.pdf` | Gold | PDF version of the report |
| `회고분석.xlsx` | Gold | Five-sheet workbook (빈틈·변경권고·집단대비·정렬·타당도) |
| `차년도방향.yaml` | Gold | Forward contract for next-year audit |
| `차년도진단문항제안.md` | Gold | Proposed diagnostic items for next year |
| `manifest_retro.json` | Gold | Run audit manifest (inputs·thresholds·counts·degrade) |

Silver outputs: `data/silver/retro-mester/{semester}-{course}/`
Gold outputs: `data/gold/retro-mester/{semester}-{course}/`

## Spec and contracts

Full specification: `specs/011-retro-mester-v0-1-0/`

- `spec.md` — feature specification and acceptance scenarios
- `plan.md` — design decisions and architecture
- `contracts/cli.md` — CLI contract
- `contracts/inputs.md` — input schema contracts
- `contracts/outputs.md` — output schema contracts
- `contracts/config_yaml.md` — retro_config.yaml schema
