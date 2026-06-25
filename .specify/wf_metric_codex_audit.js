export const meta = {
  name: 'metric-codex-audit',
  description: 'Adversarial multi-dimension audit of the metric-codex v0.1.0 module',
  phases: [
    { title: 'Review', detail: '13 dimensions find raw findings in parallel' },
    { title: 'Verify', detail: 'each finding adversarially re-verified (3 skeptics for high/critical)' },
    { title: 'Synthesize', detail: 'dedup, tally, overall verdict + completeness critic' },
  ],
}

// ---------- shared context embedded into every finder/verifier prompt ----------
const COMMON = `
You are auditing the **metric-codex v0.1.0** module (paideia umbrella, branch 013-metric-codex-v0-1-0).
metric-codex is a DOWNSTREAM aggregation+query layer: it accumulates per-STUDENT learning-capability
records (school Excel total/attendance = "minimal" layer + paideia module Silver outputs = "rich" layer)
into a deterministic provenance-tagged store, lets an advisor query one student's codex with cited
evidence (LLM optional, deterministic fallback), and distributes per-student narratives into per-advisor
bundles. Operator = the course professor; "only my advisees" is satisfied by per-advisor DISTRIBUTION
(not runtime access control).

REPO PATHS (absolute root /home/kjeong/localgit/paideia):
- Source: modules/metric-codex/src/metric_codex/{cli,ingest,store,retrieve,generate,distribute,verify,output}/*.py
- Shared contracts: shared/paideia_shared/src/paideia_shared/schemas/metric_codex/*.py
- Tests: modules/metric-codex/tests/{unit,integration,contract,fixtures}/*.py
- Spec: specs/013-metric-codex-v0-1-0/{spec.md,plan.md,data-model.md,research.md,contracts/cli.md,contracts/privacy.md}
- Constitution: .specify/memory/constitution.md ; project rules: CLAUDE.md
- Templates: modules/metric-codex/templates/*.example.yaml, prompt_narrative.txt

LAYER MAP: Bronze data/bronze/metric-codex/{sem}-{course}/ (성적출석.xlsx + _map.yaml, 지도교수배정.yaml,
blueprint.yaml, curriculum_map.yaml, question_set.yaml). Silver: codex_entry.parquet, source_ledger.parquet,
pseudonym_map.parquet, cache/{sha256}.json, staging/{pseudonym}.json, manifest_metric-codex.json.
Gold: 학생별/{sid}_{name}.md, 지도교수별/{advisor}/..., 미배정.md.

TESTABLE INVARIANTS (contracts/privacy.md) — cite these IDs when a finding violates one:
- PRIV-01 no direct identifier (10-digit id, Hangul name, email) in any staging/*.json or LLM payload (pseudonyms S{NNN} only)
- PRIV-02 pseudonym_map.parquet is the ONLY identity↔pseudonym map; never read while building the LLM prompt
- PRIV-03 pseudonym assignment bijective + deterministic (ascending student_id); re-ingest identical input → identical map
- PRIV-04 data/ gitignored; no PII artifact tracked by git
- PRIV-05 absent/unreadable/non-bijective map OR a student_id missing at re-identification → loud located error, NO partial Gold written
- EVID-01 every factual claim in QueryAnswer.narrative / per-student Gold md maps to a real codex_entry citation
- EVID-02 absent layer → no_evidence=True + literal "근거 없음"; no fabricated value; available_layers reflects reality
- EVID-03 LLM narrative rendered ONLY from the deterministic evidence bundle (bundle is sole context)
- DET-01 ingest byte-identical for identical inputs (parquet flags pinned, no wall-clock in codex_entry, sorted); re-ingest does not change entry_count
- DET-02 full pipeline completes with --backend none offline (ingest/retrieval/template/distribute/verify) — no hard stop, no silent skip
- DET-03 LLM generation cached by input-hash (prompt,facts,model,mode SHA-256); cache hit reproduces byte-for-byte
- SKIP-01 a student whose 학번 fails normalization → located error, never dropped silently
- SKIP-02 codex-but-no-roster student appears in 미배정.md + AdvisorBundleSummary.unassigned_sids; assigned+unassigned==total exactly
- SKIP-03 a per-advisor bundle contains ONLY that advisor's advisees; cross-advisor leakage = 0
- BND-01 school Excel/roster/blueprint/curriculum/consumed-Silver validated at ingestion boundary; failures report file·row·column·expected/actual and exit 2

EXIT CODES: 0 ok · 2 input/config validation (located) · 3 pipeline step failure · 4 LLM backend unreachable (api mode only, with --require-llm).

CONSTITUTION (NON-NEGOTIABLE): I Deterministic-first w/ optional LLM (pipeline completes w/o LLM; no silent skip/hard stop);
II Bronze→Silver→Gold + Pydantic contracts (consume only other modules' Silver/Gold, NEVER share Bronze; validate at boundary w/ located errors);
III variability via config not code (no hardcoded column/sheet/label names); IV student-individual terminal output;
V privacy/reproducibility/audit (PII never in git; data/ gitignored; every Silver/Gold has a manifest w/ input hashes+config ids).

PREVIOUSLY-FLAGGED v0.1.1 backlog (from a prior audit — VERIFY CURRENT STATUS against today's code; the
module was hardened afterward in commits e6361a4..784a855, so some may be fixed):
(a) cluster_names.json not generated (cluster_label entries lack a name mapping);
(b) manifest input_hashes omits some consumed sources (missing-source not recorded);
(c) pseudonym numbering unstable across accumulation (adding a new student renumbers existing S{NNN} → breaks PRIV-03 stability);
(d) shared CanonicalStudentId regex \`^\\d{10}$\` — Python \\d matches Unicode digits (e.g. Arabic-Indic), so non-ASCII "digits" pass.

METHOD: Read the ACTUAL source files (do not speculate). Cite every finding with file:line. Ground each
finding in observed code, not assumptions. You MAY use read-only Bash (grep, find, git check-ignore, viewing
files) but DO NOT run the full pytest/uv suite (it rebuilds the venv and several of you run concurrently —
that corrupts the shared env). If a claim needs runtime reproduction, state it in runtime_repro_hint instead.

SEVERITY RUBRIC:
- critical: breaks a NON-NEGOTIABLE invariant in a NORMAL/common path (PII reaches LLM, silent data loss,
  byte-identity break of a core output in the common case, exploitable security hole, hard-stop when LLM absent).
- high: violates a stated MUST / SC / contract invariant in a common path but recoverable, or determinism break in a less-common path.
- medium: real defect with a workaround, uncommon trigger, or partial spec gap.
- low: minor correctness/robustness/clarity; dead code; misleading comment.
- info: observation, style, future-proofing.
Be precise and skeptical. A "finding" must be a real defect or genuine gap, not a restatement of intended behavior.
`

const DIMENSIONS = [
  { key: 'spec', title: 'Spec & acceptance compliance', files: 'all src + spec.md',
    focus: `Trace EVERY requirement to code: FR-001..FR-024 (note FR-022/023/024 are query/privacy/distribution),
SC-001..SC-009, all Acceptance Scenarios (US1 #1-4, US2 #1-4, US3 #1-3), all Edge Cases, all Clarifications.
For each: is it fully satisfied, partially, or missing? Focus especially on the "no silent omission" family
(FR-010 normalization-fail report, FR-018 unassigned report, SC-005 fabrication=0, SC-008 silent-drop=0) and
on degrade transparency (FR-015 available_layers, FR-013 "근거 없음"). Re-check backlog (a) cluster_names.json.` },
  { key: 'contracts', title: 'Contract conformance', files: 'shared/.../schemas/metric_codex/*.py + cli/main.py vs data-model.md + contracts/cli.md',
    focus: `Check all 7 Pydantic models (CodexEntry, SourceRecord, PseudonymMapEntry, AdvisorRosterEntry,
EvidenceCitation, QueryAnswer, AdvisorBundleSummary, MetricCodexManifest) against data-model.md: field types,
ConfigDict(extra=forbid, frozen=True), validators (value_num XOR value_text; item_ref⇒item_correct;
layer==minimal⇒entry_kind∈{score_total,score_percent,attendance}; natural-key; AdvisorBundleSummary count
invariant; QueryAnswer no_evidence⇒citations==[]). Check CLI contract: every subcommand, required flags
(--semester/--course/--data-root), exit codes 0/2/3/4, atomic writes. Re-check backlog (d): is CanonicalStudentId
regex anchored & ASCII-only? Does \\d admit Unicode digits?` },
  { key: 'ingest-store', title: 'Ingest & accumulation correctness', files: 'ingest/{normalize,school_excel,paideia_sources,bronze_copies,result}.py, store/codex.py',
    focus: `학번 normalization (strip/zero-pad to 10, FR-003). Additive accumulation across re-ingest (FR-006 — new
sources add, existing entries by natural key replace-in-place not duplicate). Idempotency (FR-009/SC-007 — natural
key (student_id,source_id,entry_kind,key,item_ref); re-ingest does not grow entry_count). Hybrid value_num/value_text
coexist (FR-007). No net-new freetext collection (FR-008 — every value_text traces to a consumed-module freetext).
cohort_year derivation. EntryKind layer rule. Located errors on malformed input (FR-010/BND-01). Hunt edge cases:
duplicate student rows in Excel, missing columns, empty store, a student in only one layer.` },
  { key: 'retrieve-query', title: 'Retrieval & query grounding', files: 'retrieve/{evidence,query}.py',
    focus: `EVID-01 every factual claim cited; EVID-02 absent layer → no_evidence=True + literal "근거 없음" + correct
available_layers; EVID-03 narrative only from the evidence bundle. FR-011 freeform + question_set canonical questions;
FR-013 no fabrication when layer absent; FR-015 degrade transparency. Operates in pseudonym space; --reveal re-identifies
locally. Check: does a freeform query that matches nothing correctly emit no_evidence (not an empty-but-no_evidence answer)?
Does available_layers come from real data or a hardcoded list? Citation total-order sort stability.` },
  { key: 'privacy', title: 'PII boundary / pseudonymization (CROWN JEWEL — SC-004)', files: 'store/pseudonym.py, generate/{bundle,reidentify,backend,narrative}.py',
    focus: `THE highest-risk surface. PRIV-01: prove no 10-digit id, Hangul name, or email can reach a staging/*.json
or an LLM payload. Trace EXACTLY what goes into the bundle/prompt — is it built from pseudonym-space evidence only, or
could a value_text field carry leaked PII (e.g. a free-text answer containing a name/number)? PRIV-02 map not read while
building prompt. PRIV-03 bijective+deterministic ascending; re-check backlog (c): does adding a student renumber existing
pseudonyms (instability)? PRIV-05 absent/corrupt/non-bijective map or missing student_id at re-id → loud located error,
NO partial Gold. Adversarial: a value_text with an embedded 10-digit number or "홍길동 교수" — does the static PII scan in
the bundle builder catch it before send, or only the post-hoc verify? Is the scan applied to the actual LLM request payload?` },
  { key: 'determinism', title: 'Determinism & byte-identity', files: 'output/{determinism,manifest,paths,sha256}.py, store/codex.py, generate/backend.py',
    focus: `DET-01 parquet use_dictionary=False/write_statistics=False, deterministic sort of codex_entry, NO wall-clock
field in codex_entry (ingested_at only in source_ledger), re-ingest entry_count stable. DET-02 offline completion.
DET-03 cache key = SHA-256(prompt,facts,model,mode); cache hit byte-identical. Hunt: any list(set(...)) / dict iteration /
unsorted glob / PYTHONHASHSEED dependence (like retro-mester pipeline.py:426 bug); any datetime.now() leaking into a Silver/Gold
artifact other than the two sanctioned fields; YAML sort_keys; atomic temp+os.replace. JSON dump sort_keys. Re-check backlog
(b): are ALL consumed source hashes recorded in manifest.input_hashes, or can a source be silently absent from provenance?` },
  { key: 'distribution', title: 'Distribution / no-silent-skip / cross-leak', files: 'distribute/{roster,bundles,summary}.py',
    focus: `SKIP-02 codex-but-no-roster student in 미배정.md + unassigned_sids, assigned+unassigned==total EXACTLY.
SKIP-03 per-advisor bundle contains ONLY that advisor's advisees (cross-leak=0, SC-003). FR-018 never silent-drop.
Roster unique student_id (located error on dup). Adversarial: advisor_id = "../../etc" path traversal (commit a379ed0
claims a fix — verify it's complete: also advisor_id with "/", "..", absolute path, empty, very long, unicode). Stale
bundle clearing (does a re-run leave orphaned files from a removed advisee?). Count invariant arithmetic with a student
appearing twice. _index.md correctness.` },
  { key: 'llm-backend', title: 'LLM backend layer & fallback', files: 'generate/backend.py, generate/narrative.py, generate/bundle.py',
    focus: `[VERIFY] the anthropic SDK call signature is real and current (model id, messages, max_tokens) — flag any
unverified/incorrect API usage. subscription/api/none backends; none default → template (rendered_by=template);
unreachable api → template fallback unless --require-llm (then exit 4). Principle I: no hard stop by default. InputHashCache
correctness. Does the LLM path ever receive real PII (cross-check privacy dim)? Does the template fallback produce a
genuinely cited narrative or a degenerate stub? Is the prompt assembled from pseudonymized facts only? Error handling on
malformed LLM response (does it fall back loudly or silently mis-render?).` },
  { key: 'tests-tdd', title: 'Test quality & TDD rigor', files: 'modules/metric-codex/tests/**',
    focus: `Do tests ASSERT the invariant or merely exit==0 (the retro-mester anti-pattern)? For each SC/PRIV/EVID/DET/SKIP,
is there a test that would actually FAIL if the invariant broke? Blind spots from single-fixture/single-process testing
(e.g. determinism tested in one process can miss PYTHONHASHSEED). The skipped test test_cli_skeleton.py:113 ("empty parameter
set for subcommand") — is a real assertion silently disabled? Are RED tests genuine (would have failed pre-impl)? Negative-path
coverage: malformed Excel, corrupt pseudonym map, path-traversal advisor_id, PII-in-value_text, cache poisoning. Over-mocking
that hides real behavior. Property tests (hypothesis) present where claimed?` },
  { key: 'codequality', title: 'Code quality & constitution principles', files: 'all src + CLAUDE.md + constitution.md',
    focus: `Constitution fail-fast: any except:pass / bare except / silent return / swallowed error? Located error format
(file·row·column·expected/actual) actually populated? Type annotations on all params/returns (Principle/CLAUDE §4)?
Security: hardcoded secrets, eval/exec, subprocess(shell=True), non-parameterized SQL, path injection? Principle III: any
hardcoded column/sheet/label/advisor name that should be config? Dead code / unused abstractions / speculative flexibility
(CLAUDE §3.2-3.3)? Docstrings English Google-style; error strings English. Boundary validation only at boundaries (no
redundant internal defensive branches). Surgical-change hygiene.` },
  { key: 'integration', title: 'Cross-module integration & lineage', files: 'ingest/paideia_sources.py, ingest/bronze_copies.py, output/manifest.py',
    focus: `Principle II: metric-codex consumes immersio/needs-map SILVER (진단×시험결합/학생지표/exam_result/exam_item;
factor_scores/free_text_categorization) and makes its OWN Bronze copy of examen blueprint/curriculum (which are Silver-미영속) —
verify it NEVER reads another module's Bronze directly, and that the own-copy loaders validate via shared ExamenBlueprint/CurriculumMap.
Schema drift: does paideia_sources.py assume column/field names that the upstream Silver contracts may not guarantee (Principle III
hardcoding)? Missing optional source → layer simply absent (degrade), not a crash. Lineage: manifest.input_hashes + config_ids
record every consumed source+config so provenance is reconstructable (Principle V). Re-check backlog (a) cluster_names.json and
(b) missing-source-in-manifest here too. axis vocabulary alignment with the 8 canonical keys.` },
  { key: 'verify-gate', title: 'Verify-gate self-correctness', files: 'verify/checks.py',
    focus: `verify/checks.py is the delivery gate. For EACH invariant it claims to enforce (PRIV-01..05, EVID-01..03,
DET-01..03, SKIP-01..03, BND-01): does the check actually detect a real violation, or is it a no-op / weaker than its name /
checking the wrong artifact? Specifically: does the PII scan run over the REAL LLM request payloads and staging files (PRIV-01),
or a sanitized copy? Does EVID-01 truly map every narrative claim to a citation, or just count citations>0? Does the DET check
re-run and compare bytes, or trust a stored hash? Does it exit 3 (not 0) on each violation with a located message? Any invariant
listed in privacy.md that verify does NOT check at all (coverage gap)? commit 784a855 hardened this — confirm the hardening is real.` },
  { key: 'adversary', title: 'Adversarial personas / attack surface', files: 'cli/main.py + all input boundaries',
    focus: `Run ≥12 attacker personas and report each that SUCCEEDS (PERSONA_ATTACK_SUCCESS gate): (1) malicious roster
advisor_id path traversal / absolute path / symlink; (2) student_id with Unicode digits or zero-width chars passing \\d{10};
(3) duplicate student_id across two Excel rows with conflicting names; (4) value_text free-text carrying a real 10-digit number
or Korean name + role → reaches LLM/staging?; (5) pseudonym_map tampered to be non-bijective between ingest and generate;
(6) cache poisoning: a crafted input collides a cache key and serves another student's narrative; (7) re-ingest with a NEW
student to test pseudonym renumbering (PRIV-03); (8) roster student absent from codex (reverse of unassigned); (9) extremely
long / empty / control-char course or semester slug; (10) Excel with formula/CSV-injection cells (=cmd); (11) a question_set.yaml
with a question that has no matching layer → fabrication?; (12) concurrent/partial write leaving a half-written Gold file consumed
by distribute. For each persona: does the code defend (located error / safe degrade) or fail (leak / crash / silent skip)?` },
]

// ---------- JSON schemas ----------
const FINDINGS_SCHEMA = {
  type: 'object', additionalProperties: false,
  properties: {
    dimension: { type: 'string' },
    summary: { type: 'string', description: 'one-line dimension verdict' },
    files_read: { type: 'array', items: { type: 'string' }, description: 'actual files you opened' },
    findings: {
      type: 'array',
      items: {
        type: 'object', additionalProperties: false,
        properties: {
          id: { type: 'string', description: 'e.g. MC-SPEC-01 (prefix = dimension key uppercased)' },
          title: { type: 'string' },
          severity: { enum: ['critical', 'high', 'medium', 'low', 'info'] },
          location: { type: 'string', description: 'file:line(s)' },
          what_why: { type: 'string' },
          evidence: { type: 'string', description: 'what in the code proves this' },
          recommendation: { type: 'string' },
          violated_clause: { type: 'string', description: 'spec FR/SC / privacy.md ID / constitution principle / CLAUDE §' },
          runtime_repro_hint: { type: 'string', description: 'a concrete command/test to empirically confirm, or "" if static is sufficient' },
        },
        required: ['id', 'title', 'severity', 'location', 'what_why', 'evidence', 'recommendation', 'violated_clause', 'runtime_repro_hint'],
      },
    },
  },
  required: ['dimension', 'summary', 'files_read', 'findings'],
}

const VERDICT_SCHEMA = {
  type: 'object', additionalProperties: false,
  properties: {
    verdict: { enum: ['confirmed', 'partial', 'refuted'] },
    corrected_severity: { enum: ['critical', 'high', 'medium', 'low', 'info'] },
    rationale: { type: 'string' },
    repro: { type: 'string', description: 'what you re-read/ran to verify' },
    correction: { type: 'string', description: 'if the original framing was wrong, the corrected statement; else ""' },
    needs_runtime_repro: { type: 'boolean', description: 'true if only a live run can fully confirm' },
  },
  required: ['verdict', 'corrected_severity', 'rationale', 'repro', 'correction', 'needs_runtime_repro'],
}

const SYNTH_SCHEMA = {
  type: 'object', additionalProperties: false,
  properties: {
    overall_verdict: { type: 'string', description: '2-4 sentences: is the module ship-quality? key strengths + the defect clusters' },
    ship_recommendation: { enum: ['ship', 'ship-with-followups', 'block'] },
    blocking_gate_status: {
      type: 'object', additionalProperties: false,
      description: 'T061 blocking gates — any TRUE blocks merge',
      properties: {
        BOUNDARY_MISMATCH: { type: 'boolean' },
        INTEGRATION_MISSING: { type: 'boolean' },
        SILENT_SKIP_NEW: { type: 'boolean' },
        PERSONA_ATTACK_SUCCESS: { type: 'boolean' },
        notes: { type: 'string' },
      },
      required: ['BOUNDARY_MISMATCH', 'INTEGRATION_MISSING', 'SILENT_SKIP_NEW', 'PERSONA_ATTACK_SUCCESS', 'notes'],
    },
    unique_findings: {
      type: 'array',
      description: 'deduped across dimensions; merge same-root-cause findings into one with cross-refs',
      items: {
        type: 'object', additionalProperties: false,
        properties: {
          id: { type: 'string' },
          title: { type: 'string' },
          final_severity: { enum: ['critical', 'high', 'medium', 'low', 'info'] },
          verdict: { enum: ['confirmed', 'partial', 'refuted'] },
          dimensions: { type: 'array', items: { type: 'string' } },
          location: { type: 'string' },
          summary: { type: 'string' },
          recommendation: { type: 'string' },
          violated_clause: { type: 'string' },
        },
        required: ['id', 'title', 'final_severity', 'verdict', 'dimensions', 'location', 'summary', 'recommendation', 'violated_clause'],
      },
    },
    tally: { type: 'string', description: 'markdown table: severity × confirmed/partial/refuted counts (unique findings)' },
  },
  required: ['overall_verdict', 'ship_recommendation', 'blocking_gate_status', 'unique_findings', 'tally'],
}

const CRITIC_SCHEMA = {
  type: 'object', additionalProperties: false,
  properties: {
    gaps: {
      type: 'array',
      items: {
        type: 'object', additionalProperties: false,
        properties: {
          area: { type: 'string' },
          why_it_matters: { type: 'string' },
          suggested_check: { type: 'string' },
        },
        required: ['area', 'why_it_matters', 'suggested_check'],
      },
    },
    coverage_assessment: { type: 'string' },
  },
  required: ['gaps', 'coverage_assessment'],
}

// ---------- severity helpers ----------
const SEV_ORDER = ['info', 'low', 'medium', 'high', 'critical']
function consensus(votes) {
  const v = votes.filter(Boolean)
  if (!v.length) return { verdict: 'partial', severity: 'low', note: 'no verifier returned' }
  const c = v.filter(x => x.verdict === 'confirmed').length
  const p = v.filter(x => x.verdict === 'partial').length
  const r = v.filter(x => x.verdict === 'refuted').length
  let verdict
  if (r > c + p) verdict = 'refuted'
  else if (c >= p && c >= r) verdict = 'confirmed'
  else verdict = 'partial'
  // severity = most common corrected_severity among non-refuted; tie → highest
  const live = v.filter(x => x.verdict !== 'refuted')
  const pool = (live.length ? live : v).map(x => x.corrected_severity)
  const counts = {}
  for (const s of pool) counts[s] = (counts[s] || 0) + 1
  let best = pool[0], bestN = -1
  for (const s of Object.keys(counts)) {
    if (counts[s] > bestN || (counts[s] === bestN && SEV_ORDER.indexOf(s) > SEV_ORDER.indexOf(best))) {
      best = s; bestN = counts[s]
    }
  }
  return { verdict, severity: best, votes: v }
}

// ========================= PHASE 1+2: review → verify (pipelined) =========================
phase('Review')
log(`Auditing metric-codex across ${DIMENSIONS.length} dimensions; each finding adversarially verified.`)

const reviewed = await pipeline(
  DIMENSIONS,
  // stage 1: find
  (d) => agent(
    `${COMMON}\n\n=== YOUR DIMENSION: ${d.title} (${d.key}) ===\nPrimary files: ${d.files}\nFocus:\n${d.focus}\n\n` +
    `Read the actual source. Report ALL real findings for THIS dimension (deduped within your dimension, ` +
    `ordered by severity, at most ~8). Use id prefix MC-${d.key.toUpperCase().replace(/[^A-Z]/g, '')}. ` +
    `If the dimension is clean, return an empty findings array and say so in summary. Do not invent findings to fill space.`,
    { label: `find:${d.key}`, phase: 'Review', schema: FINDINGS_SCHEMA },
  ),
  // stage 2: verify each finding (3 perspective-diverse skeptics for high/critical, else 1)
  (review, d) => {
    const findings = (review && review.findings) || []
    return parallel(findings.map((f) => () => {
      const hard = f.severity === 'critical' || f.severity === 'high'
      const lenses = hard
        ? [
            'CORRECTNESS RE-READ: open the cited file:line yourself and confirm the code literally does what the finding claims. Quote the decisive lines.',
            'REFUTATION: find the STRONGEST reason this finding is wrong — a false positive, a guard elsewhere that already mitigates it, intended/spec-sanctioned behavior, or a test that already covers it. Default toward refuting if the evidence is thin.',
            'SEVERITY CALIBRATION: assume it is real — is the severity right? Consider real-world trigger frequency, whether a green test would catch a regression, and blast radius. Adjust corrected_severity accordingly.',
          ]
        : [
            'Re-read the cited code, then either confirm or refute. Check for a mitigating guard/test elsewhere and calibrate severity to real impact. Default toward refuting if evidence is thin.',
          ]
      return parallel(lenses.map((lens, i) => () =>
        agent(
          `${COMMON}\n\n=== ADVERSARIAL VERIFICATION ===\nA prior auditor (dimension ${d.key}) raised this finding:\n` +
          `id: ${f.id}\ntitle: ${f.title}\nseverity(claimed): ${f.severity}\nlocation: ${f.location}\n` +
          `what/why: ${f.what_why}\nevidence: ${f.evidence}\nviolated_clause: ${f.violated_clause}\n` +
          `recommendation: ${f.recommendation}\n\nYOUR LENS: ${lens}\n\n` +
          `Open the cited files yourself and judge. Return your independent verdict (confirmed/partial/refuted), ` +
          `a corrected_severity, your rationale, and exactly what you re-read. Be a skeptic, not a rubber stamp.`,
          { label: `verify:${f.id}#${i}`, phase: 'Verify', schema: VERDICT_SCHEMA },
        ),
      )).then((votes) => {
        const con = consensus(votes)
        return { finding: f, dimension: d.key, verdict: con.verdict, final_severity: con.severity, votes: votes.filter(Boolean) }
      })
    }))
  },
)

const allVerified = reviewed.flat().filter(Boolean)
const surviving = allVerified.filter((x) => x.verdict !== 'refuted')
const refuted = allVerified.filter((x) => x.verdict === 'refuted')
log(`Raw findings: ${allVerified.length}; surviving verification: ${surviving.length}; refuted: ${refuted.length}.`)

// ========================= PHASE 3: synthesize + completeness critic =========================
phase('Synthesize')

const payload = JSON.stringify(
  surviving.map((x) => ({
    id: x.finding.id, title: x.finding.title, dimension: x.dimension,
    verdict: x.verdict, severity: x.final_severity, location: x.finding.location,
    what_why: x.finding.what_why, recommendation: x.finding.recommendation,
    violated_clause: x.finding.violated_clause,
  })),
)

const [synthesis, critic] = await parallel([
  () => agent(
    `${COMMON}\n\n=== SYNTHESIS ===\nHere are the verification-surviving findings (confirmed/partial) as JSON:\n${payload}\n\n` +
    `Also note ${refuted.length} findings were refuted (excluded). Produce the audit synthesis:\n` +
    `1) Merge duplicate/same-root-cause findings reported by different dimensions into ONE unique finding (list its dimensions[]).\n` +
    `2) Assign each unique finding a final_severity (respect the verifiers' corrected severity).\n` +
    `3) Decide the T061 blocking-gate status: BOUNDARY_MISMATCH (a Pydantic/contract boundary not enforced),\n` +
    `   INTEGRATION_MISSING (a required cross-module Silver consumption / manifest lineage absent),\n` +
    `   SILENT_SKIP_NEW (any NEW silent-skip / silent-drop / swallowed error), PERSONA_ATTACK_SUCCESS (any adversary persona that succeeds).\n` +
    `   A gate is TRUE only if a confirmed (not merely partial) finding triggers it; explain in notes.\n` +
    `4) Give an overall_verdict and ship_recommendation (ship / ship-with-followups / block).\n` +
    `5) Provide a markdown severity tally (unique findings).`,
    { label: 'synthesis', phase: 'Synthesize', schema: SYNTH_SCHEMA },
  ),
  () => agent(
    `${COMMON}\n\n=== COMPLETENESS CRITIC ===\nThe audit covered these dimensions: ${DIMENSIONS.map((d) => d.key).join(', ')}.\n` +
    `Surviving finding titles:\n${surviving.map((x) => '- ' + x.finding.id + ': ' + x.finding.title).join('\n') || '(none)'}\n\n` +
    `Act as a meta-reviewer: what did this audit likely MISS? Name concrete gaps — a spec clause not traced, a source file ` +
    `not opened, an invariant in privacy.md without a verify check, an attack persona not attempted, a runtime behavior only ` +
    `a live run would reveal. For each gap give the specific check that would close it. Be concrete and file-specific; do not pad.`,
    { label: 'completeness-critic', phase: 'Synthesize', schema: CRITIC_SCHEMA },
  ),
])

return {
  counts: { raw: allVerified.length, surviving: surviving.length, refuted: refuted.length },
  refuted: refuted.map((x) => ({ id: x.finding.id, title: x.finding.title, dimension: x.dimension })),
  surviving: surviving.map((x) => ({
    id: x.finding.id, title: x.finding.title, dimension: x.dimension, verdict: x.verdict,
    final_severity: x.final_severity, location: x.finding.location, what_why: x.finding.what_why,
    evidence: x.finding.evidence, recommendation: x.finding.recommendation,
    violated_clause: x.finding.violated_clause, runtime_repro_hint: x.finding.runtime_repro_hint,
    vote_summary: x.votes.map((v) => v.verdict + '/' + v.corrected_severity).join(' '),
  })),
  synthesis,
  critic,
}
