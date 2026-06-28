"""Unit tests for the owner-only atomic writer (DAR-01/DAR-02 centralization)."""

from __future__ import annotations

import hashlib
import os
from pathlib import Path

import pytest
from paideia_shared.io import atomic_write

# Permission assertions are meaningless under root (chmod bits bypassed).
_skip_if_root = pytest.mark.skipif(
    os.geteuid() == 0,
    reason="root bypasses chmod owner-only protection",
)


@_skip_if_root
def test_owner_only_and_content(tmp_path: Path) -> None:
    """P1: result is owner-only (no group/other bits) with correct content."""
    p = tmp_path / "secret.txt"
    atomic_write(p, lambda tp: tp.write_text("x"))
    assert p.read_text() == "x"
    assert p.stat().st_mode & 0o077 == 0


def test_atomicity_on_failure_no_leftover(tmp_path: Path) -> None:
    """P2: write_fn raising propagates; path absent; no temp leftover."""
    p = tmp_path / "out.txt"

    def boom(tp: Path) -> None:
        tp.write_text("partial")
        raise ValueError("write failed")

    with pytest.raises(ValueError, match="write failed"):
        atomic_write(p, boom)

    assert not p.exists()
    assert list(tmp_path.glob(".tmp_*")) == []


def test_atomicity_preserves_existing_on_failure(tmp_path: Path) -> None:
    """P2: a pre-existing path is left unchanged when write_fn raises."""
    p = tmp_path / "out.txt"
    p.write_text("original")

    def boom(tp: Path) -> None:
        tp.write_text("new")
        raise RuntimeError("nope")

    with pytest.raises(RuntimeError, match="nope"):
        atomic_write(p, boom)

    assert p.read_text() == "original"
    assert list(tmp_path.glob(".tmp_*")) == []


@_skip_if_root
def test_umask_independence(tmp_path: Path) -> None:
    """P3: a loose umask does not loosen the final file permissions."""
    p = tmp_path / "u.txt"
    old_umask = os.umask(0o022)
    try:
        atomic_write(p, lambda tp: tp.write_text("y"))
    finally:
        os.umask(old_umask)
    assert p.stat().st_mode & 0o077 == 0


def test_determinism_identical_bytes(tmp_path: Path) -> None:
    """P4: same write_fn bytes yield identical content (sha256 equal)."""
    p1 = tmp_path / "a.txt"
    p2 = tmp_path / "b.txt"
    payload = "deterministic-payload\n"
    atomic_write(p1, lambda tp: tp.write_text(payload))
    atomic_write(p2, lambda tp: tp.write_text(payload))
    h1 = hashlib.sha256(p1.read_bytes()).hexdigest()
    h2 = hashlib.sha256(p2.read_bytes()).hexdigest()
    assert h1 == h2


@_skip_if_root
def test_write_fn_recreates_with_loose_perms_still_owner_only(
    tmp_path: Path,
) -> None:
    """Hardening: write_fn that unlink+recreates with 0o644 still ends 0o600."""
    p = tmp_path / "recreate.txt"

    def recreate(tp: Path) -> None:
        tp.unlink()
        tp.write_text("y")
        os.chmod(tp, 0o644)

    atomic_write(p, recreate)
    assert p.read_text() == "y"
    assert p.stat().st_mode & 0o077 == 0
