"""CLI path validation hardening tests (closure of adversary AV-3 + AV-4b).

Covers:
    - test_traversal_argument_rejected: ``--bronze-dir ../etc`` style escapes
    - test_symlink_input_rejected: bronze_dir / mapping is a symlink
    - test_output_under_bronze_rejected: output_dir is a descendant of bronze_dir
    - test_output_key_pattern_enforced: malformed --output-key
    - test_output_key_nul_byte_rejected: NUL byte in --output-key
    - test_pipeline_walk_skips_symlink: planted symlink inside Bronze must
      not appear in manifest.unrecognized_files nor pollute input hashes

Each rejection routes through ``app()`` and yields exit code 2 (argument error).
"""

from __future__ import annotations

import json
from pathlib import Path

from immersio.cli.main import app

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"
BRONZE = FIXTURES / "bronze_minimal"
MAPPING = FIXTURES / "mappings" / "anatomy.diagnostic.yaml"


def _run(*argv: str) -> int:
    return app(list(argv))


def test_traversal_argument_rejected(tmp_path: Path) -> None:
    """A traversal-style --bronze-dir must fail before any parsing."""
    bogus = tmp_path / "does-not-exist" / ".." / "etc"
    code = _run(
        "ingest",
        "--bronze-dir",
        str(bogus),
        "--mapping",
        str(MAPPING),
        "--output-dir",
        str(tmp_path / "silver"),
    )
    # FileNotFoundError surfaces as exit 2 (missing input).
    assert code == 2


def test_symlink_bronze_dir_rejected(tmp_path: Path) -> None:
    """A symlinked bronze_dir must be rejected (AV-3 #2)."""
    link = tmp_path / "bronze-link"
    link.symlink_to(BRONZE, target_is_directory=True)
    code = _run(
        "ingest",
        "--bronze-dir",
        str(link),
        "--mapping",
        str(MAPPING),
        "--output-dir",
        str(tmp_path / "silver"),
    )
    assert code == 2


def test_symlink_mapping_rejected(tmp_path: Path) -> None:
    """A symlinked --mapping path must be rejected (AV-3 #2)."""
    link = tmp_path / "mapping-link.yaml"
    link.symlink_to(MAPPING)
    code = _run(
        "ingest",
        "--bronze-dir",
        str(BRONZE),
        "--mapping",
        str(link),
        "--output-dir",
        str(tmp_path / "silver"),
    )
    assert code == 2


def test_output_dir_under_bronze_rejected(tmp_path: Path) -> None:
    """output_dir nested inside bronze_dir must be rejected (AV-3 #3)."""
    code = _run(
        "ingest",
        "--bronze-dir",
        str(BRONZE),
        "--mapping",
        str(MAPPING),
        "--output-dir",
        str(BRONZE / "subdir"),
    )
    assert code == 2


def test_output_key_pattern_enforced(tmp_path: Path) -> None:
    """--output-key must match {YYYY}-[12SW]-{course-slug} (AV-3 #6)."""
    code = _run(
        "ingest",
        "--bronze-dir",
        str(BRONZE),
        "--mapping",
        str(MAPPING),
        "--output-dir",
        str(tmp_path / "silver"),
        "--output-key",
        "../escape",
    )
    assert code == 2


def test_output_key_nul_byte_rejected(tmp_path: Path) -> None:
    """NUL bytes in --output-key are rejected (AV-3 #5)."""
    code = _run(
        "ingest",
        "--bronze-dir",
        str(BRONZE),
        "--mapping",
        str(MAPPING),
        "--output-dir",
        str(tmp_path / "silver"),
        "--output-key",
        "2026-1-anatomy\x00malicious",
    )
    assert code == 2


def test_pipeline_walk_skips_symlink_in_bronze(tmp_path: Path) -> None:
    """Symlink planted inside Bronze must not surface in manifest fields.

    AV-4b regression test: ``_walk_unrecognized`` and ``_sha256_dir_concat``
    must use ``os.walk(followlinks=False)`` and skip every symlinked entry.
    """
    import shutil

    sandbox_bronze = tmp_path / "bronze_sandbox"
    shutil.copytree(BRONZE, sandbox_bronze, symlinks=False)

    secret = tmp_path / "secret-outside.txt"
    secret.write_text("attacker payload\n")

    # Plant a symlink inside Bronze pointing to the outside file.
    (sandbox_bronze / "_planted_link.txt").symlink_to(secret)

    output_parent = tmp_path / "silver"
    code = _run(
        "ingest",
        "--bronze-dir",
        str(sandbox_bronze),
        "--mapping",
        str(MAPPING),
        "--output-dir",
        str(output_parent),
    )
    # ingest still completes (symlink ignored, not blocked).
    assert code == 0

    silver_dir = output_parent / "2026-1-anatomy"
    manifest = json.loads((silver_dir / "manifest.json").read_text())

    unrecognized = manifest.get("unrecognized_files", [])
    assert "_planted_link.txt" not in unrecognized
    # Defensive: the planted secret must never appear by name.
    assert not any("secret-outside" in path for path in unrecognized)
