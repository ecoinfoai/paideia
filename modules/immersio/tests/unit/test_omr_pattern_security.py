"""Security regression tests for the OMR pattern flags (adversary 9건 mitigation).

Spec 004 T015-T018 land 후 adversary 가 식별한 공격 표면:

- A1 ``..`` 평탄화 escape — Path.glob 이 세그먼트를 평탄화하지 않음
- A2 symlink dir follow — bronze_dir 내부 symlink 디렉터리가 외부로 escape
- A3 NUL/control bytes — friendly diagnostic 부재
- A4 macOS NFD 한글 — DEFAULT_RESULT_EXCLUDE_TOKENS 가 NFC 만이라 미스
- A6 absolute path / A8 oversized — Path.glob 자체에서 fail 하나 friendly 변환

본 모듈은 mitigation 후 GREEN.
"""

from __future__ import annotations

import os
import unicodedata
from pathlib import Path

import pytest

# Pre-populate ``immersio.ingest`` to break ``io ↔ ingest`` circular import
# during standalone test collection. See test_attendance_roster_only.py.
import immersio.ingest  # noqa: F401  # required-for: io ↔ ingest import order

from immersio.cli.main import _validate_glob_pattern  # noqa: E402
from immersio.io.exam_omr import discover_section_files  # noqa: E402


# =====================================================================
# CLI _validate_glob_pattern — A1 / A3 / A6 / A8 mitigation
# =====================================================================


class TestValidateGlobPattern:
    """``_validate_glob_pattern(label, value)`` is the CLI gatekeeper.

    Returns silently for ``value is None``. For any rejection it raises
    ``ValueError`` carrying ``label`` so the operator sees which flag is wrong.
    """

    def test_none_passes(self) -> None:
        _validate_glob_pattern("--exam-result-pattern", None)

    def test_valid_pattern_passes(self) -> None:
        _validate_glob_pattern("--exam-result-pattern", "*A반*결과.xls")

    def test_empty_string_rejected(self) -> None:
        with pytest.raises(ValueError, match=r"--exam-result-pattern.*empty"):
            _validate_glob_pattern("--exam-result-pattern", "")

    def test_nul_byte_rejected(self) -> None:
        with pytest.raises(ValueError, match=r"--exam-result-pattern.*NUL"):
            _validate_glob_pattern("--exam-result-pattern", "*A반\x00*.xls")

    def test_control_byte_rejected(self) -> None:
        with pytest.raises(ValueError, match=r"--exam-result-pattern.*control"):
            _validate_glob_pattern("--exam-result-pattern", "*A반\x07*.xls")

    def test_dotdot_segment_rejected(self) -> None:
        """A1: ``..`` 세그먼트 escape 차단."""
        with pytest.raises(ValueError, match=r"--exam-result-pattern.*parent"):
            _validate_glob_pattern("--exam-result-pattern", "../outside/*.xls")

    def test_dotdot_in_middle_rejected(self) -> None:
        with pytest.raises(ValueError, match=r"--exam-result-pattern.*parent"):
            _validate_glob_pattern("--exam-result-pattern", "inner/../escape/*.xls")

    def test_absolute_path_rejected(self) -> None:
        """A6: 절대경로는 친절한 진단으로 거부."""
        with pytest.raises(ValueError, match=r"--exam-result-pattern.*absolute"):
            _validate_glob_pattern("--exam-result-pattern", "/etc/*.xls")

    def test_oversized_pattern_rejected(self) -> None:
        """A8: 1024자 초과는 hygiene 거부."""
        long = "x" * 1100
        with pytest.raises(ValueError, match=r"--exam-result-pattern.*length"):
            _validate_glob_pattern("--exam-result-pattern", long)


# =====================================================================
# discover_section_files — A2 symlink escape mitigation
# =====================================================================


def test_discover_blocks_symlinked_subdir_to_outside(tmp_path: Path) -> None:
    """A2: bronze 내부 symlink 디렉터리가 외부로 escape 시 차단.

    Setup: ``inner/escaped`` 가 ``outside/`` 로 가는 symlink. 외부에 위조
    OMR 파일을 두고 패턴이 매칭하더라도 ``discover_section_files`` 가
    ValueError 로 거부해야 한다 (``base.resolve(strict=True)`` + ``is_relative_to``).
    """
    inner = tmp_path / "inner"
    outside = tmp_path / "outside"
    inner.mkdir()
    outside.mkdir()
    forged = outside / "인체구조_A반_결과.xls"
    forged.write_bytes(b"")
    escaped = inner / "escaped"
    try:
        os.symlink(outside, escaped, target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip("symlink not supported on this platform")
    with pytest.raises(ValueError, match=r"escape|relative"):
        discover_section_files(
            inner,
            section="A",
            result_pattern_override="escaped/*A반*결과.xls",
            exclude_tokens=frozenset(),
        )


# =====================================================================
# discover_section_files — A4 macOS NFD normalization
# =====================================================================


def test_discover_excludes_nfd_filename_tokens(tmp_path: Path) -> None:
    """A4: macOS 의 NFD 분해 한글이 default exclude 토큰과 매칭된다.

    ``'(문항분석)'`` 의 NFD 분해 형식 파일명은 NFC 비교에서 미스되어
    실수로 결과 후보로 잡힌다. mitigation: 매칭 직전 ``unicodedata.normalize('NFC', name)``.
    """
    nfc = "인체구조_A반_결과(문항분석).xls"
    nfd = unicodedata.normalize("NFD", nfc)
    target = tmp_path / nfd
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(b"")
    matches = discover_section_files(tmp_path, section="A")
    # NFD 분해 파일명도 default 룰에서 exclude 되어야 한다 (결과 후보 0개).
    assert matches == [], f"NFD '(문항분석)' must be excluded, got {matches}"
