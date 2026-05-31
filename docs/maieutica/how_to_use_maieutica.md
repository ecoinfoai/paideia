# how_to_use_maieutica

> 🚧 **The module is under development.**
>
> It currently exists only as a design document under `idea/`; there is no runnable CLI or code yet.
> What follows is the planned direction; once implemented, this document will be filled in with usage instructions.

---

## What this module will be

**maieutica** (from the Greek *μαιευτική*, "the art of midwifery") — a module that generates **multiple-choice quiz candidates** and **short-answer formative-assessment candidates** from textbook text for use each week.

| Item | Plan |
|---|---|
| Input | Textbook chapter text (extracted from PDF or Markdown) |
| Output | N multiple-choice candidates + M short-answer candidates per chapter (Pydantic-validated JSON) |
| Point in the semester | Before the semester (all at once) + each week (incrementally) |
| Dependencies | Textbook |
| Code vs. LLM | Text chunking and structured-output validation = code; question generation = LLM (required) |
| Downstream consumers | formative-analysis, examen |

LLM output must always be received as JSON validated against a Pydantic schema (the AutoQuizzer pattern), so that downstream modules can consume it safely.

## Current alternative

Until the module is available, you can produce similar output with the following Claude Code skills.

- **chapter-quiz-generator** — generates 20 five-option multiple-choice quiz questions per chapter
- **formative-test-creator** — generates short-answer formative-assessment items with rubrics

## References

- Design notes: `idea/paideia-idea.md` §1.2
- The big picture: [why_paideia](../why_paideia.md)
