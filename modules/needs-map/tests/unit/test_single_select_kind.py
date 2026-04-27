"""V7 / V8 negative-path coverage for single_select kind misuse [T029].

contracts/cli.md "매핑 YAML kind 검증 실패 메시지 형식" + spec FR-011 require
that a mapping YAML targeting a quantitative axis with a non-likert kind is
rejected at load time. ``MappingColumn`` V7 enforces aggregate='mean' is
likert-only; ``DiagnosticMappingConfig`` V6 enforces axes.required is the
8-key vocabulary.

This test exercises the *load* path (``needs_map.io.mapping.load_mapping``)
end-to-end on synthetic YAML fixtures so the operator-facing error block
from contracts/cli.md is also exercised, not just the bare Pydantic
validator (covered by tests/contract/test_shared_schemas_v0_1_1.py).

Spec: 003-needs-map-v0-1-1/tasks.md T029.
"""

from __future__ import annotations

from pathlib import Path

import pytest


_FULL_REQUIRED = (
    "digital_efficacy",
    "motivation",
    "time_availability",
    "material_preference",
    "study_strategy",
    "study_environment",
    "social_learning",
    "feedback_seeking",
)

_REQUIRED_BLOCK = "\n".join(f"    - {axis}" for axis in _FULL_REQUIRED)


def _eight_likert_lines(skip_axis: str | None = None) -> list[str]:
    """Return YAML lines for the 8 likert columns (no leading/trailing newlines)."""
    lines: list[str] = []
    for axis in _FULL_REQUIRED:
        if axis == skip_axis:
            continue
        lines.extend(
            [
                f"  - source: 'Q_{axis}'",
                "    kind: likert",
                f"    axis: {axis}",
                "    aggregate: mean",
            ]
        )
    return lines


def _build_yaml(extra_columns: list[str], optional: list[str] | None = None) -> str:
    """Compose a v0.1.1 mapping YAML body with the 8 likert + extra columns."""
    body_lines: list[str] = [
        "metadata:",
        "  semester: '2026-1'",
        "  course_slug: anatomy",
        "  mapping_version: 2",
        "columns:",
        "  - source: '학번'",
        "    kind: identity",
        *_eight_likert_lines(),
        *extra_columns,
        "axes:",
        "  required:",
        _REQUIRED_BLOCK,
    ]
    if optional:
        body_lines.append("  optional:")
        body_lines.extend(f"    - {key}" for key in optional)
    return "\n".join(body_lines) + "\n"


def _write_mapping(tmp_path: Path, body: str) -> Path:
    target = tmp_path / "anatomy.diagnostic.yaml"
    target.write_text(body, encoding="utf-8")
    return target


def test_single_select_targeting_quant_axis_rejected_with_v7_message(
    tmp_path: Path,
) -> None:
    """single_select column targeting a quantitative axis (motivation) MUST raise.

    The V7 validator requires ``aggregate='mean'`` only on likert; loading
    such a YAML via ``load_mapping`` triggers the operator-actionable
    multi-line block from contracts/cli.md.
    """
    from needs_map.io.mapping import MappingKindError, load_mapping

    extra = [
        "  - source: 'Q_extra_motivation_select'",
        "    kind: single_select",
        "    axis: motivation",
        "    aggregate: mean",
    ]
    body = _build_yaml(extra)
    path = _write_mapping(tmp_path, body)
    with pytest.raises(MappingKindError) as exc:
        load_mapping(path)
    msg = str(exc.value)
    assert "motivation" in msg
    assert "single_select" in msg
    assert "likert" in msg.lower()


def test_single_select_targeting_auxiliary_axis_loads_ok(
    tmp_path: Path,
) -> None:
    """single_select on AuxiliaryGroupKey (prior_readiness) MUST load."""
    from needs_map.io.mapping import load_mapping

    extra = [
        "  - source: 'Q5_prior'",
        "    kind: single_select",
        "    axis: prior_readiness",
    ]
    body = _build_yaml(extra, optional=["prior_readiness"])
    path = _write_mapping(tmp_path, body)
    config = load_mapping(path)
    aux = [c for c in config.columns if c.kind == "single_select"]
    assert len(aux) == 1
    assert aux[0].axis == "prior_readiness"


def test_multiselect_with_aggregate_mean_rejected(tmp_path: Path) -> None:
    """multiselect + aggregate=mean is V7-rejected (FR-011) regardless of axis."""
    from needs_map.io.mapping import MappingKindError, load_mapping
    from pydantic import ValidationError

    extra = [
        "  - source: 'Q11_topics'",
        "    kind: multiselect",
        "    axis: interest_topics",
        "    aggregate: mean",
    ]
    body = _build_yaml(extra, optional=["interest_topics"])
    path = _write_mapping(tmp_path, body)
    # interest_topics is auxiliary (not quantitative), so the V7 message in
    # ``mapping.py`` does not get re-wrapped into a MappingKindError — the
    # generic ValidationError carries the V7 prefix instead.
    with pytest.raises((MappingKindError, ValidationError)) as exc:
        load_mapping(path)
    assert "V7" in str(exc.value) or "mean" in str(exc.value).lower()
