# Quickstart — Your First Output in 5 Minutes

The shortest path to installing paideia for the first time, running a single
module, and seeing a result. It assumes you already know what paideia is; for
background, see [why_paideia.md](why_paideia.md).

---

## 0. Prerequisites

### Required
- **Python 3.11** + **[uv](https://docs.astral.sh/uv/)** (workspace management)
- **The NanumGothic font** — required for all PDF/PNG output. If it isn't installed, zero outputs are produced (exit 6).

```bash
# Install the font
sudo apt install fonts-nanum && fc-cache -fv      # Ubuntu/Debian
brew install --cask font-nanum-gothic             # macOS
# NixOS: home.packages = [ pkgs.nanum ];
```

### Optional
- **ANTHROPIC_API_KEY** — for when you want an LLM to smoothly produce
  natural-language output (coaching comments, question generation). **Even
  without it, the deterministic stages run to completion.**

> On a **NixOS + nix-ld environment**, you must add the nix-ld lib to
> `LD_LIBRARY_PATH` when running `pytest`/`python`. See the repository's
> operations notes for the exact canonical commands.

---

## 1. Install

```bash
git clone <repo-url> paideia
cd paideia
uv sync                       # install the entire umbrella workspace
```

To sync only a specific module or enable optional dependencies:

```bash
uv sync --extra roberta --package needs-map   # include free-text sentiment analysis (RoBERTa)
```

Verify the install:

```bash
uv run --package examen   examen   --help
uv run --package immersio immersio --help
uv run --package needs-map paideia-needs-map --help
```

---

## 2. The Directory Convention (the one thing to memorize)

Every module shares the three-layer **Bronze → Silver → Gold** structure
under `data/`.

```text
data/
├── bronze/    # raw as-is (survey CSV, OMR .xls, textbook .txt, lecture STT)
├── silver/    # normalized intermediate output (*.parquet) — the inter-module exchange format
└── gold/      # final, human-facing output (xlsx / md / pdf / png)
```

Everything is isolated per semester and course: `{semester}-{course}`
(e.g. `2026-1-anatomy`).

---

## 3. First Run — examen (exam generation)

The fastest path to seeing a result. Just place the inputs, and it runs from
ingest→plan even without an LLM.

```bash
# (1) Place inputs — under data/bronze/examen/2026-1-anatomy/:
#     textbooks textbooks/*.txt, blueprint.yaml, curriculum_map.yaml

# (2) Run the whole pipeline at once
uv run --package examen examen build \
  --semester 2026-1 \
  --course   anatomy
```

Check the output:

```bash
ls data/gold/examen/2026-1-anatomy/runs/*/
#   기말출제초안.xlsx   기말출제초안.yaml
#   출제품질리포트.md   manifest_examen.json   ingest_report.json
```

> Even if the LLM backend can't be reached, **the deterministic stages run to
> completion** — ingest, plan, verification, and so on. Only question
> generation (generate) requires an LLM (or a cache).

---

## 4. Verifying Determinism (paideia's core promise)

Run twice with the same input and you get **byte-identical** output.

```bash
uv run --package examen examen build --semester 2026-1 --course anatomy
sha256sum data/gold/examen/2026-1-anatomy/runs/*/기말출제초안.yaml > /tmp/a.txt

uv run --package examen examen build --semester 2026-1 --course anatomy
sha256sum data/gold/examen/2026-1-anatomy/runs/*/기말출제초안.yaml > /tmp/b.txt

diff /tmp/a.txt /tmp/b.txt   # empty diff = determinism guaranteed
```

---

## 5. Next Steps

- To follow the full semester flow → [tutorial.md](tutorial.md)
- Detailed per-module flags and I/O → each module's `how_to_use_*.md`
  - [needs-map](needs-map/how_to_use_needs-map.md) ·
    [examen](examen/how_to_use_examen.md) ·
    [immersio](immersio/how_to_use_immersio.md)

---

## Common Pitfalls

| Symptom | Cause | Fix |
|---|---|---|
| `exit 6` / broken Korean glyphs | NanumGothic not installed | `sudo apt install fonts-nanum` |
| `FileNotFoundError` (exit 2) | Typo in or missing input filename | Re-check the Bronze path and filename conventions (see each module's docs) |
| Only the LLM stage halts | No `ANTHROPIC_API_KEY` | Set the key, or use only up to the deterministic stages |
| Module command not found | Missing `--package` | Use the `uv run --package <module> <cmd>` form |
