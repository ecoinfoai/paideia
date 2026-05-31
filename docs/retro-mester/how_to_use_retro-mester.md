# how_to_use_retro-mester

> 🚧 **The module is under development.**
>
> It currently exists only as the design document `idea/retro-mester-v0.1.0.md`.
> There is no runnable CLI or code yet; once implemented, this document will be filled in with usage instructions.

---

## What this module will be

**retro-mester** — a CQI (continuous quality improvement) tool that, after a semester has finished, uses that semester's data to produce a short, prioritized **list of course-design changes (3–5 items)** answering the question **"how should I teach the same course next year?"** It is the **final link** in the paideia six-module cycle.

| Item | Plan |
|---|---|
| Input | needs-map (the start) + immersio (the end) outputs (v0.1.0 uses only the two endpoints) |
| Output | 3–5 prioritized course changes for next year + a per-unit diagnostic report |
| Point in the semester | Once after the semester ends (during the break) |
| Dependencies | needs-map, immersio (later enriched by formative-analysis) |
| Code vs. LLM | Finding the spots, grouping them, classifying causes, and sizing them = code; only the narrative phrasing is an optional LLM step |

## Core design direction (summary)

- The target is **next year's course design, not support for individual students**. The subject of the output is "this kind of disposition type → this kind of pattern → next year, teach the course this way."
- Rather than trusting the average, decompose the **heterogeneous mix** (a low-effort majority + a small number of high-effort adult learners) into disposition types.
- For each unit, distinguish between **"stuck because it was hard (content/fundamentals) vs. stuck because they didn't do it (motivation)."**
- Express the report in the disposition language of needs-map so that **the next year's needs-map can cite it**.
- Deterministic: the same input → the same report (the core, excluding the narrative).

## References

- Design notes: `idea/retro-mester-v0.1.0.md`, `idea/paideia-idea.md` §1.6
- Input modules: [needs-map](../needs-map/how_to_use_needs-map.md) ·
  [immersio](../immersio/how_to_use_immersio.md)
- The big picture: [why_paideia](../why_paideia.md)
