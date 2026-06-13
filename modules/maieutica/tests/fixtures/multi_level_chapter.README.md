# multi_level_chapter.txt — structure note (test contract)

Synthetic anatomy/physiology chapter fixture for multi-level chunking and
diversity tests. Content is invented but reads plausibly. This note is the
contract the chunking-test agent asserts against; line numbers are 1-based and
match `multi_level_chapter.txt` EXACTLY (52 lines total). Re-count if the .txt
changes.

The companion fixtures `generation_spec.yaml` and `curriculum_map.yaml` describe
the same chapter (semester `2026-1`, course `anatomy`, week `9`, chapter `8`).

## Full line map (1-based)

| Line | Content | Role |
|-----:|---------|------|
| 1  | `H U M A N  A N A T O M Y` | NOISE — spaced-letter header (stripped) |
| 2  | (blank) | spacing |
| 3  | `8장 호흡계통` | chapter title line (matches spec/curriculum `chapter`) |
| 4  | (blank) | spacing |
| 5  | `1. 호흡계통의 구조` | TOC entry for top-level `1.` (deduped — skipped) |
| 6  | `2. 호흡의 조절` | TOC entry for top-level `2.` (deduped — skipped) |
| 7  | (blank) | TOC/body separator |
| 8  | `1. 호흡계통의 구조` | **L1 heading** `1.` (body) |
| 9  | `호흡계통은 공기를 받아들여 가스를 교환하는 기관들의 집합이다.` | body |
| 10 | (blank) | paragraph boundary |
| 11 | `1) 코` | **L2 heading** `1)` under `1.` |
| 12 | `코는 들이마신 공기를 데우고 가습하는 첫 관문이다.` | body |
| 13 | `코털과 점막은 먼지와 이물질을 거른다.` | body |
| 14 | (blank) | paragraph boundary |
| 15 | `2) 인두` | **L2 heading** `2)` under `1.` |
| 16 | `인두는 공기와 음식이 함께 지나가는 통로이다.` | body |
| 17 | `인두는 코안과 후두를 잇는 공간이다.` | body |
| 18 | (blank) | paragraph boundary |
| 19 | `3) 후두` | **L2 heading** `3)` under `1.` |
| 20 | `후두는 발성을 담당하며 기도를 보호한다.` | body |
| 21 | `가) 성대` | **L3 heading** `가)` under `3) 후두` |
| 22 | `성대는 공기 흐름으로 진동하여 소리를 만든다.` | body |
| 23 | `나) 후두덮개` | **L3 heading** `나)` under `3) 후두` |
| 24 | `후두덮개는 삼킴 동안 기도를 덮어 음식의 진입을 막는다.` | body |
| 25 | (blank) | section boundary |
| 26 | `2. 호흡의 조절` | **L1 heading** `2.` (body) |
| 27 | `호흡은 자율신경과 화학수용체에 의해 정밀하게 조절된다.` | body |
| 28 | (blank) | paragraph boundary |
| 29 | `1) 가스 교환` | **L2 heading** `1)` under `2.` — OVERSIZED subsection |
| 30 | `폐포는 모세혈관과 맞닿아 가스를 교환한다.` | body (para 1) |
| 31 | (blank) | paragraph boundary |
| 32 | `폐포에서는 산소가 혈액으로 들어가고 이산화탄소가 혈액에서 나온다.` | body (para 2) |
| 33 | `이 교환은 분압 차이에 따른 단순 확산으로 일어난다.` | body (para 2) |
| 34 | `모세혈관의 얇은 벽은 확산 거리를 최소화한다.` | body (para 2) |
| 35 | (blank) | paragraph boundary |
| 36 | `가로막은 수축하여 흉강의 부피를 늘리고 압력을 낮춘다.` | body (para 3) |
| 37 | `압력이 낮아지면 외부 공기가 기관지를 거쳐 폐로 유입된다.` | body (para 3) |
| 38 | `기관지는 공기를 좌우 폐로 나누어 전달하는 통로이다.` | body (para 3) |
| 39 | (blank) | paragraph boundary |
| 40 | `들숨에서는 바깥갈비사이근이 갈비뼈를 들어 올려 흉강을 넓힌다.` | body (para 4) |
| 41 | `날숨에서는 가로막과 갈비사이근이 이완하여 흉강이 좁아진다.` | body (para 4) |
| 42 | `이때 폐의 탄성 반동이 공기를 바깥으로 밀어낸다.` | body (para 4) |
| 43 | (blank) | subsection boundary |
| 44 | `① 중추 조절` | **L3 heading** `①` under `2.` (sibling of `1) 가스 교환`) |
| 45 | `숨뇌의 호흡중추가 기본 리듬을 만든다.` | body |
| 46 | `② 화학 조절` | **L3 heading** `②` under `2.` |
| 47 | `화학수용체가 이산화탄소 농도를 감지해 호흡수를 바꾼다.` | body |
| 48 | (blank) | spacing |
| 49 | `123` | NOISE — standalone page number (stripped) |
| 50 | `연습문제` | NOISE — exercise block start (stripped to EOF) |
| 51 | `1. 코의 기능을 두 가지 쓰시오.` | NOISE — inside 연습문제 block (stripped) |
| 52 | `2. 폐포에서 일어나는 가스 교환을 설명하시오.` | NOISE — inside 연습문제 block (stripped) |

## Heading tree

```
8장 호흡계통
├─ 1. 호흡계통의 구조            (L1, line 8)
│  ├─ 1) 코                      (L2, line 11)
│  ├─ 2) 인두                    (L2, line 15)
│  └─ 3) 후두                    (L2, line 19)
│     ├─ 가) 성대                (L3, line 21)
│     └─ 나) 후두덮개            (L3, line 23)
└─ 2. 호흡의 조절               (L1, line 26)
   ├─ 1) 가스 교환              (L2, line 29)   ← OVERSIZED
   ├─ ① 중추 조절              (L3, line 44)
   └─ ② 화학 조절              (L3, line 46)
```

### Level markers (parallel within each level)

- **L1**: `N.` — lines 8, 26 (and TOC copies at 5, 6).
- **L2**: `N)` — lines 11, 15, 19 (under `1.`); line 29 (under `2.`).
- **L3**: mixed marker styles depending on parent branch:
  - `가)` / `나)` — lines 21, 23 (under `3) 후두`).
  - `①` / `②` — lines 44, 46 (under `2.`).

### "Deepest common level" caveat for the test agent

Depth is NOT uniform across branches — this is intentional so the
"descend to the deepest COMMON level" rule is exercised, not assumed:

- Under `1.`: `1) 코` and `2) 인두` stop at L2; only `3) 후두` has L3 children
  (`가)`/`나)`). So the deepest *common* level under `1.` is L2 (`N)`); the
  `가)`/`나)` items are a deeper branch on one sibling only.
- Under `2.`: the L3 items `①`/`②` are siblings of the L2 item `1) 가스 교환`
  at the same parent (`2.`), i.e. the marker level is inconsistent within one
  parent. The test agent must decide how the v0.1.1 recursion treats this
  (e.g. whether `①`/`②` are promoted to siblings of `1)` or treated as a
  distinct deeper level). This fixture deliberately leaves that to the test.

## Oversized subsection

`1) 가스 교환` (heading line 29) is the single oversized deepest-level
subsection. Its body spans lines 30–42 and is organized into **4 paragraphs**
separated by blank lines:

| Paragraph | Lines | Sentences |
|-----------|-------|-----------|
| 1 | 30        | 1 |
| 2 | 32–34     | 3 |
| 3 | 36–38     | 3 |
| 4 | 40–42     | 3 |

All other deepest-level subsections (`1) 코`, `2) 인두`, `3) 후두`, the `가)` /
`나)` / `①` / `②` items) have only 1–2 body sentences and no internal blank
lines, so `1) 가스 교환` is clearly the longest by character count — well above
`median × K` (K≈3). It is the one subsection that should trigger the
blank-line paragraph-boundary sub-split in v0.1.1.

## Noise lines (cleaner must strip — verified)

Running `clean_textbook` on this fixture removes exactly:

- **Line 1** — `[spaced_header]` `H U M A N  A N A T O M Y`
- **Line 49** — `[page_number]` `123`
- **Lines 50–52** — `[연습문제/exercise_block]` (from `연습문제` to EOF)

No noise text leaks into any emitted chunk (verified: `H U M A N`, `123`,
`연습문제`, `코의 기능` all absent from chunk bodies). `removed_spans` is
non-empty (3 entries).

## Verbatim key-concept terms (for groundedness/anchor tests)

These short noun phrases appear VERBATIM on their own body lines and survive
cleaning, so downstream groundedness/anchor lookups resolve to 확인:

| Term | Body lines (verbatim occurrence) |
|------|----------------------------------|
| 코     | 11 (`1) 코`), 12, 13 |
| 인두   | 15 (`2) 인두`), 16, 17 |
| 후두   | 19 (`3) 후두`), 20 |
| 폐포   | 30, 32 |
| 기관지 | 37, 38 |
| 가로막 | 36, 41 |

(`코`, `인두`, `폐포`, `기관지`, `가로막` mirror the key concepts already used
by `test_us1_quiz_build.py`.)

## Current-chunker behavior (top-level `N.` only, pre-v0.1.1)

Under the CURRENT implementation (`chunk_chapter`, which detects only `N.`
headings and dedups TOC copies), the fixture yields exactly **2 chunks**:

| section | line_start | line_end |
|---------|-----------:|---------:|
| `1. 호흡계통의 구조` | 8  | 25 |
| `2. 호흡의 조절`     | 26 | 47 |

The TOC copies at lines 5–6 are skipped (each `N.` heading appears twice).
v0.1.1 will descend into the `N)` / `가)` / `①` levels and paragraph-split the
oversized `1) 가스 교환` subsection; the assertions for that behavior live in
the downstream chunking test, not here.

## Companion fixture field values

### generation_spec.yaml

| field | value |
|-------|-------|
| semester | `2026-1` |
| course_slug | `anatomy` |
| week | `9` |
| chapter_no | `8` |
| chapter | `8장 호흡계통` |
| quiz_count | `12` (default; tests may override — "quiz_count 가변") |
| formative_count | `3` |

### curriculum_map.yaml

| field | value |
|-------|-------|
| semester | `2026-1` |
| course_slug | `anatomy` |
| entries[0].week | `9` |
| entries[0].chapter | `8장 호흡계통` |
| entries[0].chapter_no | `8` |
| entries[0].subtopic | `호흡계통의 구조와 호흡 조절` |
| entries[0].sections | `["1. 호흡계통의 구조", "2. 호흡의 조절"]` |

Both load cleanly via `maieutica.ingest.spec_load.load_generation_spec` /
`load_curriculum_map` and are mutually consistent and consistent with the
chapter title on line 3 of the .txt.
