"""T015 — Unit tests for metric_codex.output.paths.

Tests (RED first, per TDD mandate):
- bronze_dir, silver_dir, gold_dir: return expected path shapes under the
  default data root and under an overridden data_root.
- run_gold_dir: returns a run-isolated subpath under gold_dir.
- atomic_write is NOT in paths.py (it lives in determinism.py); importing from
  paths must NOT provide atomic_write.
"""

from __future__ import annotations

from pathlib import Path

# ---------------------------------------------------------------------------
# bronze_dir
# ---------------------------------------------------------------------------


def test_bronze_dir_default_root() -> None:
    """bronze_dir default data root → data/bronze/metric-codex/{semester}-{slug}/."""
    from metric_codex.output.paths import bronze_dir

    result = bronze_dir("2026-1", "anatomy")
    assert result == Path("data") / "bronze" / "metric-codex" / "2026-1-anatomy"


def test_bronze_dir_custom_root(tmp_path: Path) -> None:
    """bronze_dir honours data_root override."""
    from metric_codex.output.paths import bronze_dir

    result = bronze_dir("2026-1", "anatomy", data_root=tmp_path)
    assert result == tmp_path / "bronze" / "metric-codex" / "2026-1-anatomy"


def test_bronze_dir_slug_with_hyphen() -> None:
    """bronze_dir handles slugs that already contain hyphens."""
    from metric_codex.output.paths import bronze_dir

    result = bronze_dir("2026-1", "human-body", data_root=Path("/data"))
    assert result == Path("/data/bronze/metric-codex/2026-1-human-body")


# ---------------------------------------------------------------------------
# silver_dir
# ---------------------------------------------------------------------------


def test_silver_dir_default_root() -> None:
    """silver_dir default data root → data/silver/metric-codex/{semester}-{slug}/."""
    from metric_codex.output.paths import silver_dir

    result = silver_dir("2026-1", "anatomy")
    assert result == Path("data") / "silver" / "metric-codex" / "2026-1-anatomy"


def test_silver_dir_custom_root(tmp_path: Path) -> None:
    """silver_dir honours data_root override."""
    from metric_codex.output.paths import silver_dir

    result = silver_dir("2026-2", "physiology", data_root=tmp_path)
    assert result == tmp_path / "silver" / "metric-codex" / "2026-2-physiology"


# ---------------------------------------------------------------------------
# gold_dir
# ---------------------------------------------------------------------------


def test_gold_dir_default_root() -> None:
    """gold_dir default data root → data/gold/metric-codex/{semester}-{slug}/."""
    from metric_codex.output.paths import gold_dir

    result = gold_dir("2026-1", "anatomy")
    assert result == Path("data") / "gold" / "metric-codex" / "2026-1-anatomy"


def test_gold_dir_custom_root(tmp_path: Path) -> None:
    """gold_dir honours data_root override."""
    from metric_codex.output.paths import gold_dir

    result = gold_dir("2026-1", "nursing", data_root=tmp_path)
    assert result == tmp_path / "gold" / "metric-codex" / "2026-1-nursing"


# ---------------------------------------------------------------------------
# run_gold_dir
# ---------------------------------------------------------------------------


def test_run_gold_dir_default_root() -> None:
    """run_gold_dir appends runs/{run_id} under gold_dir."""
    from metric_codex.output.paths import run_gold_dir

    result = run_gold_dir("2026-1", "anatomy", run_id="ab12cd34")
    expected = Path("data") / "gold" / "metric-codex" / "2026-1-anatomy" / "runs" / "ab12cd34"
    assert result == expected


def test_run_gold_dir_custom_root(tmp_path: Path) -> None:
    """run_gold_dir honours data_root override."""
    from metric_codex.output.paths import run_gold_dir

    result = run_gold_dir("2026-1", "anatomy", run_id="xyz", data_root=tmp_path)
    expected = tmp_path / "gold" / "metric-codex" / "2026-1-anatomy" / "runs" / "xyz"
    assert result == expected


def test_run_gold_dir_same_run_id_idempotent() -> None:
    """Two calls with the same run_id return the same path (idempotent)."""
    from metric_codex.output.paths import run_gold_dir

    a = run_gold_dir("2026-1", "anatomy", run_id="abc123")
    b = run_gold_dir("2026-1", "anatomy", run_id="abc123")
    assert a == b


def test_run_gold_dir_different_run_ids_different_paths() -> None:
    """Different run_ids yield different paths (re-run isolation)."""
    from metric_codex.output.paths import run_gold_dir

    a = run_gold_dir("2026-1", "anatomy", run_id="run1")
    b = run_gold_dir("2026-1", "anatomy", run_id="run2")
    assert a != b


# ---------------------------------------------------------------------------
# atomic_write must NOT be exported from paths (it lives in determinism.py)
# ---------------------------------------------------------------------------


def test_atomic_write_not_in_paths() -> None:
    """paths.py must not export atomic_write (belongs in determinism.py)."""
    import metric_codex.output.paths as paths_module

    assert not hasattr(paths_module, "atomic_write"), (
        "atomic_write should not be in paths.py — it belongs in determinism.py"
    )
