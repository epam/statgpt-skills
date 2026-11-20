#!/usr/bin/env python3
"""Build the Grade C Dataset Discovery Index workbook from datasets.jsonl.

Usage:
    python build_workbook.py datasets.jsonl --out index.xlsx
    python build_workbook.py datasets.jsonl --out index.xlsx --template ../assets/template.xlsx
    python build_workbook.py datasets.jsonl --out index.xlsx --sort dataset_id

The workbook has:
  Instructions   the field specification, from the template
  Datasets       one row per dataset, columns A-I, column D = Dataset ID
  <dataset id>   one indicators sheet per dataset, named with that dataset's ID,
                 two columns: Indicator | Units of measure

The indicators sheet is named with the dataset's own ID, so a row and its sheet cannot drift
apart. Excel cannot spell every id, though - it allows at most 31 characters and none of
: \ / ? * [ ] - so the name is derived once, here, by _gradec.sheet_name_map(), and the
derived form is what goes into column D. Ids that had to be reshaped are printed at the end.

Validation from validate_records.py runs first and blocks the write on any error.
Use --skip-validation only to inspect a broken run, never to deliver one.
"""

from __future__ import annotations

import argparse
import json
import os
import sys

from copy import copy

from openpyxl.styles import Alignment, Border, Font, PatternFill, Side

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _gradec import (  # noqa: E402
    DATASET_COLUMNS,
    DATASET_HEADERS,
    INDICATOR_HEADERS,
    indicator_rows,
    sheet_name_map,
)

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_TEMPLATE = os.path.join(HERE, "..", "assets", "template.xlsx")

# The template's look, used only when the template does not show it itself. The reference
# template ships a formatted Datasets row 2 and an example indicators sheet ('TABEL1_1'), and
# their cell styles are what the delivered workbook copies - see TemplateStyle.
_THIN = Side(style="thin")
HEADER_FONT = Font(name="Arial", size=10, bold=True, color="FFFFFFFF")
HEADER_FILL = PatternFill("solid", fgColor="FF2E5C8A")
HEADER_ALIGN = Alignment(wrap_text=True, vertical="center")
BODY_FONT = Font(name="Arial", size=10)
BODY_ALIGN = Alignment(wrap_text=True, vertical="top")
BORDER = Border(left=_THIN, right=_THIN, top=_THIN, bottom=_THIN)
INDICATOR_WIDTHS = {"A": 62.0, "B": 20.0}


class CellStyle:
    """One cell's look, detached from the sheet it was read from."""

    def __init__(self, font, fill, alignment, border, number_format="General"):
        self.font, self.fill, self.alignment = font, fill, alignment
        self.border, self.number_format = border, number_format

    @classmethod
    def of(cls, cell) -> "CellStyle":
        return cls(copy(cell.font), copy(cell.fill), copy(cell.alignment), copy(cell.border),
                   cell.number_format)

    def apply(self, cell) -> None:
        cell.font, cell.fill, cell.alignment = copy(self.font), copy(self.fill), copy(self.alignment)
        cell.border, cell.number_format = copy(self.border), self.number_format


class TemplateStyle:
    """The formatting the template shows, read before its example content is removed.

    Datasets body cells come from the template's row 2 (Arial 10, wrapped, top-aligned, thin
    border, text number format '@' in the reference template), one style per column A-I.
    Indicators sheets copy the template's example indicators sheet: header and body styles,
    column widths. A template without those parts falls back to the constants above.
    """

    def __init__(self, wb):
        ws = wb["Datasets"]
        n = len(DATASET_COLUMNS)
        row2 = [ws.cell(row=2, column=c) for c in range(1, n + 1)]
        if any(c.has_style and c.border.bottom.style for c in row2):
            self.dataset_body = [CellStyle.of(c) for c in row2]
        else:
            self.dataset_body = [CellStyle(BODY_FONT, PatternFill(), BODY_ALIGN, BORDER, "@")] * n

        example = next((wb[s] for s in wb.sheetnames if s not in ("Instructions", "Datasets")), None)
        k = len(INDICATOR_HEADERS)
        if example is not None and [example.cell(row=1, column=c).value for c in range(1, k + 1)] == INDICATOR_HEADERS:
            self.ind_header = [CellStyle.of(example.cell(row=1, column=c)) for c in range(1, k + 1)]
            self.ind_body = [CellStyle.of(example.cell(row=2, column=c)) for c in range(1, k + 1)]
            self.ind_widths = {
                letter: example.column_dimensions[letter].width or width
                for letter, width in INDICATOR_WIDTHS.items()
            }
        else:
            self.ind_header = [CellStyle(HEADER_FONT, HEADER_FILL, HEADER_ALIGN, BORDER)] * k
            self.ind_body = [CellStyle(BODY_FONT, PatternFill(), BODY_ALIGN, BORDER)] * k
            self.ind_widths = dict(INDICATOR_WIDTHS)


def load_records(path: str) -> list[dict]:
    records = []
    with open(path, "r", encoding="utf-8") as fh:
        for lineno, line in enumerate(fh, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError as exc:
                raise SystemExit(f"{path}:{lineno}: invalid JSON: {exc}")
    if not records:
        raise SystemExit(f"{path}: no records")
    return records


def cell_text(rec: dict, field: str) -> str:
    value = rec.get(field, "")
    if value is None:
        return ""
    return str(value).strip()


def run_validation(jsonl: str, strict: bool) -> int:
    import validate_records  # noqa: PLC0415

    argv = sys.argv
    sys.argv = ["validate_records.py", jsonl] + (["--strict"] if strict else [])
    try:
        return validate_records.main()
    finally:
        sys.argv = argv


def write_indicator_sheet(wb, name: str, rows: list[dict], style: TemplateStyle) -> None:
    if name in wb.sheetnames:
        del wb[name]
    ws = wb.create_sheet(title=name)
    for col, header in enumerate(INDICATOR_HEADERS, start=1):
        style.ind_header[col - 1].apply(ws.cell(row=1, column=col, value=header))
    for offset, row in enumerate(rows):
        for col, key in enumerate(("indicator", "unit"), start=1):
            style.ind_body[col - 1].apply(ws.cell(row=2 + offset, column=col, value=row.get(key, "")))
    for letter, width in style.ind_widths.items():
        ws.column_dimensions[letter].width = width
    ws.freeze_panes = "A2"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("jsonl")
    ap.add_argument("--out", required=True, help="output .xlsx path")
    ap.add_argument("--template", default=DEFAULT_TEMPLATE, help="template workbook (Instructions, Datasets header, optional example row and indicators sheet)")
    ap.add_argument("--sort", choices=["none", "dataset_id", "dataset_name"], default="none",
                    help="row order; default keeps the JSONL order, which is the portal's own order")
    ap.add_argument("--row-height", type=float, default=409.6,
                    help="Datasets row height in points, matching the template (0 = leave unset)")
    ap.add_argument("--skip-validation", action="store_true", help="write even if validation fails (diagnostics only)")
    ap.add_argument("--strict", action="store_true", help="treat validation warnings as failures")
    args = ap.parse_args()

    if not args.skip_validation:
        print("Validating records ...")
        if run_validation(args.jsonl, args.strict) != 0:
            print("\nValidation failed - workbook not written. Fix the records, or pass --skip-validation "
                  "to inspect a broken run.", file=sys.stderr)
            return 1
        print("Validation passed.\n")

    records = load_records(args.jsonl)
    if args.sort != "none":
        records.sort(key=lambda r: str(r.get(args.sort, "")))

    if not os.path.exists(args.template):
        raise SystemExit(f"template not found: {args.template}")
    from openpyxl import load_workbook  # noqa: PLC0415

    wb = load_workbook(args.template)
    if "Datasets" not in wb.sheetnames:
        raise SystemExit(f"template has no 'Datasets' sheet: {args.template}")
    ws = wb["Datasets"]

    actual = [c.value for c in ws[1]][: len(DATASET_HEADERS)]
    if actual != DATASET_HEADERS:
        raise SystemExit(
            "template header row does not match the required nine fields.\n"
            f"expected: {DATASET_HEADERS}\nfound:    {actual}"
        )
    # Read the look before the example goes: the reference template ships a formatted example
    # row 2 (and blank formatted rows down to 301) plus the example indicators sheet 'TABEL1_1'.
    style = TemplateStyle(wb)
    if ws.max_row > 1:
        ws.delete_rows(2, ws.max_row - 1)
    # The example row and its sheet are not this run's data; leaving the sheet in would deliver
    # a sheet that belongs to no row.
    for stale in list(wb.sheetnames):
        if stale not in ("Instructions", "Datasets"):
            del wb[stale]

    # One name per dataset, decided for the whole workbook at once, so that two ids which
    # sanitize to the same thing cannot quietly share a sheet and lose one dataset's rows.
    names = sheet_name_map(cell_text(rec, "dataset_id") for rec in records)

    indicator_total = 0
    reshaped: list[tuple[str, str]] = []
    for offset, rec in enumerate(records):
        row = 2 + offset
        dataset_id = cell_text(rec, "dataset_id")
        name = names[dataset_id]
        if name != dataset_id:
            reshaped.append((dataset_id, name))
        for col, field in enumerate(DATASET_COLUMNS, start=1):
            # Column D carries the sheet name: the template makes the dataset's ID and the
            # name of its indicators sheet the same string.
            value = name if field == "dataset_id" else cell_text(rec, field)
            style.dataset_body[col - 1].apply(ws.cell(row=row, column=col, value=value))
        if args.row_height:
            ws.row_dimensions[row].height = args.row_height

        rows = indicator_rows(rec)
        indicator_total += len(rows)
        write_indicator_sheet(wb, name, rows, style)

    last = 1 + len(records)
    ws.auto_filter.ref = f"A1:I{last}"
    ws.freeze_panes = "A2"

    out_dir = os.path.dirname(os.path.abspath(args.out))
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)
    wb.save(args.out)

    partial = sum(1 for r in records if (r.get("evidence") or {}).get("data_read") == "partial")
    print(f"Wrote {args.out}")
    print(f"  datasets:          {len(records)}")
    print(f"  rows partial:      {partial}")
    print(f"  indicators sheets: {len(records)}")
    print(f"  indicator rows:    {indicator_total} (mean {indicator_total / len(records):.1f} per dataset)")
    if reshaped:
        print(f"  dataset ids reshaped to fit an Excel sheet name: {len(reshaped)}")
        for source, name in reshaped[:20]:
            print(f"    {source}  ->  {name}")
        if len(reshaped) > 20:
            print(f"    ... and {len(reshaped) - 20} more")
        print("  Column D carries the reshaped form, as the template's Instructions sheet requires.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
