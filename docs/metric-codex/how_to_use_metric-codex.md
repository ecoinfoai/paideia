# how_to_use_metric-codex

> 🚧 **The module is under development.**
>
> It currently exists only as the design document `idea/metric-codex-v0.1.0.md`.
> There is no runnable CLI or code yet; once implemented, this document will be filled in with usage instructions.
>
> ⚠️ metric-codex is a downstream project **outside** the direct scope of paideia.
> It is an aggregation and query layer that re-gathers paideia's outputs around *a single student*;
> its consumer is not a course instructor but an **academic advisor**, and its data model is student-centric.

---

## What this module will be

**metric-codex** (a register, *codex*, + *metric* → "a register of learning metrics") —
a tool that accumulates the learning-competency data produced by paideia together with the grades and attendance from the school's systems, **centered on a single student**, and lets an academic advisor run **evidence-based, locally-run-LLM queries** about a semester of learning for the students they advise.

| Item | Plan |
|---|---|
| Input | School Excel files (total scores and attendance, the minimal layer) + paideia outputs (per-item and per-domain, the rich layer) |
| Output | A per-student accumulated store + advisor query responses (with source citations) |
| Consumer | Academic advisors (their own advisees only) |
| Dependencies | paideia module outputs (especially immersio's per-student records) |

## Core constraints (design anchors)

- **Learning-competency data only** — counseling and personal-life information is excluded for legal reasons.
- **Only one's own advisees** can be queried.
- **Local processing** — queries run on a local LLM, and the data never leaves the machine.
- **Evidence citation** — every answer cites its source, and anything missing is explicitly marked as "no evidence."
- **Structured + unstructured hybrid** — tables such as scores and test attempts are held together with free-text descriptions for querying.
- **Source and timestamp tags** — a record of which source the data came from and when it arrived (file-based ingestion).

## References

- Design notes: `idea/metric-codex-v0.1.0.md`
- Data-supplying modules: [immersio](../immersio/how_to_use_immersio.md) ·
  [needs-map](../needs-map/how_to_use_needs-map.md)
- The big picture: [why_paideia](../why_paideia.md)
