"""needs-map pipeline orchestration (T031 skeleton; phases wired in T056/T074/T105).

This is the single trusted channel between CLI arguments and downstream phase
functions. ``NeedsMapArgs`` (Phase 2 design alignment §6 final draft) is a
frozen Pydantic model that bundles every argument plus run-time constants
(``created_at_utc`` cached once at instantiation). All phase functions accept
fields from this struct by explicit keyword arguments — defaults on the model
are restricted to truly run-time-derivable items, so a missing CLI flag never
silently becomes a hard-coded default (qa Stage-2 mitigation).

T031 deliberately leaves Phase A-F bodies as ``NotImplementedError`` stubs.
T056 (US1) wires Phase A+B, T074 (US2) wires Phase C, T105 (US3) wires
Phase D-F. Each wiring task MUST send an INTEGRATION tag to qa-engineer per
Rule 4 (Phase 2 §2).
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated, Literal

from paideia_shared.schemas import (
    CourseSlug,
    NeedsMapManifest,
    SemesterCode,
)
from pydantic import BaseModel, ConfigDict, Field

from .llm.fallback import LLMCallTracker

PhaseSet = frozenset[Literal["A", "B", "C", "D", "E", "F"]]


def _now_utc_iso() -> str:
    """Single canonical ISO8601 UTC timestamp (no microseconds, terminal Z)."""
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


class NeedsMapArgs(BaseModel):
    """Authoritative bundle of CLI arguments + resolved environment + run-time constants.

    All downstream phase functions receive this struct (or fields from it) by
    explicit keyword arguments. Identity, phase selection, IO roots, seed,
    LLM provider/model, and ``llm_enabled`` are required-for-invariants and
    have no defaults at the model level — the CLI dispatcher fills them
    (cli/main.py T032). Truly run-time-derivable items
    (``created_at_utc``, ``llm_timeout_seconds``, ``llm_retries``,
    ``keyword_language``, ``dry_run``, ``verbose``) carry defaults.

    Phase 2 design alignment §6.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    # --- identity (required, FR-002) ---
    semester: SemesterCode
    course_slug: CourseSlug

    # --- phase selection (required, FR-025) ---
    phases: PhaseSet

    # --- IO roots (required, FR-001/002) ---
    input_root: Path
    output_root: Path

    # --- determinism (required-for: SC-002, FR-022, axis 1·2·3) ---
    seed: int  # No default — CLI dispatcher resolves --seed | env | 42
    created_at_utc: Annotated[
        str, Field(pattern=r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")
    ] = Field(default_factory=_now_utc_iso)

    # --- clustering (FR-009/010) ---
    k_override: Annotated[int, Field(ge=2, le=6)] | None = None
    # k_override=1 is rejected at CLI layer (T032/T075 — cli.md exit 1).

    # --- LLM (FR-LLM-001/002, priority §3.2: --no-llm > env presence) ---
    llm_enabled: bool
    llm_provider: Literal["anthropic", "openai"]
    llm_model: Annotated[str, Field(min_length=1)]
    llm_timeout_seconds: Annotated[float, Field(gt=0)] = 30.0
    llm_retries: Annotated[int, Field(ge=0)] = 1

    # --- free-text (FR-014/026) ---
    keyword_language: Annotated[str, Field(pattern=r"^[a-z]{2}$")] = "ko"

    # --- operational ---
    dry_run: bool = False
    verbose: bool = False

    @property
    def output_key(self) -> str:
        """Concatenation used for the per-run directory and manifest field."""
        return f"{self.semester}-{self.course_slug}"


def _silver_dir(args: NeedsMapArgs) -> Path:
    return args.output_root / "silver" / "needs-map" / args.output_key


def _gold_dir(args: NeedsMapArgs) -> Path:
    return args.output_root / "gold" / "needs-map" / args.output_key


def run_needs_map(args: NeedsMapArgs) -> NeedsMapManifest:
    """Orchestrate Phase A-F per ``args.phases``.

    Skeleton implementation: each requested phase raises NotImplementedError
    so integration tests (T034 cli_smoke) RED as the Phase 3 entry signal.
    Wired progressively:
      - Phase A,B → T056 (US1)
      - Phase C   → T074 (US2)
      - Phase D,E,F → T105 (US3)

    Args:
        args: Frozen :class:`NeedsMapArgs` bundle.

    Returns:
        Validated :class:`NeedsMapManifest` after all requested phases finish
        and all Pydantic-validated outputs are written to disk.

    Raises:
        NotImplementedError: Whenever the requested phase is not yet wired.
            This is the deliberate RED signal for Phase 3 entry.
    """
    if not isinstance(args, NeedsMapArgs):
        raise TypeError(
            f"run_needs_map: expected NeedsMapArgs, got {type(args).__name__}."
        )

    tracker = LLMCallTracker()  # noqa: F841 — wired by T056/T074/T105
    silver = _silver_dir(args)
    gold = _gold_dir(args)
    _ = silver, gold  # paths resolved up-front so dry-run / debug output can echo them

    if args.dry_run:
        # Dry-run never writes; surfaces the resolved plan only. Wiring tasks
        # may extend this to print the plan; for the skeleton the early-return
        # of NotImplementedError below is enough.
        pass

    for phase in ("A", "B", "C", "D", "E", "F"):
        if phase in args.phases:
            raise NotImplementedError(
                f"Phase {phase} not wired yet — pending T056/T074/T105 "
                f"(skeleton T031). args.phases={sorted(args.phases)}."
            )

    raise NotImplementedError(
        "run_needs_map: no phases requested — args.phases is empty."
    )
