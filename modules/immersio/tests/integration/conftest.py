"""Integration test helpers — corrupt-bronze fixture builder."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

GOOD_BRONZE = Path(__file__).resolve().parents[1] / "fixtures" / "bronze_minimal"
GOOD_MAPPING = (
    Path(__file__).resolve().parents[1] / "fixtures" / "mappings" / "anatomy.diagnostic.yaml"
)


@pytest.fixture
def corrupt_bronze(tmp_path: Path) -> Path:
    """Materialize a fresh writable copy of the bronze_minimal fixture."""
    target = tmp_path / "bronze_corrupt"
    shutil.copytree(GOOD_BRONZE, target)
    return target


@pytest.fixture
def corrupt_mapping(tmp_path: Path) -> Path:
    """Materialize a fresh writable copy of the canonical mapping YAML."""
    target = tmp_path / "anatomy.diagnostic.yaml"
    shutil.copy2(GOOD_MAPPING, target)
    return target
