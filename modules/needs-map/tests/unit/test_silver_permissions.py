"""Owner-only permission tests for the silver parquet writer (DAR-02).

``_write_silver_atomic`` is the single sink for all student-PII silver
parquet (factor_scores, scale_reliability, cluster_assignment,
free_text_categorization). The artifact must land mode 0o600 regardless
of umask.
"""

from __future__ import annotations

import os
from pathlib import Path

import pandas as pd
import pytest
from needs_map.pipeline import _write_silver_atomic


@pytest.mark.skipif(os.geteuid() == 0, reason="root bypasses chmod 0o600 protection")
@pytest.mark.parametrize(
    "name",
    [
        "factor_scores.parquet",
        "scale_reliability.parquet",
        "cluster_assignment.parquet",
        "free_text_categorization.parquet",
    ],
)
def test_write_silver_atomic_is_owner_only(tmp_path: Path, name: str) -> None:
    df = pd.DataFrame({"student_id": ["2026194001"], "value": [1.0]})
    _write_silver_atomic(tmp_path, name, df)
    target = tmp_path / name
    mode = target.stat().st_mode & 0o777
    assert mode & 0o077 == 0, f"expected owner-only, got {oct(mode)}"
    assert mode == 0o600, oct(mode)
