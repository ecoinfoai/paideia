"""Determinism guard for the silver_phase3_* fixture builder (T014/T015).

Verifies that ``build_silver_phase3.build_all()`` is byte-identical across
re-runs, and in particular that the SPEC-GAP-001 ``cluster_names.json``
sidecar is canonicalised (``sort_keys=True, ensure_ascii=False``) per
qa-engineer option A — a future patch that replaces the fixture's sidecar
with the real needs-map output must keep the exact same bytes.

Scope: this test re-runs the full builder into a temporary directory and
hashes every parquet/json file. It is NOT a contract test for the silver
schemas (those live in ``tests/contract/combine/``) — it strictly enforces
that random seed pinning + JSON canonicalisation + pyarrow flag pinning
hold together.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
from types import ModuleType


def _load_builder() -> ModuleType:
    """Import ``build_silver_phase3`` from the fixtures directory.

    The fixtures dir is not a Python package (no top-level ``__init__``
    on the path), so we resolve the module by file path. Cached on first
    call via the module's own ``__cached__``.
    """
    here = Path(__file__).resolve()
    fixtures_root = here.parents[2] / "fixtures"
    builder_path = fixtures_root / "build_silver_phase3.py"
    spec = importlib.util.spec_from_file_location("build_silver_phase3", builder_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"could not load builder from {builder_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


build_all = _load_builder().build_all


def _digests_under(root: Path) -> dict[str, str]:
    """SHA256 every parquet/json file under ``root`` (relative paths)."""
    out: dict[str, str] = {}
    for p in sorted(root.rglob("*")):
        if not p.is_file() or p.suffix not in (".parquet", ".json"):
            continue
        out[str(p.relative_to(root))] = hashlib.sha256(p.read_bytes()).hexdigest()
    return out


def test_build_all_is_byte_deterministic(tmp_path: Path) -> None:
    """Two consecutive ``build_all`` invocations land byte-identical artifacts."""
    run1 = tmp_path / "run1"
    run2 = tmp_path / "run2"
    run1.mkdir()
    run2.mkdir()
    build_all(run1)
    build_all(run2)

    d1 = _digests_under(run1)
    d2 = _digests_under(run2)

    # Same set of relative paths (no extra files / no missing files).
    assert sorted(d1.keys()) == sorted(d2.keys()), (
        f"file inventory diverged: only-in-run1={set(d1) - set(d2)}, "
        f"only-in-run2={set(d2) - set(d1)}"
    )
    for rel, h1 in d1.items():
        assert h1 == d2[rel], f"byte-identical violation for {rel}"


def test_cluster_names_sidecar_canonical_json(tmp_path: Path) -> None:
    """SPEC-GAP-001 sidecar must be canonical JSON (sort_keys + non-ASCII Korean).

    qa-engineer option A locks down the sidecar's serialisation policy so
    that when the real needs-map patch lands, the file content is
    bit-identical to the fixture's content.
    """
    out = tmp_path / "fixtures"
    out.mkdir()
    build_all(out)

    # Minimal fixture sidecar — k=3 case.
    sidecar = (
        out
        / "silver_phase3_minimal"
        / "silver"
        / "needs-map"
        / "2026-1-anatomy"
        / "cluster_names.json"
    )
    text = sidecar.read_text(encoding="utf-8")
    payload = json.loads(text)
    # Keys are stringified cluster ids; values are Korean labels.
    assert sorted(payload.keys()) == ["0", "1", "2"]
    assert all(isinstance(v, str) and v for v in payload.values())

    # Canonical form: re-encode with the same options and require equality
    # (modulo trailing newline). This catches any drift in indent / sort.
    canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2)
    assert text.rstrip("\n") == canonical, (
        "cluster_names.json drifted from canonical form (sort_keys + ensure_ascii=False + indent=2)"
    )


def test_no_clusters_sidecar_single_label(tmp_path: Path) -> None:
    """k=1 fallback fixture lands the well-known '단일 군집 (산출 불가)' label."""
    out = tmp_path / "fixtures"
    out.mkdir()
    build_all(out)

    sidecar = (
        out
        / "silver_phase3_no_clusters"
        / "silver"
        / "needs-map"
        / "2026-1-anatomy"
        / "cluster_names.json"
    )
    payload = json.loads(sidecar.read_text(encoding="utf-8"))
    assert payload == {"0": "단일 군집 (산출 불가)"}


def test_missing_factor_scores_fixture_omits_factor_scores(tmp_path: Path) -> None:
    """US5 fail-fast trigger: factor_scores.parquet must be absent."""
    out = tmp_path / "fixtures"
    out.mkdir()
    build_all(out)

    nm_root = (
        out / "silver_phase3_missing_factor_scores" / "silver" / "needs-map" / "2026-1-anatomy"
    )
    assert (nm_root / "manifest.json").exists()
    assert (nm_root / "cluster_assignment.parquet").exists()
    assert not (nm_root / "factor_scores.parquet").exists()
