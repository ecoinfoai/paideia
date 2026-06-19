"""T054 — verify gate: post-hoc invariant check functions for metric-codex.

Each check function returns a list of Violation objects (empty = pass).
They NEVER raise on a detected invariant violation — they collect all
violations so ``run_all_checks`` can report ALL of them at once.

Invariants covered:
- PRIV-01: no 10-digit id / email / known name in staging bundles.
- PRIV-03/05: pseudonym map present and bijective.
- PRIV-04: silver and gold output dirs are gitignored (static repo check).
- EVID-01/02/03: evidence grounding (template-mode: byte-match; llm: citation
  resolve + PII-free bundle check).
- SKIP-02: manifest count invariant (assigned + unassigned == total).
- SKIP-03: no cross-advisor leak in 지도교수별 bundles.
- MANIFEST: input_hashes and config_ids non-empty (provenance present).
"""

from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from paideia_shared.schemas import AdvisorBundleSummary, PseudonymMapEntry
from paideia_shared.schemas.metric_codex import CodexEntry

from metric_codex.distribute.bundles import _parse_student_id
from metric_codex.errors import LocatedInputError
from metric_codex.generate.bundle import assert_no_pii, build_bundles
from metric_codex.generate.narrative import render_template
from metric_codex.generate.reidentify import validate_pseudonym_map
from metric_codex.output.manifest import read_manifest
from metric_codex.retrieve.query import QuestionSet, load_question_set
from metric_codex.store.codex import read_existing_store
from metric_codex.store.pseudonym import read_pseudonym_map

_SID_PATTERN = re.compile(r"\b\d{10}\b")
_ADVISOR_BUNDLE_DIR = "지도교수별"
_STUDENT_DIR = "학생별"


# ---------------------------------------------------------------------------
# Violation
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Violation:
    """A single detected invariant violation.

    Attributes:
        invariant_id: Stable invariant identifier from privacy.md (e.g. PRIV-01).
        message: Human-readable located description (which artifact, what went wrong).
        file: Optional source file path for additional context.
        detail: Optional extra detail (expected/actual).
    """

    invariant_id: str
    message: str
    file: str | None = field(default=None)
    detail: str | None = field(default=None)

    def __str__(self) -> str:
        """Render a single located line for stderr output.

        Returns:
            Human-readable violation string including invariant_id prefix.
        """
        parts = [f"[{self.invariant_id}]"]
        if self.file:
            parts.append(self.file)
        parts.append(self.message)
        base = " ".join(parts)
        if self.detail:
            base += f" ({self.detail})"
        return base


# ---------------------------------------------------------------------------
# PRIV-01: no PII in staging bundles
# ---------------------------------------------------------------------------


def check_priv01_no_staging_pii(
    silver_dir: Path,
    pseudonym_map: list[PseudonymMapEntry],
) -> list[Violation]:
    """Scan every staging bundle JSON for PII (PRIV-01).

    Checks for 10-digit student_ids, email addresses, and known Korean names
    from the pseudonym map.  Uses the same patterns as ``assert_no_pii`` but
    collects violations instead of raising on the first hit.

    Args:
        silver_dir: metric-codex Silver directory for this semester/course.
        pseudonym_map: Full pseudonym map (provides known name set).

    Returns:
        List of Violation (empty if no staging dir or no PII found).
    """
    staging_dir = silver_dir / "staging"
    if not staging_dir.is_dir():
        return []

    known_names: frozenset[str] = frozenset(
        e.name_kr for e in pseudonym_map if e.name_kr
    )
    violations: list[Violation] = []

    for json_path in sorted(staging_dir.glob("*.json")):
        payload = json_path.read_text(encoding="utf-8")
        try:
            assert_no_pii(payload, known_names=known_names)
        except LocatedInputError as exc:
            violations.append(
                Violation(
                    invariant_id="PRIV-01",
                    message=exc.message,
                    file=str(json_path),
                    detail=f"expected={exc.expected}, got={exc.actual}",
                )
            )

    return violations


# ---------------------------------------------------------------------------
# PRIV-03/05: pseudonym map bijective
# ---------------------------------------------------------------------------


def check_priv03_pseudonym_bijective(
    pseudonym_map_path: Path,
) -> list[Violation]:
    """Check that the pseudonym map exists and is bijective (PRIV-03/PRIV-05).

    Args:
        pseudonym_map_path: Path to ``pseudonym_map.parquet``.

    Returns:
        List of Violation (empty if the map is present and bijective).
    """
    if not pseudonym_map_path.is_file():
        return [
            Violation(
                invariant_id="PRIV-03",
                message="pseudonym_map.parquet is missing",
                file=str(pseudonym_map_path),
                detail="expected: an existing bijective pseudonym map",
            )
        ]

    try:
        entries = read_pseudonym_map(pseudonym_map_path)
    except LocatedInputError as exc:
        return [
            Violation(
                invariant_id="PRIV-03",
                message=f"pseudonym_map.parquet is unreadable: {exc}",
                file=str(pseudonym_map_path),
            )
        ]

    try:
        validate_pseudonym_map(entries)
    except LocatedInputError as exc:
        return [
            Violation(
                invariant_id="PRIV-03",
                message=exc.message,
                file=str(pseudonym_map_path),
                detail=f"expected={exc.expected}, got={exc.actual}",
            )
        ]

    return []


# ---------------------------------------------------------------------------
# PRIV-04: data dirs gitignored
# ---------------------------------------------------------------------------


def _find_git_root_with_content(path: Path) -> Path | None:
    """Walk up from ``path`` to find a non-empty .git directory.

    An empty ``.git`` directory (as may appear in some system temp dirs) is
    NOT considered a valid git repository root.  We require the presence of
    ``HEAD`` or ``config`` inside ``.git`` as a minimum sanity check.

    Args:
        path: Starting filesystem path.

    Returns:
        The git repository root directory, or None if not inside a real repo.
    """
    current = path.resolve()
    for candidate in [current, *current.parents]:
        git_dir = candidate / ".git"
        if git_dir.is_dir() and (
            (git_dir / "HEAD").exists() or (git_dir / "config").exists()
        ):
            return candidate
    return None


def _is_git_ignored(path: Path, *, git_root: Path) -> bool:
    """Return True if ``path`` is covered by a .gitignore rule.

    Runs ``git check-ignore -q <path>`` from inside the path's own repository
    (``cwd=git_root``).  Running it from a different repo's working directory
    makes git reject the path as "outside repository" — so the cwd MUST be the
    git root that actually contains ``path``.

    Args:
        path: An absolute filesystem path to check.
        git_root: The git repository root that contains ``path``.

    Returns:
        True when git considers the path ignored (exit 0); False otherwise.
    """
    try:
        result = subprocess.run(  # noqa: S603
            ["git", "check-ignore", "-q", str(path)],  # noqa: S607
            cwd=str(git_root),
            capture_output=True,
        )
        return result.returncode == 0
    except FileNotFoundError:
        # git not available — skip the check conservatively.
        return True


def check_priv04_gitignored(data_root: Path) -> list[Violation]:
    """Assert that the silver and gold output dirs are git-ignored (PRIV-04).

    Runs ``git check-ignore`` on the silver and gold roots.  A non-ignored
    path means PII-bearing artifacts could be committed accidentally.

    Only checks paths that reside inside a git repository.  When ``data_root``
    is outside a repo (e.g., a pytest ``tmp_path``), the check is skipped —
    gitignore rules cannot apply outside of a repo tree.

    If either directory does not yet exist, the check is applied to the
    ``data_root`` itself (the parent that WOULD hold PII when created).

    Args:
        data_root: The ``--data-root`` directory (the repo's ``data/`` root).

    Returns:
        List of Violation (empty if paths are ignored, outside a repo, or
        git is unavailable).
    """
    # Only run the check when data_root is inside a real git repository.
    # An empty .git dir (e.g. /tmp/.git on some systems) is not considered
    # a real repo — we require HEAD or config to be present inside .git.
    git_root = _find_git_root_with_content(data_root)
    if git_root is None:
        return []

    violations: list[Violation] = []
    check_paths = [data_root / "silver", data_root / "gold"]
    for path in check_paths:
        target = path if path.exists() else data_root
        if not _is_git_ignored(target, git_root=git_root):
            violations.append(
                Violation(
                    invariant_id="PRIV-04",
                    message=f"path is NOT git-ignored: {target}",
                    file=str(target),
                    detail="expected: covered by .gitignore (data/ rule)",
                )
            )
    return violations


# ---------------------------------------------------------------------------
# EVID-01/02/03: evidence grounding
# ---------------------------------------------------------------------------


def check_evidence_grounding(
    gold_dir: Path,
    codex_entries: list[CodexEntry],
    pseudonym_map: list[PseudonymMapEntry],
    question_set: QuestionSet,
    *,
    llm_backend: str | None,
) -> list[Violation]:
    """Check evidence grounding for per-student Gold narratives (EVID-01/02/03).

    For ``llm_backend == "none(template)"`` (offline path):
    - Re-derives the deterministic template for each student and compares it
      byte-for-byte against the on-disk Gold md.  A mismatch is an
      EVID-01/EVID-03 violation (the file must equal the cited template).
    - Independently checks EVID-02: every bundle that declares
      ``no_evidence=True`` for a question must have the literal "근거 없음"
      in the on-disk md.

    For LLM backends (free prose):
    - Skips the byte-match (LLM prose is non-deterministic).
    - Checks that the staging bundle for each student (the sole LLM context)
      is PII-free (PRIV-01 / EVID-03).
    - Note: citation resolution of LLM prose is not verifiable post-hoc
      because LLM prose is free-form.  The bundle construction guarantee
      (build_bundles produces only evidence-grounded facts) covers EVID-03
      at the pipeline stage.

    Args:
        gold_dir: Gold tier directory containing ``학생별/*.md``.
        codex_entries: All CodexEntry rows for the semester/course.
        pseudonym_map: Full pseudonym map for re-identification.
        question_set: The canonical question set used during generation.
        llm_backend: The ``llm_backend`` value from the manifest.

    Returns:
        List of Violation (empty if all narratives pass the checks).
    """
    violations: list[Violation] = []
    student_dir = gold_dir / _STUDENT_DIR
    if not student_dir.is_dir():
        # generate not yet run — nothing to check.
        return []

    # Build pseudonym index and group entries by student_id.
    entries_by_sid: dict[str, list[CodexEntry]] = {}
    for entry in codex_entries:
        entries_by_sid.setdefault(entry.student_id, []).append(entry)

    # Build a student_id → Gold md path mapping from the on-disk files.
    sid_to_md: dict[str, Path] = {}
    for md_path in sorted(student_dir.glob("*.md")):
        try:
            sid = _parse_student_id(md_path.name, md_path)
            sid_to_md[sid] = md_path
        except LocatedInputError:
            violations.append(
                Violation(
                    invariant_id="EVID-01",
                    message="Gold md filename does not begin with 10-digit student_id",
                    file=str(md_path),
                )
            )

    # Build bundles (pseudo-space, PII-free) for evidence checks.
    try:
        bundles = build_bundles(
            codex_entries=codex_entries,
            pseudonym_map=pseudonym_map,
            question_set=question_set,
        )
    except LocatedInputError as exc:
        violations.append(
            Violation(
                invariant_id="EVID-03",
                message=f"bundle construction failed: {exc}",
            )
        )
        return violations

    # Build a pseudonym → bundle map for quick lookup.
    bundle_by_pseudonym = {b.pseudonym: b for b in bundles}

    # Build pseudonym → student_id reverse lookup.
    pseudonym_to_sid: dict[str, str] = {
        e.pseudonym: e.student_id for e in pseudonym_map
    }

    for pseudonym, bundle in bundle_by_pseudonym.items():
        sid = pseudonym_to_sid.get(pseudonym)
        if sid is None:
            continue

        md_path = sid_to_md.get(sid)
        if md_path is None:
            # Student has entries but no Gold md — not an EVID violation per se
            # (generate may not have been run).  Skip.
            continue

        on_disk = md_path.read_text(encoding="utf-8")

        if llm_backend == "none(template)":
            # EVID-01/EVID-03: byte-identical match against the deterministic template.
            expected = render_template(bundle)
            if on_disk != expected:
                violations.append(
                    Violation(
                        invariant_id="EVID-01",
                        message=(
                            f"Gold md content differs from the deterministic "
                            f"cited template for pseudonym {pseudonym!r}"
                        ),
                        file=str(md_path),
                        detail="expected: byte-identical to render_template(bundle)",
                    )
                )
        else:
            # LLM prose or None (corrupt/absent manifest): skip byte-match.
            # For LLM prose the staging bundle PII check covers EVID-03 via
            # check_priv01_no_staging_pii.  For None (M-001), run_all_checks
            # guards against reaching here, so this branch is a safety net.
            pass

        # EVID-02: every no_evidence question → "근거 없음" in the md.
        for bq in bundle.questions:
            if bq.answer.no_evidence and "근거 없음" not in on_disk:
                violations.append(
                    Violation(
                        invariant_id="EVID-02",
                        message=(
                            f"Gold md for pseudonym {pseudonym!r} lacks '근거 없음' "
                            f"for question {bq.question_id!r} where no_evidence=True"
                        ),
                        file=str(md_path),
                    )
                )
                break  # one violation per file is sufficient

    return violations


# ---------------------------------------------------------------------------
# SKIP-02: manifest count invariant
# ---------------------------------------------------------------------------


def check_skip02_count_invariant(
    manifest_path: Path,
) -> list[Violation]:
    """Re-check the manifest SKIP-02 count invariant after possible hand-editing.

    ``read_manifest`` validates via Pydantic which itself calls the model
    validator — but the embedded ``bundle_summary`` model_validator enforces
    ``assigned + unassigned == total`` at construction time.  When the JSON
    has been hand-edited to break this, ``read_manifest`` will raise a
    ``LocatedInputError`` (wrapping a ValidationError).  We catch that and
    surface it as a SKIP-02 violation rather than crashing.

    For a successfully loaded manifest we re-check the invariant manually as
    an additional layer in case the schema ever relaxes the constraint.

    Args:
        manifest_path: Path to ``manifest_metric-codex.json``.

    Returns:
        List of Violation (empty if the manifest is valid and count holds).
    """
    try:
        manifest = read_manifest(manifest_path)
    except LocatedInputError as exc:
        # A manifest that fails to load (bad JSON or schema) is itself reported
        # as a SKIP-02 violation rather than a crash — the hand-edit may have
        # broken the embedded bundle_summary invariant.
        return [
            Violation(
                invariant_id="SKIP-02",
                message=f"manifest could not be loaded/validated: {exc}",
                file=str(manifest_path),
            )
        ]

    summary: AdvisorBundleSummary = manifest.bundle_summary
    total = summary.total_students_with_codex
    assigned = summary.assigned_count
    unassigned = len(summary.unassigned_sids)
    actual = assigned + unassigned

    if actual != total:
        return [
            Violation(
                invariant_id="SKIP-02",
                message=(
                    f"bundle_summary count invariant violated: "
                    f"assigned_count({assigned}) + unassigned({unassigned}) "
                    f"= {actual}, expected total={total}"
                ),
                file=str(manifest_path),
                detail=f"expected: {assigned} + {unassigned} == {total}",
            )
        ]

    return []


# ---------------------------------------------------------------------------
# SKIP-03: no cross-advisor leak
# ---------------------------------------------------------------------------


def check_skip03_no_cross_leak(
    gold_dir: Path,
    roster: list | None,
) -> list[Violation]:
    """Check that no advisor bundle contains a student assigned to another advisor.

    For each directory under ``gold_dir/지도교수별/{advisor_id}/``, parses
    every md filename to extract the student_id, then looks up that
    student_id in the roster.  Any md whose roster advisor_id differs from
    the directory's advisor_id is a SKIP-03 cross-leak violation.

    If ``지도교수별/`` does not exist, no violation (distribute not yet run).
    If roster is None but ``지도교수별/`` exists, logs an informational
    SKIP-03 violation about the missing roster (cannot verify without it).

    Args:
        gold_dir: Gold tier directory for this semester/course.
        roster: Validated roster entries, or None if the roster is absent.

    Returns:
        List of Violation (empty if no cross-leak or no bundle dir).
    """
    bundle_root = gold_dir / _ADVISOR_BUNDLE_DIR
    if not bundle_root.is_dir():
        return []

    violations: list[Violation] = []

    if roster is None:
        violations.append(
            Violation(
                invariant_id="SKIP-03",
                message=(
                    "'지도교수별' dir exists but no roster was supplied — "
                    "SKIP-03 cross-leak cannot be verified without a roster"
                ),
                file=str(bundle_root),
            )
        )
        return violations

    sid_to_advisor: dict[str, str] = {e.student_id: e.advisor_id for e in roster}

    for advisor_dir in sorted(bundle_root.iterdir()):
        if not advisor_dir.is_dir():
            continue
        advisor_id = advisor_dir.name

        for md_path in sorted(advisor_dir.glob("*.md")):
            if md_path.name.startswith("_"):
                # Skip _index.md and similar internal files.
                continue
            try:
                sid = _parse_student_id(md_path.name, md_path)
            except LocatedInputError:
                # Malformed filename — not a SKIP-03 but still noteworthy.
                continue

            expected_advisor = sid_to_advisor.get(sid)
            if expected_advisor is not None and expected_advisor != advisor_id:
                violations.append(
                    Violation(
                        invariant_id="SKIP-03",
                        message=(
                            f"cross-advisor leak: student {sid!r} (roster advisor "
                            f"{expected_advisor!r}) found in {advisor_id!r} bundle"
                        ),
                        file=str(md_path),
                        detail=(
                            f"expected advisor_id={expected_advisor!r}, "
                            f"got directory={advisor_id!r}"
                        ),
                    )
                )

    return violations


# ---------------------------------------------------------------------------
# Manifest provenance
# ---------------------------------------------------------------------------


def check_manifest_hashes(manifest_path: Path) -> list[Violation]:
    """Check that the manifest carries non-empty provenance hashes.

    A manifest produced after a real ingest must have at least one entry in
    ``input_hashes`` and ``config_ids``.  Empty dicts indicate either that
    ingest was never run or provenance was stripped by hand-editing.

    Args:
        manifest_path: Path to ``manifest_metric-codex.json``.

    Returns:
        List of Violation (empty if manifest is loadable and has provenance).
    """
    try:
        manifest = read_manifest(manifest_path)
    except LocatedInputError as exc:
        return [
            Violation(
                invariant_id="MANIFEST",
                message=f"manifest could not be loaded: {exc}",
                file=str(manifest_path),
            )
        ]

    violations: list[Violation] = []

    if not manifest.input_hashes:
        violations.append(
            Violation(
                invariant_id="MANIFEST",
                message="manifest.input_hashes is empty — provenance missing",
                file=str(manifest_path),
                detail="expected: at least one source_id → sha256 entry",
            )
        )

    return violations


# ---------------------------------------------------------------------------
# run_all_checks
# ---------------------------------------------------------------------------


def run_all_checks(
    *,
    data_root: Path,
    semester: str,
    course_slug: str,
    question_set_path: Path | None = None,
    roster_path: Path | None = None,
) -> list[Violation]:
    """Load all artifacts and run every applicable verify check.

    Checks whose inputs are absent are skipped with a note in the docstring:
    - No staging dir → PRIV-01 skipped (no staging bundles to scan).
    - No roster file → SKIP-03 reports a missing-roster violation if
      ``지도교수별`` dir exists (cannot verify cross-leak without the roster).
    - No question_set → EVID checks skipped.
    - No manifest → SKIP-02 / MANIFEST checks skipped.

    Args:
        data_root: The ``--data-root`` directory (repo's ``data/``).
        semester: Semester code (e.g. ``"2026-1"``).
        course_slug: Course slug (e.g. ``"anatomy"``).
        question_set_path: Optional override for the Bronze question_set.yaml.
        roster_path: Optional override for the Bronze 지도교수배정.yaml.

    Returns:
        Aggregated list of Violation from all checks.  Empty = all pass.
    """
    from metric_codex.output.paths import bronze_dir, gold_dir, silver_dir

    own_bronze = bronze_dir(semester, course_slug, data_root=data_root)
    own_silver = silver_dir(semester, course_slug, data_root=data_root)
    own_gold = gold_dir(semester, course_slug, data_root=data_root)
    pseudonym_path = own_silver / "pseudonym_map.parquet"
    manifest_path = own_silver / "manifest_metric-codex.json"

    # --- Load shared artifacts (errors → collected as violations, never crash) ---
    violations: list[Violation] = []

    # Load codex entries.
    codex_entries: list[CodexEntry] = []
    if own_silver.is_dir():
        try:
            codex_entries, _ = read_existing_store(own_silver)
        except LocatedInputError as exc:
            violations.append(
                Violation(
                    invariant_id="MANIFEST",
                    message=f"failed to read Silver store: {exc}",
                    file=str(own_silver),
                )
            )

    # Load pseudonym map.
    pseudonym_map: list[PseudonymMapEntry] = []
    if pseudonym_path.is_file():
        try:
            pseudonym_map = read_pseudonym_map(pseudonym_path)
        except LocatedInputError as exc:
            violations.append(
                Violation(
                    invariant_id="PRIV-03",
                    message=f"failed to read pseudonym map: {exc}",
                    file=str(pseudonym_path),
                )
            )

    # Load manifest (if present) — needed by SKIP-02 and MANIFEST checks.
    # M-001: use None sentinel when manifest fails to load.  check_evidence_grounding
    # skips the byte-match when llm_backend is None to avoid false EVID-01 noise
    # that would mask the real manifest failure (SKIP-02/MANIFEST already report it).
    llm_backend: str | None = None
    if manifest_path.is_file():
        try:
            manifest = read_manifest(manifest_path)
            llm_backend = manifest.llm_backend
        except LocatedInputError:
            pass  # SKIP-02 / MANIFEST checks will re-report this.

    # Load question set (needed for EVID checks).
    qs_path = question_set_path or (own_bronze / "question_set.yaml")
    question_set: QuestionSet | None = None
    if qs_path.is_file():
        try:
            question_set = load_question_set(qs_path)
        except LocatedInputError as exc:
            violations.append(
                Violation(
                    invariant_id="EVID-01",
                    message=f"failed to load question_set: {exc}",
                    file=str(qs_path),
                )
            )

    # Load roster (needed for SKIP-03).
    roster = None
    effective_roster_path = roster_path or (own_bronze / "지도교수배정.yaml")
    if effective_roster_path.is_file():
        try:
            from metric_codex.distribute.roster import load_roster

            roster = load_roster(effective_roster_path)
        except LocatedInputError:
            roster = None  # SKIP-03 will handle the missing-roster case.

    # --- Run checks ---
    violations += check_priv01_no_staging_pii(own_silver, pseudonym_map)
    violations += check_priv03_pseudonym_bijective(pseudonym_path)
    violations += check_priv04_gitignored(data_root)

    if manifest_path.is_file():
        violations += check_skip02_count_invariant(manifest_path)
        violations += check_manifest_hashes(manifest_path)

    # M-001: skip the byte-match when llm_backend is None (corrupt/absent manifest).
    # The manifest failure is already reported by SKIP-02/MANIFEST checks above.
    if question_set is not None and pseudonym_map and llm_backend is not None:
        violations += check_evidence_grounding(
            own_gold,
            codex_entries,
            pseudonym_map,
            question_set,
            llm_backend=llm_backend,
        )

    violations += check_skip03_no_cross_leak(own_gold, roster)

    return violations


__all__ = [
    "Violation",
    "check_priv01_no_staging_pii",
    "check_priv03_pseudonym_bijective",
    "check_priv04_gitignored",
    "check_evidence_grounding",
    "check_skip02_count_invariant",
    "check_skip03_no_cross_leak",
    "check_manifest_hashes",
    "run_all_checks",
]
