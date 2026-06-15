"""Shared Literal types for the retro-mester CQI pipeline (spec 010).

These Literals are referenced by all retro-mester schemas; centralised here
to avoid import cycles and allow paideia_shared consumers to import them
without depending on the retro-mester module itself.
"""

from __future__ import annotations

from typing import Literal

SegmentKey = Literal["학령기", "만학도"]
"""Student demographic segment used for gap analysis."""

ImportanceLevel = Literal["상", "중", "하"]
"""Curriculum unit importance level (high / medium / low)."""

EffortLevel = Literal["상", "중", "하"]
"""Instructional change effort level (high / medium / low)."""

CauseLabel = Literal[
    "기초구멍",
    "내용난이도",
    "가설-전달",
    "가설-되새김",
    "가설-속도",
    "미상",
]
"""Root-cause hypothesis label for a unit gap."""

ValidityVerdict = Literal["건전", "문항수선", "판정불가"]
"""Item/unit psychometric validity verdict."""

AlignmentFlag = Literal[
    "정렬됨",
    "과소교수-과다평가",
    "과다교수-과소평가",
    "인지수준절벽",
    "기대-실제괴리",
]
"""Teaching-assessment alignment diagnostic flag."""

PriorityQuadrant = Literal["빠른승리", "큰베팅", "낮은우선", "보류"]
"""Impact-effort priority quadrant label."""

__all__ = [
    "SegmentKey",
    "ImportanceLevel",
    "EffortLevel",
    "CauseLabel",
    "ValidityVerdict",
    "AlignmentFlag",
    "PriorityQuadrant",
]
