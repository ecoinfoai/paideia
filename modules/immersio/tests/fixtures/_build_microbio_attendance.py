"""Build microbiology attendance XLSX fixture (US3)."""

from __future__ import annotations

from pathlib import Path

from openpyxl import Workbook

ROSTER = [
    ("2027000001", "학생가"),
    ("2027000002", "학생나"),
    ("2027000003", "학생다"),
]


def build(target: Path) -> None:
    wb = Workbook()
    sheet = wb.active
    sheet.title = "출석"
    sheet.append(["학번", "이름"] + [f"W{week:02d}" for week in range(1, 17)] + ["비고"])
    for sid, name in ROSTER:
        sheet.append([sid, name] + ["O"] * 16 + [""])
    wb.save(target)


if __name__ == "__main__":
    out = Path(__file__).parent / "bronze_minimal_microbio" / "출석" / "출석부.xlsx"
    out.parent.mkdir(parents=True, exist_ok=True)
    build(out)
    print(f"wrote {out}")
