"""Build the synthetic attendance XLSX fixture for bronze_minimal."""

from __future__ import annotations

from pathlib import Path

from openpyxl import Workbook

ROSTER: list[tuple[str, str]] = [
    ("2026000001", "학생A"),
    ("2026000002", "학생B"),
    ("2026000003", "학생C"),
    ("2026000004", "학생D"),
    ("2026000005", "학생E"),
]

# 16 weeks (W01..W16) per student. O=present, X=absent, L=late, E=excused, ""=blank.
ATTENDANCE: dict[str, list[str]] = {
    "2026000001": ["O"] * 14 + ["L", "O"],
    "2026000002": ["O"] * 12 + ["X", "O", "O", "O"],
    "2026000003": ["O"] * 10 + ["L", "L", "X", "O", "O", "E"],
    "2026000004": ["O"] * 16,
    "2026000005": ["O"] * 8 + ["X", "X", "O", "O", "O", "O", "O", "O"],
}

NOTE: dict[str, str] = {"2026000003": "감기로 인한 공결 1회"}


def build(target: Path) -> None:
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "출석"
    header = ["학번", "이름"] + [f"W{week:02d}" for week in range(1, 17)] + ["비고"]
    sheet.append(header)
    for student_id, name in ROSTER:
        weeks = ATTENDANCE[student_id]
        row = [student_id, name] + weeks + [NOTE.get(student_id, "")]
        sheet.append(row)
    workbook.save(target)


if __name__ == "__main__":
    out = Path(__file__).parent / "bronze_minimal" / "출석" / "출석부.xlsx"
    out.parent.mkdir(parents=True, exist_ok=True)
    build(out)
    print(f"wrote {out}")
