"""T055 — Unit tests for ``_run_build`` orchestration (first-non-zero stop).

Monkeypatches the four ``_run_*`` stage functions to controllable returns so the
first-non-zero-stop contract is proved for BOTH paths without the heavy pipeline
fixture:

- all-zero → ``_run_build`` returns 0 (all four stages called, in order);
- a middle stage returning 3 (verify-style) → ``_run_build`` returns 3 AND the
  later stage(s) are NOT called;
- a stage raising ``LocatedInputError`` → propagates out of ``_run_build``.
"""

from __future__ import annotations

import argparse

import pytest
from metric_codex.cli import main as cli_main
from metric_codex.errors import LocatedInputError


def _dummy_args() -> argparse.Namespace:
    """Return a minimal Namespace; the patched stages ignore its contents."""
    return argparse.Namespace(semester="2026-1", course="anatomy")


def _patch_stages(
    monkeypatch: pytest.MonkeyPatch,
    returns: dict[str, int],
    call_order: list[str],
    raises: dict[str, Exception] | None = None,
) -> None:
    """Replace the four ``_run_*`` stage functions with recording fakes.

    Args:
        monkeypatch: pytest monkeypatch fixture.
        returns: Map of stage name → exit code the fake returns.
        call_order: List appended to (in call order) by each fake.
        raises: Optional map of stage name → exception to raise instead of return.
    """
    raises = raises or {}

    def _make(name: str):
        def _fake(_args: argparse.Namespace) -> int:
            call_order.append(name)
            if name in raises:
                raise raises[name]
            return returns[name]

        return _fake

    monkeypatch.setattr(cli_main, "_run_ingest", _make("ingest"))
    monkeypatch.setattr(cli_main, "_run_generate", _make("generate"))
    monkeypatch.setattr(cli_main, "_run_distribute", _make("distribute"))
    monkeypatch.setattr(cli_main, "_run_verify", _make("verify"))


# ---------------------------------------------------------------------------
# (a) all-zero → 0, all four stages run in order
# ---------------------------------------------------------------------------


class TestBuildAllZero:
    def test_returns_zero(self, monkeypatch: pytest.MonkeyPatch) -> None:
        order: list[str] = []
        _patch_stages(
            monkeypatch,
            returns={"ingest": 0, "generate": 0, "distribute": 0, "verify": 0},
            call_order=order,
        )
        rc = cli_main._run_build(_dummy_args())
        assert rc == 0

    def test_all_four_stages_called_in_order(self, monkeypatch: pytest.MonkeyPatch) -> None:
        order: list[str] = []
        _patch_stages(
            monkeypatch,
            returns={"ingest": 0, "generate": 0, "distribute": 0, "verify": 0},
            call_order=order,
        )
        cli_main._run_build(_dummy_args())
        assert order == ["ingest", "generate", "distribute", "verify"]


# ---------------------------------------------------------------------------
# (b) verify-style middle/last stage returning 3 → stop, later stages NOT called
# ---------------------------------------------------------------------------


class TestBuildReturnNonZeroStop:
    """The return-non-zero path: a stage returning 3 halts the loop."""

    def test_verify_return_3_propagates(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """verify (last stage) returns 3 → _run_build returns 3."""
        order: list[str] = []
        _patch_stages(
            monkeypatch,
            returns={"ingest": 0, "generate": 0, "distribute": 0, "verify": 3},
            call_order=order,
        )
        rc = cli_main._run_build(_dummy_args())
        assert rc == 3, f"verify→3 must propagate as _run_build's return; got {rc}"

    def test_verify_return_3_runs_all_four(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """verify is last, so all four stages still run before the 3 is returned."""
        order: list[str] = []
        _patch_stages(
            monkeypatch,
            returns={"ingest": 0, "generate": 0, "distribute": 0, "verify": 3},
            call_order=order,
        )
        cli_main._run_build(_dummy_args())
        assert order == ["ingest", "generate", "distribute", "verify"]

    def test_middle_stage_return_3_stops_later_stages(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A MIDDLE stage (generate) returning 3 must NOT call distribute/verify."""
        order: list[str] = []
        _patch_stages(
            monkeypatch,
            returns={"ingest": 0, "generate": 3, "distribute": 0, "verify": 0},
            call_order=order,
        )
        rc = cli_main._run_build(_dummy_args())
        assert rc == 3
        assert order == ["ingest", "generate"], (
            "distribute/verify must NOT run after generate returned non-zero"
        )
        assert "distribute" not in order
        assert "verify" not in order


# ---------------------------------------------------------------------------
# (c) a stage raising LocatedInputError propagates (raise path)
# ---------------------------------------------------------------------------


class TestBuildRaisePropagates:
    """The raise path: a stage raising LocatedInputError propagates + stops."""

    def test_ingest_raise_propagates(self, monkeypatch: pytest.MonkeyPatch) -> None:
        order: list[str] = []
        _patch_stages(
            monkeypatch,
            returns={"ingest": 0, "generate": 0, "distribute": 0, "verify": 0},
            call_order=order,
            raises={"ingest": LocatedInputError("bad input", actual="x")},
        )
        with pytest.raises(LocatedInputError):
            cli_main._run_build(_dummy_args())

    def test_ingest_raise_stops_later_stages(self, monkeypatch: pytest.MonkeyPatch) -> None:
        order: list[str] = []
        _patch_stages(
            monkeypatch,
            returns={"ingest": 0, "generate": 0, "distribute": 0, "verify": 0},
            call_order=order,
            raises={"ingest": LocatedInputError("bad input", actual="x")},
        )
        with pytest.raises(LocatedInputError):
            cli_main._run_build(_dummy_args())
        assert order == ["ingest"], "no stage may run after ingest raised"
