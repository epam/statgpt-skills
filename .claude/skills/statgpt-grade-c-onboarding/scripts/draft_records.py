#!/usr/bin/env python3
"""Extract the mechanical part of a record from local table files - no model tokens per dataset.

For a portal whose datasets all have the same shape (a stub column of line items and a row of
period headers - central-bank and ministry spreadsheet portals are almost always like this),
this script reads the files and derives, per dataset:

  - the candidate indicator rows: the line-item labels of every sheet, each with a
    dataset-unique `suggested_indicator`, its ancestor chain, its observation count and the
    sheets it appears on
  - the non-empty period bounds per frequency, and the frequency itself
  - the observation count
  - unit hints found in the title block and the footnotes

It writes one draft per dataset to <workdir>/drafts/<safe_id>.json. A draft is NOT a record:
reference area, regional coverage, description and the final indicator wording still need a
worker. But the worker then reviews a small draft instead of reading 40 sheets, which is where
the tokens actually go.

Because one drafter serves every dataset, a bug here is wrong identically on a hundred
records. Every rule below is in the script rather than in a worker's prompt for that reason,
and each of these six was a real defect found by calibration, by cross-checking records
against the draft, or by two workers reporting the same anomaly:

  1. The leftmost text column is not necessarily the label column. On a bilingual portal it
     is the local-language label and the English one sits far to the right, past the last
     data column, under a header reading "Items". An ASCII test does not find it - plenty of
     languages are ASCII too. So: look for a label header in the header band, then fall back
     to scoring candidate columns for English vocabulary.
  2. A year label is not one-per-block. Forward-filling a year row mislabels every block
     whose year sits on the block's LAST column, which called 87 of 108 quarterly and monthly
     tables "Annual". So: assign periods run by run, and let the single distinct year label
     found anywhere inside a run's span win.
  3. A literal 0 and a dash are not observations. Testing "is a number" reported all-zero and
     all-'-' line items as published series.
  4. Stripping a trailing footnote marker also eats the "2)" of "Broad Money (M2)". So: roll
     back any strip that leaves the parentheses unbalanced.
  5. The row above a repeated label is not always its parent - on a list of partner countries
     it is a SIBLING, which produced indicator names like "laos, laos, malaysia". So: qualify
     a name only from the label's own numbering, and otherwise hand the bare label back
     flagged `still_ambiguous` so a worker reads the sheet.
  6. Quarter columns written as the quarter's last month (2004-03, 2004-06, ...) are not a
     monthly series with nine months missing a year.

Usage:
    python draft_records.py work/ --plan work/plan.json
    python draft_records.py work/ --plan work/plan.json --only TABEL1_1

The plan is a JSON list, one object per dataset:
    [{"dataset_id": "TABEL1_1",
      "dataset_url": "https://.../TABEL1_1.xls",
      "dataset_name": "I.1. Broad Money and its Affecting Factors",
      "files": ["work/raw/TABEL1_1-9f2a1c/TABEL1_1.xlsx"],
      "sheets": "*",            # or ["Jan-Dec 2024", "2002-2017"]
      "stub_col": 0,            # optional 0-based override, otherwise detected
      "label_col": 221,         # optional 0-based override for the English label column
      "unit": "billions of Rp"  # optional, otherwise taken from the unit hints
     }, ...]

Legacy .xls must be converted to .xlsx first - see references/sources.md section 5 for how,
and for the year-stored-as-a-date-serial trap that a naive conversion walks into.
"""

from __future__ import annotations

import argparse
import collections
import datetime
import json
import os
import re
import sys

from openpyxl import load_workbook

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _gradec import safe_id  # noqa: E402

# Month names and abbreviations. English first, then the non-English forms that turn up in
# period headers on national portals; a three-letter prefix is enough to identify one.
MONTH_PREFIX = {
    "jan": 1, "feb": 2, "peb": 2, "fev": 2, "mar": 3, "maa": 3, "apr": 4, "abr": 4, "avr": 4,
    "may": 5, "mei": 5, "mai": 5, "mag": 5, "jun": 6, "giu": 6, "jul": 7, "lug": 7, "jui": 7,
    "aug": 8, "ags": 8, "agu": 8, "ago": 8, "aou": 8, "sep": 9, "set": 9, "oct": 10, "okt": 10,
    "ott": 10, "out": 10, "nov": 11, "nop": 11, "dec": 12, "des": 12, "dez": 12, "dic": 12,
    "dis": 12,
}
QUARTER_RE = re.compile(r"^(?:q|k|tw\.?\s*|triwulan\s*|trim\.?\s*|kv\.?\s*)([1-4]|i{1,3}|iv)\b", re.I)
ROMAN = {"i": 1, "ii": 2, "iii": 3, "iv": 4}

# Header cells that mark the column of line-item labels. This is how the English label column
# is found when it does not sit where a naive reader would look for it.
LABEL_HEADERS = {
    "items", "item", "itmes", "indicator", "indicators", "description", "descriptions",
    "series", "particulars", "variable", "variables", "concept", "subject", "measure",
    "line item", "line items", "component", "components", "category", "categories",
}

# "No data", written the many ways a statistical publisher writes it.
EMPTYISH = {"", "-", "--", "---", "...", "..", ".", "n.a.", "na", "n/a", "nil", "x", "*",
            ":", "c", "..."}

# Trailing footnote / revision markers glued onto a label: " 4)", "2)", "*", "**", " r".
MARKER_RE = re.compile(r"(\s*\d+\s*\)|\s*\*+|\s+r)\s*$")

UNIT_HINT_RE = re.compile(
    r"\b(billions?|millions?|thousands?|trillions?|percent|per cent|persons?|units?|index|"
    r"=\s?100|Rp|IDR|USD|EUR|GBP|JPY|tonnes?|tons?|GWh|kWh|barrels?|hectares?)\b",
    re.I,
)

# Numbering prefixes, deepest structural signal a stub column usually carries. Indentation
# rarely survives a format conversion; "I." / "A." / "1." / "a." / "-" does.
PREFIX_LEVEL = (
    (re.compile(r"^(?:i{1,3}|iv|v|vi{1,3}|ix|xi{0,3})\.\s", re.I), 0),
    (re.compile(r"^[A-Z]\.\s"), 1),
    (re.compile(r"^\d+(?:\.\d+)*\.\s"), 2),
    (re.compile(r"^[a-z][.)]\s"), 3),
    (re.compile(r"^[-*•·]\s"), 4),
)

# English statistical vocabulary, used to tell a column of English labels from a column of
# labels in the source's own language. Scoring vocabulary, not characters: a great many
# languages are pure ASCII, so an ASCII test silently accepts the wrong column.
EN_WORDS = set("""the and of to in for by on with other others total net gross claims
liabilities deposits loans credits money currency demand time savings foreign domestic
government private sector sectors banks bank central rural commercial assets capital income
expenditure exports imports balance trade reserves interest rate average outstanding position
end period securities residents nonresidents non-residents public state regional national
joint branch offices enterprises corporations households services goods primary secondary
current account financial transactions errors omissions memorandum item share value price
index volume number amount receipts payments consumption investment production output
employment unemployment population male female urban total revenue tax taxes debt equity
shares bonds bills notes cash transfers subsidies grants imports monthly annual quarterly
of which whereof including excluding per capita real nominal seasonally adjusted""".split())


def text(value: object) -> str:
    return re.sub(r"\s+", " ", str(value)).strip() if value is not None else ""


def strip_marker(label: str) -> str:
    """Drop trailing footnote / revision markers, without eating a real suffix.

    'Broad Money (M2)' has to survive: the digit-then-paren rule would strip the '2)' and
    leave the unbalanced 'Broad Money (M'. So a strip that unbalances the parentheses is
    rolled back.
    """
    previous = None
    while label != previous:
        previous = label
        cut = MARKER_RE.sub("", label).strip()
        if cut.count("(") != cut.count(")"):
            return label
        label = cut
    return label


def is_number(value: object) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def nonempty(value: object) -> bool:
    """True only for a cell that is a real observation.

    A literal 0 across every column, and an item whose "no data" marker is the string '-',
    are not published series. Testing only "is this a number" reported both as data, so they
    would have become indicator rows for series the portal does not publish.
    """
    if value is None:
        return False
    if is_number(value):
        return value != 0
    body = text(value).lower()
    if body in EMPTYISH:
        return False
    # A text cell is an observation only when it IS a number (a value stored as text, perhaps
    # with a revision flag). "Any digit" counted footnote markers like "1)" and whole labels
    # like "1. Non-oil and gas" as observations, and a label column mapped as a period column.
    body = re.sub(r"[\s*r]+$", "", body)
    if re.fullmatch(r"\(\s*[\d.,]+\s*\)", body):
        body = body.strip("() ")
    try:
        number = float(body.replace(",", ""))
    except ValueError:
        return False
    return number != 0


def year_of(value: object) -> int | None:
    """Calendar year, or the first year of a 'YYYY/YY' fiscal-year label."""
    if is_number(value):
        n = int(value)
        return n if 1800 <= n <= 2100 and float(value) == n else None
    body = strip_marker(text(value))
    m = re.fullmatch(r"((?:1[89]|20)\d{2})\s*/\s*\d{2,4}", body)
    if m:
        return int(m.group(1))
    if re.fullmatch(r"(?:1[89]|20)\d{2}", body):
        return int(body)
    return None


def is_fiscal(value: object) -> bool:
    return bool(re.fullmatch(r"((?:1[89]|20)\d{2})\s*/\s*\d{2,4}", strip_marker(text(value))))


def quarter_of(value: object) -> int | None:
    if is_number(value):
        return None
    m = QUARTER_RE.match(strip_marker(text(value)))
    if not m:
        return None
    body = m.group(1).lower()
    return int(body) if body.isdigit() else ROMAN[body]


def month_of(value: object) -> tuple[str, object] | None:
    """('D', datetime) for a real date cell, ('M', 1..12) for a month label, else None."""
    if isinstance(value, datetime.datetime):
        return ("D", value)
    if isinstance(value, datetime.date):
        return ("D", datetime.datetime(value.year, value.month, value.day))
    if is_number(value):
        return None
    body = strip_marker(text(value)).lower()
    if not body:
        return None
    key = re.split(r"[^a-z]", body)[0][:3]
    return ("M", MONTH_PREFIX[key]) if key in MONTH_PREFIX else None


def english_score(values: list[str]) -> int:
    """How much a column of labels reads as English. Higher is more English."""
    score = 0
    for value in values:
        for word in re.findall(r"[A-Za-z'-]+", value.lower()):
            if word in EN_WORDS:
                score += 1
    return score


def runs_of(columns: list[int]) -> list[list[int]]:
    """Split sorted column indices into runs, breaking on any gap of two or more.

    The gap is what separates one year's block of period columns from the next: publishers
    leave an unheaded spacer column between blocks, and it often carries the block's total.
    """
    out: list[list[int]] = []
    current: list[int] = []
    for column in columns:
        if current and column - current[-1] > 1:
            out.append(current)
            current = []
        current.append(column)
    if current:
        out.append(current)
    return out


def annual_stamp(value: object) -> str:
    """'1985' for a calendar year; '1984/85' for a fiscal year, never a bare '1984'.

    A fiscal year 1984/85 (April-March) stamped '1984' made one table claim calendar-1984 data.
    """
    if is_fiscal(value):
        m = re.fullmatch(r"((?:1[89]|20)\d{2})\s*/\s*(\d{2,4})", strip_marker(text(value)))
        return "%s/%s" % (m.group(1), m.group(2)[-2:])
    return "%d" % year_of(value)


def annual_after(run: list[int], in_run: set[int], header: list, body: list[list],
                 ncol: int) -> int | None:
    """The unheaded, mostly numeric column within two columns after a run, or None."""
    for following in range(run[-1] + 1, min(run[-1] + 3, ncol)):
        if following in in_run or (following < len(header) and text(header[following])):
            return None
        cells = [row[following] for row in body if following < len(row) and row[following] is not None]
        numeric = sum(1 for v in cells if nonempty(v))
        texty = sum(1 for v in cells if isinstance(v, str) and not nonempty(v) and text(v).lower() not in EMPTYISH)
        if numeric and numeric > texty:
            return following
    return None


def assign_years(runs: list[list[int]], year_row: list | None, ncol: int, lookahead: int = 1) -> list[int | None]:
    """One year per run of period columns.

    The single distinct year label found anywhere inside the run's span wins, wherever it
    sits - on the run's first column, its last, or the total column just after it. Only a run
    with no unambiguous label falls back to the ordinal rule, where the Nth year label from
    the left belongs to the Nth run. Forward-filling the year row instead is what made 87 of
    108 tables report the wrong frequency.
    """
    # Distinct years in order: a publisher that labels both the first and the last column of
    # each year block (1990 ... 1990 1991 ... 1991) otherwise counts every year twice.
    ordinal: list[int] = []
    for v in (year_row or []):
        y = year_of(v)
        if y is not None and (not ordinal or ordinal[-1] != y):
            ordinal.append(y)
    years: list[int | None] = []

    def labels(low: int, high: int) -> list[int]:
        out: list[int] = []
        for column in range(low, high + 1):
            y = year_of(year_row[column]) if year_row and column < len(year_row) else None
            if y is not None and y not in out:
                out.append(y)
        return out

    for i, run in enumerate(runs):
        # The run's own columns first; the look-ahead column can hold the NEXT block's label.
        found = labels(run[0], run[-1])
        if not found:
            found = labels(run[0], min(run[-1] + lookahead, ncol - 1))
        if len(found) == 1:
            years.append(found[0])
        elif not found and years and years[-1]:
            # An unlabelled run right after a labelled one is the next year. The ordinal rule
            # drifts as soon as there are more runs than year labels.
            years.append(years[-1] + 1)
        elif i < len(ordinal):
            years.append(ordinal[i])
        elif years and years[-1]:
            years.append(years[-1] + 1)
        else:
            years.append(None)
    return years


def depth_of(label: str) -> int | None:
    """Hierarchy depth from the label's own numbering prefix, or None when it has none."""
    body = label.strip()
    for pattern, level in PREFIX_LEVEL:
        if pattern.match(body):
            return level
    return None


def find_label_header_col(rows: list[list], header_row: int) -> int | None:
    """The label column marked by a header cell such as 'Items' in the header band.

    Searched across a band rather than one row, because the header sits at a different height
    on each era sheet. This is the only reliable way to find a label column that sits past the
    last data column - on one real portal it was column 221.
    """
    for r in range(0, min(len(rows), header_row + 4)):
        for c, value in enumerate(rows[r]):
            if text(value).lower().strip(": ") in LABEL_HEADERS:
                return c
    return None


def pick_columns(rows: list[list], body: list[list], header_row: int,
                 stub_override: int | None, label_override: int | None) -> tuple[int, int | None]:
    """-> (stub column, label column or None).

    The stub column is the text-densest column; the label column is the one that actually
    carries English labels, which is not always the same column and is not always to its left.
    """
    density: collections.Counter[int] = collections.Counter()
    for row in body:
        for c, value in enumerate(row):
            body_text = text(value)
            if (body_text and not is_number(value) and len(body_text) > 2
                    and not re.fullmatch(r"[\d\s.,%*()/-]+", body_text)):
                density[c] += 1
    if not density:
        return (stub_override or 0, label_override)

    if stub_override is not None:
        stub = stub_override
    else:
        top = max(density.values())
        stub = min((c for c, n in density.items() if n >= max(3, 0.4 * top)),
                   default=density.most_common(1)[0][0])

    if label_override is not None:
        return stub, label_override

    def column_values(column: int) -> list[str]:
        return [text(row[column]) for row in body if column < len(row) and text(row[column])][:60]

    label = find_label_header_col(rows, header_row)
    if label is None or label == stub or density.get(label, 0) < 2:
        # No usable label header. Score every reasonably dense column for English and take
        # the best - including columns to the RIGHT of the stub, which is where a bilingual
        # publisher puts the English repeat.
        label, best = None, 0
        for column in sorted(density, reverse=True):
            if column == stub or density[column] < 0.4 * density[stub]:
                continue
            score = english_score(column_values(column))
            if score > best:
                label, best = column, score
    if label is not None:
        # Guard the header-derived column too: sometimes 'Items' sits above a local-language
        # column, or the English repeat is simply missing on that sheet.
        if english_score(column_values(label)) < english_score(column_values(stub)):
            label = None
    return stub, label


def map_periods(header: list, year_row: list | None, body: list[list], kind: str,
                ncol: int) -> tuple[dict[int, tuple[str, str]], bool]:
    """Column index -> (frequency, period stamp), for every headed data column."""
    per_column: dict[int, tuple[str, str]] = {}
    fiscal = False

    if kind == "Q":
        quarter_cols = [c for c, v in enumerate(header) if quarter_of(v)]
        # A run ends where the quarter number stops increasing.
        runs: list[list[int]] = []
        current: list[int] = []
        for column in quarter_cols:
            if current and quarter_of(header[column]) <= quarter_of(header[current[-1]]):
                runs.append(current)
                current = []
            current.append(column)
        if current:
            runs.append(current)
        years = assign_years(runs, year_row, ncol, lookahead=2)
        in_run = {c for run in runs for c in run}
        for run, year in zip(runs, years):
            if year is None:
                continue
            for column in run:
                per_column[column] = ("Quarterly", "%d-Q%d" % (year, quarter_of(header[column])))
            # The column just after a COMPLETE run of quarters is usually that year's annual
            # total. A partial year (Q1-Q2 of the latest year) has no annual column, and
            # looking past it reached the label column and stamped it "Annual <year>".
            if len(run) == 4:
                annual = annual_after(run, in_run, header, body, ncol)
                if annual is not None:
                    per_column[annual] = ("Annual", "%d" % year)

    elif kind == "M":
        month_cols = [c for c, v in enumerate(header) if month_of(v)]
        date_cols = [c for c in month_cols if month_of(header[c])[0] == "D"]
        for column in date_cols:
            stamp = month_of(header[column])[1]
            per_column[column] = ("Monthly", "%04d-%02d" % (stamp.year, stamp.month))
        label_cols = [c for c in month_cols if c not in date_cols]
        # A run also ends where the month number stops increasing: years laid out with no
        # spacer column (Jan..Dec Jan..Dec) were one run, and 15 years collapsed into one.
        runs = []
        for run in runs_of(label_cols):
            if len(run) <= 12:
                # One year's block: a stray repeated label inside it is a typo, not a reset.
                runs.append(run)
                continue
            current: list[int] = []
            for column in run:
                if current and month_of(header[column])[1] <= month_of(header[current[-1]])[1]:
                    runs.append(current)
                    current = []
                current.append(column)
            if current:
                runs.append(current)
        in_run = set(month_cols)
        for run, year in zip(runs, assign_years(runs, year_row, ncol)):
            if year is None:
                continue
            for column in run:
                per_column[column] = ("Monthly", "%04d-%02d" % (year, month_of(header[column])[1]))
            # An unheaded column right after a complete Jan-Dec run is the year's annual
            # (year-end or total) value - the monthly twin of the quarterly rule above.
            if len(run) == 12:
                annual = annual_after(run, in_run, header, body, ncol)
                if annual is not None:
                    per_column[annual] = ("Annual", "%d" % year)
        for column, value in enumerate(header):
            if column not in per_column and year_of(value) is not None and not month_of(value):
                per_column[column] = ("Annual", annual_stamp(value))
                fiscal = fiscal or is_fiscal(value)

    else:
        for column, value in enumerate(header):
            year = year_of(value)
            if year is not None:
                per_column[column] = ("Annual", annual_stamp(value))
                fiscal = fiscal or is_fiscal(value)

    # Quarter columns written as the LAST MONTH of the quarter (2004-03, 2004-06, 2004-09,
    # 2004-12) read literally as a monthly series missing nine months a year. If every monthly
    # period on this sheet falls on a quarter end, and there are enough of them to be a real
    # series, they are quarters.
    months = [p for f, p in per_column.values() if f == "Monthly"]
    if len(months) >= 4 and all(int(p[5:7]) in (3, 6, 9, 12) for p in months):
        per_column = {
            c: (("Quarterly", "%s-Q%d" % (p[:4], (int(p[5:7]) + 2) // 3)) if f == "Monthly" else (f, p))
            for c, (f, p) in per_column.items()
        }
    return per_column, fiscal


def scan_sheet(ws, stub_override: int | None, label_override: int | None) -> dict | None:
    """Period columns with data, line-item rows with data, unit hints, observation count."""
    rows = [list(r) for r in ws.iter_rows(min_row=1, max_row=min(ws.max_row or 1, 2000),
                                          max_col=min(ws.max_column or 1, 400), values_only=True)]
    if not rows:
        return None
    ncol = max((len(r) for r in rows), default=0)
    if not ncol:
        return None
    rows = [list(r) + [None] * (ncol - len(r)) for r in rows]

    # Header row: the row in the top band with the most period-like cells, and the kind of
    # period it holds. Kind matters, because a row of quarter labels and a row of year labels
    # need different period arithmetic.
    header_row = kind = None
    best = 0
    for r in range(min(25, len(rows))):
        for candidate_kind, n in (
            ("Q", sum(1 for v in rows[r] if quarter_of(v))),
            ("M", sum(1 for v in rows[r] if month_of(v))),
            ("A", sum(1 for v in rows[r] if year_of(v) is not None)),
        ):
            if n > best and n >= 3:
                header_row, kind, best = r, candidate_kind, n
    if header_row is None:
        return None

    # A year repeated over every month (1990 1990 ... 1990 1991 ...) outscores the month row
    # beneath it, and the whole sheet was read as annual - 20 years of monthly data lost on
    # several tables. A month or quarter row right under a year row is the real header.
    if kind == "A":
        for r in range(header_row + 1, min(header_row + 3, len(rows))):
            for sub_kind, test in (("M", month_of), ("Q", quarter_of)):
                n = sum(1 for v in rows[r] if test(v))
                if n >= 3 and n >= best * 0.5:
                    header_row, kind, best = r, sub_kind, n
                    break
            else:
                continue
            break

    # Prefer a lower row of real date cells: publishers often leave a half-broken duplicate
    # header directly above the good one. But the reverse happens too: a complete month-name
    # row (with its year row) above a STALE date row left over from another sheet - on SEKI
    # 1990-2003 era sheets the date row said 1999-01..2010-06 under month names for 1990-2003.
    # So a date row only wins over a month-name row when it clearly has more period cells.
    month_names = sum(1 for v in rows[header_row] if isinstance(v, str) and month_of(v))
    need = max(best * 0.8, month_names * 1.2)
    for r in range(header_row + 1, min(header_row + 3, len(rows))):
        if sum(1 for v in rows[r] if isinstance(v, (datetime.datetime, datetime.date))) >= max(3, need):
            header_row, kind = r, "M"
            break

    header = rows[header_row]
    year_row = None
    for r in range(header_row - 1, max(-1, header_row - 4), -1):
        if sum(1 for v in rows[r] if year_of(v) is not None) >= 1:
            year_row = rows[r]
            break

    body = rows[header_row + 1:]
    stub, label_col = pick_columns(rows, body, header_row, stub_override, label_override)
    per_column, fiscal = map_periods(header, year_row, body, kind, ncol)
    # The label columns are never period columns, whatever header sits above them.
    for column in (stub, label_col):
        per_column.pop(column, None)
    if not per_column:
        return None

    ordered: list[dict] = []
    per_freq: dict[str, set[str]] = collections.defaultdict(set)
    observations = 0
    previous_label = ""
    stack: dict[int, str] = {}
    label_rows: set[int] = set()

    for offset, row in enumerate(body):
        stub_label = strip_marker(text(row[stub])) if stub < len(row) else ""
        english = strip_marker(text(row[label_col])) if label_col is not None and label_col < len(row) else ""
        if not stub_label and not english:
            continue
        label_rows.add(header_row + 1 + offset)

        count = 0
        for column, (frequency, period) in per_column.items():
            if column < len(row) and nonempty(row[column]):
                count += 1
                per_freq[frequency].add(period)

        name = english or stub_label
        level = depth_of(name)
        if level is None:
            level = depth_of(stub_label)
        from_prefix = level is not None
        if from_prefix:
            for deeper in [k for k in stack if k >= level]:
                del stack[deeper]
            path = [stack[k] for k in sorted(stack)]
            stack[level] = name
        else:
            path = [previous_label] if previous_label else []

        if not count:
            # A labelled row with no data is a section heading or a dropped item. Headings are
            # what the next row hangs under, so it is remembered as a possible parent.
            previous_label = name or previous_label
            continue
        observations += count
        ordered.append({
            "row": header_row + 2 + offset,
            "indicator": name,
            "source_label": stub_label,
            "observations": count,
            "under": previous_label,
            "path": path,
            "path_from_prefix": from_prefix,
            "is_english": bool(english),
        })
        previous_label = name

    # Unit hints live in the title block above the header and in the footnote block at the
    # bottom - never in the label column, whose labels would otherwise pose as units.
    units: list[str] = []
    hint_rows = list(range(0, header_row + 1)) + list(range(max(header_row + 1, len(rows) - 12), len(rows)))
    for r in hint_rows:
        if r in label_rows:
            continue
        for value in rows[r]:
            if isinstance(value, str) and UNIT_HINT_RE.search(value) and len(value) < 160:
                units.append(value.strip())

    return {
        "sheet": ws.title,
        "header_row": header_row + 1,
        "stub_col": stub + 1,
        "label_col": (label_col + 1) if label_col is not None else None,
        "kind": kind,
        "fiscal_year_columns": fiscal,
        "period_columns": len(per_column),
        "rows": ordered,
        "units": units,
        "per_freq": {k: sorted(v) for k, v in per_freq.items()},
        "observations": observations,
    }


def suggest_names(candidates: list[dict]) -> list[dict]:
    """Give every candidate a name that is unique within the dataset.

    A bare 'Loans' appearing under four parents is four indicator rows, and the validator
    rejects a record that writes them identically. Resolving that is mechanical once the
    ancestor chain is known, so it is done here rather than in a hundred worker prompts -
    duplicate indicator rows were the single largest source of validation errors.

    A name is qualified ONLY when the chain came from the label's own numbering. Without that,
    'path' is just the row above, which on a list of countries or currencies is a SIBLING;
    chaining it produced names like 'laos, laos, malaysia' that workers copied verbatim. The
    bare label flagged ambiguous is a better answer than a confident wrong one.
    """
    counts = collections.Counter(c["indicator"] for c in candidates)
    for candidate in candidates:
        name = candidate["indicator"]
        if counts[name] > 1 and candidate["path_from_prefix"]:
            for depth in range(1, len(candidate["path"]) + 1):
                name = ", ".join(candidate["path"][-depth:] + [candidate["indicator"]])
                if sum(1 for other in candidates
                       if other["path_from_prefix"]
                       and ", ".join(other["path"][-depth:] + [other["indicator"]]) == name) == 1:
                    break
        candidate["suggested_indicator"] = name

    seen = collections.Counter(c["suggested_indicator"] for c in candidates)
    for candidate in candidates:
        candidate["still_ambiguous"] = seen[candidate["suggested_indicator"]] > 1
        candidate["suggestion_reliable"] = (
            candidate["is_english"]
            and not candidate["still_ambiguous"]
            and (candidate["path_from_prefix"]
                 or candidate["suggested_indicator"] == candidate["indicator"])
        )
    return candidates


def collapse(blocks: list[dict]) -> list[dict]:
    """One candidate per distinct (ancestor chain, line item), in first-appearance order.

    Era sheets repeat the same line-item list, so the raw per-sheet rows are several times
    redundant. Keying on the chain keeps what a worker needs - that a bare 'Loans' occurs
    under four different parents and is therefore four indicator rows - while dropping the era
    duplication. 'sheets' is what rule I-9 needs to mark era-limited items.
    """
    out: dict[tuple, dict] = {}
    for block in blocks:
        for row in block["rows"]:
            key = (tuple(row["path"]), row["indicator"])
            entry = out.get(key)
            if entry is None:
                entry = out[key] = {
                    "indicator": row["indicator"],
                    "source_label": row["source_label"],
                    "path": row["path"],
                    "path_from_prefix": row["path_from_prefix"],
                    "is_english": row["is_english"],
                    "under": row["under"],
                    "observations": 0,
                    "sheets": [],
                    "first_row": row["row"],
                }
            entry["observations"] += row["observations"]
            if block["sheet"] not in entry["sheets"]:
                entry["sheets"].append(block["sheet"])
    return suggest_names(list(out.values()))


FREQUENCY_ORDER = ["Daily", "Business daily", "Weekly", "Monthly", "Quarterly",
                   "Semi-annual", "Annual", "Irregular"]


def draft_dataset(entry: dict) -> dict:
    files = entry.get("files") or ([entry["file"]] if entry.get("file") else [])
    wanted = entry.get("sheets", "*")
    stub_override = entry.get("stub_col")
    label_override = entry.get("label_col")

    blocks: list[dict] = []
    per_freq: dict[str, set[str]] = collections.defaultdict(set)
    units: collections.Counter[str] = collections.Counter()
    observations = 0
    sheets_read: list[str] = []
    sheet_shapes: list[dict] = []

    for path in files:
        if path.lower().endswith(".xls"):
            raise SystemExit(
                f"{path}: legacy .xls - convert it to .xlsx first, and mind the year-as-date-serial "
                "trap (references/sources.md, section 5)"
            )
        wb = load_workbook(path, data_only=True, read_only=True)
        names = wb.sheetnames if wanted == "*" else [s for s in wb.sheetnames if s in wanted]
        for name in names:
            result = scan_sheet(wb[name], stub_override, label_override)
            if not result or not result.get("rows"):
                continue
            tag = f"{os.path.basename(path)}:{name}"
            sheets_read.append(tag)
            observations += result["observations"]
            for hint in result["units"]:
                units[hint] += 1
            for frequency, periods in result["per_freq"].items():
                per_freq[frequency].update(periods)
            blocks.append({"sheet": tag, "rows": result["rows"]})
            sheet_shapes.append({
                "sheet": tag, "header_row": result["header_row"], "stub_col": result["stub_col"],
                "label_col": result["label_col"], "period_columns": result["period_columns"],
                "fiscal_year_columns": result["fiscal_year_columns"],
            })
        wb.close()

    candidates = collapse(blocks)
    bounds = {f: [min(p), max(p)] for f, p in per_freq.items() if p}
    frequencies = [f for f in FREQUENCY_ORDER if f in bounds]
    unit_guess = entry.get("unit") or ""
    ambiguous = sum(1 for c in candidates if not c["suggestion_reliable"])

    return {
        "dataset_id": entry["dataset_id"],
        "dataset_name": entry.get("dataset_name", ""),
        "dataset_url": entry.get("dataset_url", ""),
        "draft": True,
        "frequency_coverage": "; ".join(frequencies),
        "period_min_max": bounds,
        "observation_count": observations,
        "sheets_read": sheets_read,
        "sheet_shapes": sheet_shapes,
        "unit_from_plan": unit_guess,
        "unit_hints": [hint for hint, _ in units.most_common(6)],
        "candidates_needing_a_look": ambiguous,
        "candidate_indicators": [
            {
                "indicator": c["suggested_indicator"],
                "source_label": c["source_label"],
                "unit": unit_guess,
                "observations": c["observations"],
                "sheets": c["sheets"][:6],
                "path": c["path"],
                "suggestion_reliable": c["suggestion_reliable"],
                "still_ambiguous": c["still_ambiguous"],
                "is_english": c["is_english"],
            }
            for c in candidates
        ],
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("workdir")
    ap.add_argument("--plan", required=True, help="JSON list of datasets to draft")
    ap.add_argument("--only", action="append", help="draft only these dataset ids")
    args = ap.parse_args()

    with open(args.plan, "r", encoding="utf-8") as fh:
        plan = json.load(fh)
    if isinstance(plan, dict):
        plan = plan.get("datasets", [])

    out_dir = os.path.join(args.workdir, "drafts")
    os.makedirs(out_dir, exist_ok=True)

    done = 0
    ambiguous_total = 0
    candidate_total = 0
    no_label_column: list[str] = []
    for entry in plan:
        if args.only and entry.get("dataset_id") not in args.only:
            continue
        try:
            draft = draft_dataset(entry)
        except SystemExit:
            raise
        except Exception as exc:  # noqa: BLE001 - one bad file must not stop the batch
            print(f"FAIL  {entry.get('dataset_id', '?')}: {type(exc).__name__}: {exc}")
            continue
        path = os.path.join(out_dir, safe_id(entry["dataset_id"]) + ".json")
        # ensure_ascii=True on purpose: a worker that opens a draft without naming an encoding
        # gets the platform default, and one non-ASCII byte in a UTF-8 draft killed a worker
        # with 'charmap codec can't decode byte 0x81'. A pure-ASCII draft cannot fail that way.
        with open(path, "w", encoding="utf-8", newline="\n") as fh:
            json.dump(draft, fh, ensure_ascii=True, indent=1)
        done += 1
        candidate_total += len(draft["candidate_indicators"])
        ambiguous_total += draft["candidates_needing_a_look"]
        if not any(s["label_col"] for s in draft["sheet_shapes"]):
            no_label_column.append(entry["dataset_id"])
        print(
            f"{entry['dataset_id']}: {len(draft['candidate_indicators'])} candidate indicators "
            f"({draft['candidates_needing_a_look']} to check by hand), "
            f"{draft['observation_count']} observations, {draft['frequency_coverage'] or 'no frequency'}, "
            f"{', '.join(f'{k} {v[0]}..{v[1]}' for k, v in draft['period_min_max'].items()) or 'no periods'}"
        )

    print(f"\n{done} drafts in {out_dir}")
    if candidate_total:
        print(f"{candidate_total} candidate indicator rows, {ambiguous_total} flagged "
              f"still_ambiguous or not English - a worker must read the sheet for those")
    if no_label_column:
        print(f"{len(no_label_column)} datasets have no English label column at all: "
              f"{', '.join(no_label_column[:10])}"
              + (" ..." if len(no_label_column) > 10 else ""))
        print("Those need a translation glossary in recipe.md, per field-rules E.")
    print("Drafts are not records: a worker still has to set reference area, regional coverage,")
    print("description, and the final indicator wording, then write work/records/<safe_id>.json.")
    print("Cross-check the records against these drafts with scripts/audit_corpus.py.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
