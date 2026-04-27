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

import pytest

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


# ---------------------------------------------------------------------------
# Adversary contract (T030 followup) — YAML safe_load + size cap
# ---------------------------------------------------------------------------


def test_yaml_python_object_apply_blocked(tmp_path: Path) -> None:
    """``!!python/object/apply`` MUST raise — load_mapping uses safe_load.

    Adversary scenario: operator (or compromised supply-chain artifact)
    embeds an arbitrary-code-execution tag in the mapping YAML.
    yaml.safe_load refuses such tags (only the safe constructor set), so
    an attempt to load them raises ``yaml.constructor.ConstructorError``
    (a subclass of ``yaml.YAMLError``) before any Pydantic validator runs.
    """
    import yaml
    from needs_map.io.mapping import load_mapping

    target = tmp_path / "rogue.yaml"
    target.write_text(
        "metadata:\n"
        "  semester: '2026-1'\n"
        "  course_slug: anatomy\n"
        "  mapping_version: 2\n"
        "  course_name_kr: !!python/object/apply:os.system ['echo pwned']\n"
        "columns: []\n"
        "axes:\n"
        "  required: []\n",
        encoding="utf-8",
    )
    with pytest.raises(yaml.YAMLError):
        load_mapping(target)


def test_mapping_file_size_cap_rejected(tmp_path: Path) -> None:
    """Mapping YAML > size cap (256 KB) MUST be rejected.

    Adversary DoS guard: a YAML balloon (e.g. anchor multiplication, deeply
    nested aliases) can exhaust memory at parse time. The loader rejects
    files larger than the cap before yaml.safe_load is even called.
    """
    from needs_map.io.mapping import MappingFileTooLargeError, load_mapping

    target = tmp_path / "huge.yaml"
    payload = "# " + "x" * 100 + "\n"
    chunks = (300 * 1024 // len(payload)) + 1
    target.write_text(payload * chunks, encoding="utf-8")
    with pytest.raises(MappingFileTooLargeError) as exc:
        load_mapping(target)
    msg = str(exc.value)
    assert "size" in msg.lower() or "256" in msg or "KB" in msg


def test_load_uses_yaml_safe_load_only() -> None:
    """``load_mapping`` source MUST call ``yaml.safe_load`` exclusively.

    Regression guard against accidentally switching to ``yaml.load`` (which
    enables the FullLoader and re-introduces arbitrary code execution).
    """
    import inspect

    from needs_map.io import mapping as mapping_module

    source = inspect.getsource(mapping_module)
    assert "yaml.safe_load" in source
    assert "yaml.load(" not in source, (
        "yaml.load() detected — use yaml.safe_load to block !!python tags."
    )
