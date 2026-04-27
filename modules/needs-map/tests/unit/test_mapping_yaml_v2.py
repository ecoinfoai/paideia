"""YAML anchor/alias support for the v0.1.1 mapping schema [T030].

Per spec FR-009 + research §R-08, ``ordinal_maps`` may live as a top-level
block of YAML anchors that ``columns[*].ordinal_map`` references via
``*alias``. ``pyyaml.safe_load`` resolves anchors automatically; the loader
must drop the unrecognised top-level ``ordinal_maps`` key before forwarding
to Pydantic (T018 implementation).

This test loads a synthetic v0.1.1 fixture where two likert columns share
one anchored ordinal_map and asserts both columns end up with the same
dict, end-to-end, through ``load_mapping``.

Spec: 003-needs-map-v0-1-1/tasks.md T030;
contracts/mapping_yaml_v2.md "최상위 구조".
"""

from __future__ import annotations

from pathlib import Path

_FIXTURE = Path(
    "modules/needs-map/tests/fixtures/mappings/mapping_v2_with_anchors.yaml"
)


def test_anchor_alias_shared_between_two_likert_columns() -> None:
    """Two likert columns referencing the same anchor share the resolved dict."""
    from needs_map.io.mapping import load_mapping

    config = load_mapping(_FIXTURE)
    motivation_cols = [
        c for c in config.columns if c.kind == "likert" and c.axis == "motivation"
    ]
    study_strategy_cols = [
        c for c in config.columns if c.kind == "likert" and c.axis == "study_strategy"
    ]
    assert len(motivation_cols) >= 1
    assert len(study_strategy_cols) >= 1

    expected_map = {
        "전혀 그렇지 않다.": 1,
        "그렇지 않다.": 2,
        "조금 그렇지 않다.": 3,
        "보통이다.": 4,
        "조금 그렇다.": 5,
        "그렇다.": 6,
        "매우 그렇다.": 7,
    }
    assert motivation_cols[0].ordinal_map == expected_map
    assert study_strategy_cols[0].ordinal_map == expected_map


def test_anchor_resolved_drops_top_level_holder() -> None:
    """``ordinal_maps`` top-level block is silently dropped before validation.

    DiagnosticMappingConfig has ``extra='forbid'``; without the loader's
    explicit drop, the holder would surface as a Pydantic ValidationError.
    """
    from needs_map.io.mapping import load_mapping

    # Bare reload — if drop logic regressed this would raise.
    config = load_mapping(_FIXTURE)
    assert config.metadata.mapping_version == 2
