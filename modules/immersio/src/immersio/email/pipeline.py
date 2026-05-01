"""immersio-email orchestration pipeline (T048 — Foundational stub).

Phase 2 ships a stub so the CLI subparser (T030) parses correctly. The
real pipeline body (Phase A→B→C→D→E + dry-run / self-test / send
branches) lands in T048 (US1), T056 (US2), T072 (US3), and so on.
"""

from __future__ import annotations

import argparse
import sys


def run_email_dispatch(args: argparse.Namespace) -> int:
    """Foundational stub — emits NotImplementedError-shaped exit (T048).

    The Foundational phase only needs the CLI subparser (T030) to accept
    arguments cleanly. Calling ``immersio email`` before US1 ships will
    return exit code 2 with a clear message — no Gmail API call, no
    side-effect on disk.

    Args:
        args: argparse.Namespace from the email subparser.

    Returns:
        Process exit code. Foundational stub always returns 2.
    """
    print(
        "ERROR [immersio email]: pipeline body lands in spec 006 Phase 3 "
        "(US1 — T048). Foundational stub does not dispatch.",
        file=sys.stderr,
    )
    return 2


__all__ = ["run_email_dispatch"]
