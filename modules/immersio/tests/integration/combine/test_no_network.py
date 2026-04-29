"""Static + dynamic verification: combine/ has no network/LLM calls (T063, SC-002).

Static: grep combine/ for forbidden imports (anthropic / openai / requests /
urllib / httpx). Dynamic: run the pipeline with socket disabled and confirm
no network attempts surface.
"""

from __future__ import annotations

import importlib.util
import re
from pathlib import Path
from types import ModuleType

import pytest

_COMBINE_ROOT = (
    Path(__file__).resolve().parents[3]
    / "src"
    / "immersio"
    / "combine"
)

_FORBIDDEN_IMPORT_PATTERNS = (
    re.compile(r"^\s*import\s+anthropic\b", re.MULTILINE),
    re.compile(r"^\s*from\s+anthropic\b", re.MULTILINE),
    re.compile(r"^\s*import\s+openai\b", re.MULTILINE),
    re.compile(r"^\s*from\s+openai\b", re.MULTILINE),
    re.compile(r"^\s*import\s+requests\b", re.MULTILINE),
    re.compile(r"^\s*from\s+requests\b", re.MULTILINE),
    re.compile(r"^\s*import\s+urllib\b", re.MULTILINE),
    re.compile(r"^\s*from\s+urllib\b", re.MULTILINE),
    re.compile(r"^\s*import\s+httpx\b", re.MULTILINE),
    re.compile(r"^\s*from\s+httpx\b", re.MULTILINE),
    re.compile(r"^\s*import\s+http\.client\b", re.MULTILINE),
    re.compile(r"^\s*import\s+socket\b", re.MULTILINE),
)


def _python_files_in_combine() -> list[Path]:
    return [p for p in _COMBINE_ROOT.rglob("*.py") if p.is_file()]


def test_no_network_imports_in_combine_static() -> None:
    """SC-002 static gate: combine/ 전체에 network/LLM import 0건."""
    offenders: list[tuple[Path, str]] = []
    for path in _python_files_in_combine():
        text = path.read_text(encoding="utf-8")
        for pat in _FORBIDDEN_IMPORT_PATTERNS:
            for match in pat.finditer(text):
                line = text[: match.start()].count("\n") + 1
                offenders.append((path.relative_to(_COMBINE_ROOT), match.group()))
    assert not offenders, (
        f"network/LLM imports found in combine/: {offenders}"
    )


def test_no_network_clock_random_in_combine_static() -> None:
    """결정성 보강: combine/ 에 datetime.now / time.time / random.random 0건.

    Phase 1+2 결정성 정책 inherit (PNG/PDF/xlsx 의 timestamp 는 SOURCE_DATE_EPOCH
    + dcterms 후처리 + PNG_METADATA 로 fix; combine/ 는 raw clock 호출 0).
    """
    forbidden = (
        re.compile(r"datetime\.now\(", re.MULTILINE),
        re.compile(r"time\.time\(", re.MULTILINE),
        re.compile(r"random\.random\(", re.MULTILINE),
        re.compile(r"random\.randint\(", re.MULTILINE),
    )
    offenders: list[tuple[Path, str]] = []
    for path in _python_files_in_combine():
        text = path.read_text(encoding="utf-8")
        for pat in forbidden:
            for match in pat.finditer(text):
                offenders.append(
                    (path.relative_to(_COMBINE_ROOT), match.group())
                )
    assert not offenders, (
        f"non-deterministic clock/random calls in combine/: {offenders}"
    )


def _load_builder() -> ModuleType:
    here = Path(__file__).resolve()
    builder_path = here.parents[2] / "fixtures" / "build_silver_phase3.py"
    spec = importlib.util.spec_from_file_location(
        "build_silver_phase3", builder_path
    )
    if spec is None or spec.loader is None:
        raise RuntimeError(f"could not load builder from {builder_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_pipeline_runs_with_socket_disabled(
    tmp_path_factory: pytest.TempPathFactory, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Dynamic gate: run the pipeline with socket.socket() rejected — no
    silent network call surface (SC-002)."""
    import socket

    original_socket = socket.socket

    def _no_network(*args, **kwargs):
        raise OSError("Network access denied during SC-002 dynamic gate")

    monkeypatch.setattr(socket, "socket", _no_network)

    from immersio.combine.pipeline import run_us1_pipeline

    builder = _load_builder()
    tmp = tmp_path_factory.mktemp("no_network")
    builder.build_silver_phase3_minimal(tmp)
    rc = run_us1_pipeline(
        semester="2026-1",
        course_slug="anatomy",
        silver_dir=tmp / "silver",
        gold_dir=tmp / "gold",
    )
    assert rc == 0
    # Restore for any later tests.
    socket.socket = original_socket
