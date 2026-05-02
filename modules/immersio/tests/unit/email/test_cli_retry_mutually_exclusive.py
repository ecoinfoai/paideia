"""CLI --retry-failed / --retry-skipped mutex test (T077, FR-D03c)."""

from __future__ import annotations

import pytest

from immersio.cli.main import _build_parser


def test_retry_failed_and_skipped_mutually_exclusive() -> None:
    """argparse mutex group rejects both flags simultaneously."""
    parser = _build_parser()
    with pytest.raises(SystemExit) as exc_info:
        parser.parse_args(
            [
                "email",
                "--profile",
                "alpha-prof",
                "--semester",
                "2026-1",
                "--course",
                "anatomy",
                "--exam-name",
                "중간고사",
                "--send",
                "--retry-failed",
                "--retry-skipped",
            ]
        )
    # argparse exits with code 2 on mutex violation
    assert exc_info.value.code == 2


def test_retry_failed_alone_accepted() -> None:
    parser = _build_parser()
    args = parser.parse_args(
        [
            "email",
            "--profile",
            "alpha-prof",
            "--semester",
            "2026-1",
            "--course",
            "anatomy",
            "--exam-name",
            "중간고사",
            "--send",
            "--retry-failed",
        ]
    )
    assert args.retry_failed is True
    assert args.retry_skipped is False


def test_retry_skipped_alone_accepted() -> None:
    parser = _build_parser()
    args = parser.parse_args(
        [
            "email",
            "--profile",
            "alpha-prof",
            "--semester",
            "2026-1",
            "--course",
            "anatomy",
            "--exam-name",
            "중간고사",
            "--send",
            "--retry-skipped",
        ]
    )
    assert args.retry_skipped is True
    assert args.retry_failed is False


def test_neither_retry_flag_default() -> None:
    parser = _build_parser()
    args = parser.parse_args(
        [
            "email",
            "--profile",
            "alpha-prof",
            "--semester",
            "2026-1",
            "--course",
            "anatomy",
            "--exam-name",
            "중간고사",
        ]
    )
    assert args.retry_failed is False
    assert args.retry_skipped is False
