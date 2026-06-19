"""T024 — US1 provenance (FR-004 / FR-008 / FR-020 / SC-006).

Every CodexEntry's ``source_id`` resolves to a ``source_ledger`` row; every
ledger row carries an ``ingested_at`` timestamp; and every ``value_text`` entry
traces back to a needs-map free-text source.  Time order is reconstructable from
the ledger.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
from metric_codex.cli.main import app
from metric_codex.output.paths import silver_dir

from tests.fixtures.scenario_a import COURSE, SEMESTER, build_scenario_a

_NOW = "2026-06-19T00:00:00Z"


def _ingest(data_root: Path) -> int:
    return app(
        [
            "ingest",
            "--semester",
            SEMESTER,
            "--course",
            COURSE,
            "--data-root",
            str(data_root),
            "--now",
            _NOW,
        ]
    )


def _load(data_root: Path) -> tuple[pd.DataFrame, pd.DataFrame]:
    sd = silver_dir(SEMESTER, COURSE, data_root=data_root)
    entries = pd.read_parquet(sd / "codex_entry.parquet")
    ledger = pd.read_parquet(sd / "source_ledger.parquet")
    return entries, ledger


def test_every_entry_source_resolves(tmp_path: Path) -> None:
    """Every entry.source_id is present in the source_ledger (referential integrity)."""
    data_root = build_scenario_a(tmp_path)
    assert _ingest(data_root) == 0

    entries, ledger = _load(data_root)
    ledger_ids = set(ledger["source_id"])
    assert set(entries["source_id"]).issubset(ledger_ids)


def test_ledger_rows_carry_ingested_at(tmp_path: Path) -> None:
    """Every ledger row carries a non-empty ingested_at (time order reconstructable)."""
    data_root = build_scenario_a(tmp_path)
    assert _ingest(data_root) == 0

    _entries, ledger = _load(data_root)
    assert ledger["ingested_at"].notna().all()
    assert (ledger["ingested_at"] == _NOW).all()


def test_value_text_traces_to_needsmap_freetext(tmp_path: Path) -> None:
    """Every value_text entry's source is a needs-map free-text source (FR-008/FR-020)."""
    data_root = build_scenario_a(tmp_path)
    assert _ingest(data_root) == 0

    entries, ledger = _load(data_root)
    by_source = dict(zip(ledger["source_id"], ledger["origin_module"], strict=True))

    text_entries = entries[entries["value_text"].notna()]
    assert not text_entries.empty
    for source_id in text_entries["source_id"].unique():
        assert by_source[source_id] == "needs-map"
        assert "free_text" in source_id
