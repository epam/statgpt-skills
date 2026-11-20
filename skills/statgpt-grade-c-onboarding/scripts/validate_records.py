#!/usr/bin/env python3
"""Validate Grade C Dataset Discovery Index records before they go into the workbook.

Usage:
    python validate_records.py datasets.jsonl [--strict] [--quiet]
    python validate_records.py work/records/SOME_ID-9f2a1c.json
    python validate_records.py work/records/

Reads records (see SKILL.md "Record format"): the nine Datasets fields plus an indicators
list of {"indicator", "unit"} rows, one per row of the dataset's indicators sheet. Applies the
rules from references/field-rules.md and references/indicators.md that can be checked
mechanically, and prints ERROR / WARN lines with the record's location and dataset id.

WHAT BELONGS IN HERE, AND WHAT DOES NOT

This validator checks only things that are actually knowable:

  * closed standards        ISO 3166-1 alpha-3 codes; the template's frequency vocabulary
  * the template's grammar  required keys, non-empty fields, 'None' spelled exactly, a level
                            in parentheses after each region, the time_coverage sentence shape
  * Excel's documented      a sheet name is at most 31 characters and cannot contain : \\ / ? * [ ]
    limits
  * computable facts        duplicate rows, duplicate ids, colliding sheet names, unbalanced
                            parentheses, mojibake, a record that contradicts its own evidence,
                            an observation count below its own row count, word counts
  * fixed word lists the    the banned hedge vocabulary, which field-rules.md defines
    skill itself defines

It must NOT encode guesses about the world. There is no closed list of sub-national level
names, or of units of measure, or of what an indicator can be called: those vary by country,
agency and domain, and a rule built from one portal's vocabulary is wrong everywhere else -
silently, and in places nobody can predict. A check like that costs more than it finds,
because a reader learns to ignore its warnings.

Judgments of that kind live in scripts/audit_corpus.py instead, which tallies a field across
every record and lets a reader decide. That is not a weaker version of validation; it is how
nine of the twenty-five defects on a real run were actually found, and it needs no vocabulary:
"105 of 109 records say None" is a fact, and the reader supplies the suspicion.

Exit code 0 when there are no errors (and, with --strict, no warnings), else 1.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from collections import Counter

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _gradec import (  # noqa: E402
    SHEET_NAME_BAD,
    SHEET_NAME_MAX,
    indicator_rows,
    is_legacy_indicators,
    safe_id,
    sheet_name,
)

FIELDS = [
    "reference_area",
    "regional_coverage",
    "agency",
    "dataset_id",
    "dataset_name",
    "description",
    "dataset_url",
    "time_coverage",
    "frequency_coverage",
    "indicators",
]

REQUIRED_NON_EMPTY = [
    "reference_area",
    "regional_coverage",
    "agency",
    "dataset_id",
    "dataset_name",
    "description",
    "dataset_url",
    "time_coverage",
    "frequency_coverage",
    "indicators",
]

FREQUENCIES = [
    "Daily",
    "Business daily",
    "Weekly",
    "Monthly",
    "Quarterly",
    "Semi-annual",
    "Annual",
    "Irregular",
]

# Hedging that always makes a cell unusable for the search layer. Word-boundary matched,
# case-insensitive: plain substring matching false-positives on real content
# ("privatization/asset" contains "n/a", "4 wheels and more" contains "and more").
HARD_HEDGES = [
    r"\betc\b",
    r"\bincluding but not limited to\b",
    r"\band so on\b",
    r"\bvarious\b",
    r"\bmultiple indicators\b",
    r"\bseveral indicators\b",
    r"\bvarious indicators\b",
    r"\bmain indicators\b",
    r"\bTBD\b",
    r"\bto be determined\b",
    r"\bnot specified\b",
]

# Hedging in some contexts, legitimate source wording in others (a residual category called
# "others", a maturity bucket "4 wheels and more", a source cell literally marked "N/A").
# Reported as warnings: read them, keep the legitimate ones.
SOFT_HEDGES = [
    r"\band others\b",
    r"\band more\b",
    r"\bamong others\b",
    r"\bunknown\b",
    r"\bN/A\b",
    r"\bseveral\b",
    r"\ba number of\b",
]

# Truncation marks. An error inside the indicator list, a warning elsewhere.
TRUNCATION = [r"\.\.\.", r"…"]

# Wording that betrays a breakdown folded into one indicator row instead of being written out
# as individual rows, which is what the template asks for.
FOLD_SMELLS = [
    r"\bseparately\b",
    r"\brespectively\b",
    r"\beach with\b",
    r"\bfull .{0,20}breakdown\b",
    r"\bbreakdown\b",
    r"\bby (?:economic sector|sector|industrial origin|partner|partner countr|instrument|tenor|maturity"
    r"|expenditure|purpose|holder|ownership|group of|bank group|type of|categor|classification|component)",
    r"\(\s*\d{2,}\s+\w+",          # "(17 sectors: ...", "(90 cities)"
    r"\bwith its members\b",
    r"\bwith claims on .{0,40}\band\b",
    r"\band .{0,30}\bseparately\b",
]

# Unit-ish text, used to spot a unit left inside the indicator name.
UNIT_LIKE = re.compile(
    r"\b(?:billions?|millions?|thousands?|units?|percent|percentage|index|=\s*100|persons|people"
    r"|tonnes?|tons?|barrels?|GWh|kWh|USD|EUR|IDR|Rp|per\s+\d|ratio|number of)\b",
    re.I,
)

# Markers of a broken decode: U+FFFD, plus UTF-8 bytes read as cp1252 / latin-1.
MOJIBAKE = ["\ufffd", "\u00e2\u20ac", "\u00c3\u0083", "\u00c2\u00a0"]

PERIOD = r"\d{4}(?:-(?:Q[1-4]|H[1-2]|W\d{2}|\d{2}(?:-\d{2})?))?"
# From <period> to <period>, or ... to present (latest available <period>[, note]),
# optionally followed by a note introduced by ", ", "; " or " (".
TIME_RE = re.compile(
    r"^From (?P<start>" + PERIOD + r") to "
    r"(?:present \(latest available " + PERIOD + r"[^)]*\)|" + PERIOD + r")"
    r"(?P<note>(?:[,;] | \().*)?$"
)

URL_SMELLS = ["sessionid", "jsessionid", "token=", "access_token", "sig=", "signature=", "&_=", "localhost"]

ISO3 = set(
    """ABW AFG AGO AIA ALA ALB AND ARE ARG ARM ASM ATA ATF ATG AUS AUT AZE BDI BEL BEN BES BFA BGD BGR BHR BHS
BIH BLM BLR BLZ BMU BOL BRA BRB BRN BTN BVT BWA CAF CAN CCK CHE CHL CHN CIV CMR COD COG COK COL COM CPV CRI CUB
CUW CXR CYM CYP CZE DEU DJI DMA DNK DOM DZA ECU EGY ERI ESH ESP EST ETH FIN FJI FLK FRA FRO FSM GAB GBR GEO GGY
GHA GIB GIN GLP GMB GNB GNQ GRC GRD GRL GTM GUF GUM GUY HKG HMD HND HRV HTI HUN IDN IMN IND IOT IRL IRN IRQ ISL
ISR ITA JAM JEY JOR JPN KAZ KEN KGZ KHM KIR KNA KOR KWT LAO LBN LBR LBY LCA LIE LKA LSO LTU LUX LVA MAC MAF MAR
MCO MDA MDG MDV MEX MHL MKD MLI MLT MMR MNE MNG MNP MOZ MRT MSR MTQ MUS MWI MYS MYT NAM NCL NER NFK NGA NIC NIU
NLD NOR NPL NRU NZL OMN PAK PAN PCN PER PHL PLW PNG POL PRI PRK PRT PRY PSE PYF QAT REU ROU RUS RWA SAU SDN SEN
SGP SGS SHN SJM SLB SLE SLV SMR SOM SPM SRB SSD STP SUR SVK SVN SWE SWZ SXM SYC SYR TCA TCD TGO THA TJK TKL TKM
TLS TON TTO TUN TUR TUV TWN TZA UGA UKR UMI URY USA UZB VAT VCT VEN VGB VIR VNM VUT WLF WSM XKX YEM ZAF ZMB ZWE
EUR EUU""".split()
)

# The end of a time_coverage string: what the record claims is its latest period.
LATEST_RE = re.compile(r"latest available (" + PERIOD + r")")
TO_PERIOD_RE = re.compile(r"^From " + PERIOD + r" to (" + PERIOD + r")(?:[,;] | \(|$)")


def period_key(period: str) -> tuple[int, int, int, int]:
    """(year, month-of-year, day, granularity rank) for a period stamp.

    Granularity is part of the key because a coarser stamp never proves a later period. An
    annual '2026' and a quarterly '2026-Q2' both sit in 2026, and the year label - which
    stands for a year still in progress - is NOT evidence that data runs past Q2. Ignoring
    that made every record whose evidence carried both an annual and a quarterly bound look
    self-contradictory. Rank: 0 annual, 1 semi-annual, 2 quarterly, 3 monthly/weekly, 4 daily.
    """
    body = str(period).strip()
    m = re.fullmatch(r"(\d{4})", body)
    if m:
        return (int(m.group(1)), 12, 31, 0)
    m = re.fullmatch(r"(\d{4})-H([1-2])", body)
    if m:
        return (int(m.group(1)), int(m.group(2)) * 6, 31, 1)
    m = re.fullmatch(r"(\d{4})-Q([1-4])", body)
    if m:
        return (int(m.group(1)), int(m.group(2)) * 3, 31, 2)
    m = re.fullmatch(r"(\d{4})-W(\d{2})", body)
    if m:
        return (int(m.group(1)), min(12, 1 + (int(m.group(2)) * 7) // 31), 31, 3)
    m = re.fullmatch(r"(\d{4})-(\d{2})", body)
    if m:
        return (int(m.group(1)), int(m.group(2)), 31, 3)
    m = re.fullmatch(r"(\d{4})-(\d{2})-(\d{2})", body)
    if m:
        return (int(m.group(1)), int(m.group(2)), int(m.group(3)), 4)
    return (0, 0, 0, 0)


def proves_later(evidence: tuple[int, int, int, int], claimed: tuple[int, int, int, int]) -> bool:
    """Does `evidence` prove a period genuinely later than `claimed`?

    A later year always does. Within the same year, only a stamp at least as fine as the
    claim can - see period_key.
    """
    if evidence[0] > claimed[0]:
        return True
    if evidence[0] < claimed[0]:
        return False
    return evidence[3] >= claimed[3] and evidence[:3] > claimed[:3]


class Report:
    def __init__(self) -> None:
        self.errors: list[str] = []
        self.warnings: list[str] = []
        self.ctx = ""

    def err(self, msg: str) -> None:
        self.errors.append(f"ERROR {self.ctx}: {msg}")

    def warn(self, msg: str) -> None:
        self.warnings.append(f"WARN  {self.ctx}: {msg}")


def text_of(rec: dict, field: str) -> str:
    value = rec.get(field, "")
    if field == "indicators":
        return "; ".join(f"{r['indicator']} ({r['unit']})" for r in indicator_rows(rec))
    return "" if value is None else str(value)


def check_reference_area(value: str, rep: Report) -> None:
    body = value
    if "partner countries:" in body:
        reporting, partners = body.split("partner countries:", 1)
        if not reporting.strip().strip(";").strip():
            rep.err("reference_area has 'partner countries:' but no reporting country before it")
        body = reporting + "; " + partners
    coded = 0
    groups: list[str] = []
    for entry in [e.strip() for e in body.split(";") if e.strip()]:
        match = re.search(r"\(([^)]*)\)\s*$", entry)
        if not match:
            groups.append(entry)
            continue
        code = match.group(1).split(",")[0].strip()
        if code not in ISO3:
            rep.err(f"reference_area entry has an invalid ISO 3166-1 alpha-3 code {code!r}: {entry!r}")
        else:
            coded += 1
    if groups:
        shown = ", ".join(groups[:8]) + (" ..." if len(groups) > 8 else "")
        rep.warn(
            f"reference_area has {len(groups)} entries without an ISO3 code, read as group labels "
            f"({shown}) - the search may not match them to a member-country question"
        )
    if coded == 0:
        rep.warn("reference_area contains no country with an ISO3 code, only group labels")


def check_time_coverage(value: str, freqs: list[str], rep: Report) -> None:
    if not TIME_RE.match(value):
        rep.err(
            "time_coverage does not match the required grammar "
            "'From <period> to <period>' / 'From <period> to present (latest available <period>)': "
            f"{value!r}"
        )
        return
    start = TIME_RE.match(value).group("start")
    if re.fullmatch(r"\d{4}-\d{2}", start) and "Monthly" not in freqs:
        rep.warn(f"time_coverage starts at monthly granularity {start!r} but frequency_coverage is {freqs}")
    if re.fullmatch(r"\d{4}-Q[1-4]", start) and "Quarterly" not in freqs:
        rep.warn(f"time_coverage starts at quarterly granularity {start!r} but frequency_coverage is {freqs}")


def check_frequency(value: str, rep: Report) -> list[str]:
    parts = [p.strip() for p in value.split(";") if p.strip()]
    for part in parts:
        if part not in FREQUENCIES:
            rep.err(
                f"frequency_coverage value {part!r} is outside the closed vocabulary {FREQUENCIES}"
            )
    known = [p for p in parts if p in FREQUENCIES]
    if known != sorted(known, key=FREQUENCIES.index):
        rep.err(
            "frequency_coverage is not in vocabulary order "
            "(Daily; Business daily; Weekly; Monthly; Quarterly; Semi-annual; Annual; Irregular): "
            f"{value!r}"
        )
    if len(known) != len(set(known)):
        rep.err(f"frequency_coverage repeats a value: {value!r}")
    return parts


def check_indicators(rec: dict, rep: Report) -> None:
    if is_legacy_indicators(rec):
        rep.err(
            "indicators are in the old single-cell format (strings with the unit in parentheses). "
            "The template now wants one indicators sheet per dataset with an Indicator and a "
            "Units of measure column: re-run the dataset"
        )

    rows = indicator_rows(rec)
    if not rows:
        rep.err("indicators is empty - every dataset needs its own indicators sheet")
        return

    for row in rows:
        name, unit = row["indicator"], row["unit"]
        if not name:
            rep.err(f"indicator row has no indicator name (unit {unit!r})")
            continue
        if not unit:
            rep.err(f"indicator row has no unit of measure: {name!r}")
        if "\n" in name or "\r" in name or "\n" in unit or "\r" in unit:
            rep.err(f"indicator row contains a newline: {name[:60]!r}")
        if name.count("(") != name.count(")"):
            rep.err(f"indicator name has unbalanced parentheses: {name!r}")
        if len(name) > 200:
            rep.warn(f"indicator name is {len(name)} chars - is a breakdown still folded into it? {name[:80]!r}...")
        if re.match(r"^(?:total|subtotal|memo|of which|breakdown|indicators?|unit|units)$", name, re.I):
            rep.err(f"indicator row is a heading, not a measurement: {name!r}")
        if len(unit) > 60:
            rep.warn(f"unit of measure is unusually long ({len(unit)} chars): {unit[:60]!r}")


        trailing = re.search(r"\(([^()]*)\)\s*$", name)
        if trailing:
            inside = trailing.group(1).strip()
            if unit and inside.lower() == unit.lower():
                rep.err(
                    f"indicator name repeats the unit in parentheses - the unit belongs only in the "
                    f"Units of measure column: {name!r}"
                )
            elif UNIT_LIKE.search(inside):
                rep.warn(
                    f"indicator name ends with something that reads like a unit ({inside!r}) - "
                    f"move it to the unit column unless it is part of the concept: {name!r}"
                )

        for pattern in FOLD_SMELLS:
            found = re.search(pattern, name, re.I)
            if found:
                rep.warn(
                    f"indicator {name[:70]!r} looks like a folded breakdown ({found.group(0)!r}) - "
                    "the template wants every breakdown category written out as its own row"
                )
                break

    counts = Counter((r["indicator"].lower(), r["unit"].lower()) for r in rows)
    for (name, unit), n in counts.items():
        if n > 1:
            rep.err(f"indicators repeat the same row {n} times: {name[:70]!r} ({unit})")

    unstated = sum(1 for r in rows if r["unit"].strip().lower() == "unit not stated by source")
    if unstated and unstated >= max(3, len(rows) // 2):
        rep.warn(
            f"{unstated} of {len(rows)} rows say 'unit not stated by source' - that is allowed only "
            "after reading the header block, the line under the sheet title and the footnotes; on "
            "export and balance-of-payments tables the unit is usually printed under the title"
        )

    if len(rows) < 3:
        rep.warn(f"only {len(rows)} indicator rows - check that the table was not collapsed")
    if len(rows) > 2000:
        rep.warn(
            f"{len(rows)} indicator rows - allowed, but say in the description how far the "
            "breakdown cross-product was expanded"
        )


def check_record(rec: dict, rep: Report) -> None:
    for field in FIELDS:
        if field not in rec:
            rep.err(f"missing key {field!r}")

    if "dataset_number" in rec:
        rep.warn(
            "record carries 'dataset_number' - the template no longer has that column. The "
            "dataset's own ID is column D and the name of its indicators sheet; the key is ignored"
        )
    if str(rec.get("excluded_regional_values", "")).strip():
        rep.warn(
            "record carries 'excluded_regional_values' - the template no longer has that column. "
            "Regional coverage now enumerates the regions that ARE present, so a missing region is "
            "simply absent from column B; the key is ignored"
        )

    for field in REQUIRED_NON_EMPTY:
        if not text_of(rec, field).strip():
            rep.err(f"{field} is empty but required")

    for field in FIELDS:
        value = text_of(rec, field)
        for pattern in HARD_HEDGES:
            found = re.search(pattern, value, re.I)
            if found:
                # A published table can be *called* "Main Indicators" (Bank Indonesia PSFMI table 1,
                # SSKI table 1). dataset_name must stay verbatim (field-rules F), so the hedge list
                # is not applied to it; every other field is still checked.
                if field == "dataset_name":
                    rep.warn(
                        f"dataset_name contains {found.group(0)!r} - allowed only because column F "
                        "must reproduce the source's published title verbatim"
                    )
                    continue
                rep.err(f"{field} contains the forbidden hedge {found.group(0)!r} - name the thing instead")
        for pattern in SOFT_HEDGES:
            found = re.search(pattern, value, re.I)
            if found:
                rep.warn(
                    f"{field} contains {found.group(0)!r} - legitimate only when it is the source's own "
                    "category name or marker, never as a stand-in for a list you did not finish"
                )
        for pattern in TRUNCATION:
            found = re.search(pattern, value)
            if found:
                if field == "indicators":
                    rep.err("indicators contains an ellipsis - the list must be complete, never truncated")
                else:
                    rep.warn(f"{field} contains an ellipsis")
        for bad in MOJIBAKE:
            if bad in value:
                rep.err(f"{field} contains mojibake / replacement characters ({bad!r}) - fix the source encoding")
        if field != "description" and ("\n" in value or "\r" in value):
            rep.warn(f"{field} contains a newline")

    area = text_of(rec, "reference_area")
    if area.strip():
        check_reference_area(area, rep)

    regional = text_of(rec, "regional_coverage").strip()
    if regional and regional.lower() == "none" and regional != "None":
        rep.err(f"regional_coverage must be written exactly 'None' when there is no sub-national breakdown, got {regional!r}")
    if regional and regional != "None" and "(" not in regional:
        # Template grammar, not a vocabulary: "the full list of the sub-national regions the
        # dataset covers, separated by ',', each with its level in parentheses". What the
        # levels are CALLED is the source's business - there is no closed list of them, and
        # guessing one here would be wrong for most of the world. Only the shape is checked.
        rep.err(
            "regional_coverage names no level in parentheses - the template wants the regions "
            "written out, each with its own level, as 'California (state), Texas (state)': "
            f"{regional[:90]!r}"
        )

    agency = text_of(rec, "agency").strip()
    if agency and not re.search(r"\([^)]+\)\s*$", agency) and " / " not in agency:
        rep.warn(f"agency has no acronym in parentheses: {agency!r}")

    dataset_id = text_of(rec, "dataset_id")
    if dataset_id != dataset_id.strip():
        rep.err(f"dataset_id has surrounding whitespace: {dataset_id!r}")
    if dataset_id.strip():
        # The dataset ID is the name of the dataset's indicators sheet, so Excel's limits on a
        # sheet name are limits on the ID. build_workbook.py reshapes what it must and writes
        # the reshaped form into column D; this only says so, once, per record.
        bad = sorted({ch for ch in dataset_id if ch in SHEET_NAME_BAD})
        if bad or len(dataset_id.strip()) > SHEET_NAME_MAX:
            rep.warn(
                f"dataset_id {dataset_id!r} cannot be an Excel sheet name "
                + (f"(contains {''.join(bad)})" if bad else f"({len(dataset_id.strip())} chars, max {SHEET_NAME_MAX})")
                + f" - column D and the indicators sheet will read {sheet_name(dataset_id)!r}"
            )

    desc = text_of(rec, "description").strip()
    if desc:
        words = len(desc.split())
        if words < 20:
            rep.err(f"description is {words} words - too short to state what is measured, how it is broken down, and the value status")
        elif words < 40 or words > 200:
            rep.warn(f"description is {words} words (target 40-180)")
        if "http://" in desc or "https://" in desc:
            rep.err("description contains a URL - the link belongs in dataset_url")
        for puff in ("comprehensive", "one-stop", "valuable", "rich data", "user-friendly"):
            if puff in desc.lower():
                rep.warn(f"description contains promotional wording {puff!r}")
        # Six records once shared one templated sentence with the file code substituted in:
        # "This table presents TABEL9_3 data compiled by ...". That names no measurement and
        # passes every other check.
        if dataset_id.strip() and dataset_id.strip() in desc:
            rep.err(
                f"description contains the dataset id {dataset_id.strip()!r} - the id is column D. "
                "A description that has to name it is describing the file, not the measurement"
            )

    url = text_of(rec, "dataset_url").strip()
    if url:
        if not url.startswith("https://"):
            rep.err(f"dataset_url is not https: {url!r}")
        if " " in url:
            rep.err(f"dataset_url contains a space: {url!r}")
        for smell in URL_SMELLS:
            if smell in url.lower():
                rep.err(f"dataset_url looks session- or token-bound ({smell!r}): {url!r}")

    freqs = check_frequency(text_of(rec, "frequency_coverage"), rep) if text_of(rec, "frequency_coverage").strip() else []
    if text_of(rec, "time_coverage").strip():
        check_time_coverage(text_of(rec, "time_coverage").strip(), freqs, rep)

    check_indicators(rec, rep)

    evidence = rec.get("evidence") or {}
    if not evidence:
        rep.warn("no evidence block - a reviewer cannot re-check this row without re-running the crawl")
    else:
        if evidence.get("data_read") not in ("full", "partial"):
            rep.warn("evidence.data_read should be 'full' or 'partial'")
        if evidence.get("data_read") == "partial":
            rep.warn("row is marked partial - it must be listed in the final report")
        if not evidence.get("data_urls"):
            rep.warn("evidence.data_urls is empty - was the dataset's data actually read?")
        check_observation_count(rec, evidence, rep)
        check_evidence_agrees_with_time(rec, evidence, rep)


def check_observation_count(rec: dict, evidence: dict, rep: Report) -> None:
    """An observation count that is a multiple of the row count is not a count.

    Cheap-tier workers wrote 'OBS 28' for a table of 14 indicators covering 24 years of
    monthly data - twice the row count, for every record in the batch. Every row needs at
    least one non-empty observation (rule I-14), so a count below the row count is impossible
    rather than merely suspicious.
    """
    rows = len(indicator_rows(rec))
    try:
        count = int(evidence.get("observation_count") or 0)
    except (TypeError, ValueError):
        rep.err(f"evidence.observation_count is not a number: {evidence.get('observation_count')!r}")
        return
    if not rows or not count:
        return
    if count < rows:
        rep.err(
            f"evidence.observation_count is {count} for {rows} indicator rows - every row needs at "
            "least one non-empty observation, so this is not a count of observations"
        )
        return
    if count in (rows, rows * 2, rows * 3) and rows >= 4:
        rep.warn(
            f"evidence.observation_count is {count} = {count // rows}x the {rows} indicator rows - "
            "that is the signature of a row count, not of counted observations. Use the count the "
            "drafter derived from the files"
        )


def check_evidence_agrees_with_time(rec: dict, evidence: dict, rep: Report) -> None:
    """The latest period the row claims, against the latest period its own evidence records.

    A record once said 'latest available 1989' while its own evidence.period_min_max recorded
    monthly data to 2026-07: 1989 was where the annual block stopped. The latest available
    period is the latest non-empty observation across ALL frequencies.
    """
    bounds = evidence.get("period_min_max")
    if not isinstance(bounds, dict) or not bounds:
        return
    stated = text_of(rec, "time_coverage").strip()
    m = LATEST_RE.search(stated) or TO_PERIOD_RE.match(stated)
    if not m:
        return
    claimed = m.group(1)
    claimed_key = period_key(claimed)

    latest = None
    for pair in bounds.values():
        if isinstance(pair, (list, tuple)) and len(pair) == 2 and pair[1]:
            key = period_key(pair[1])
            if key[0] and proves_later(key, claimed_key) and (latest is None or key > latest[0]):
                latest = (key, str(pair[1]))
    if latest is not None:
        rep.err(
            f"time_coverage says the latest available period is {claimed!r}, but this record's own "
            f"evidence.period_min_max goes to {latest[1]!r}. The latest available period is the "
            "latest non-empty observation across every frequency; a frequency that ends earlier "
            "goes in the trailing note"
        )


def iter_inputs(path: str):
    """Yield (context, record_or_error) for a .jsonl file, a single-record .json file,
    or a directory of single-record .json files (what one dataset worker writes)."""
    if os.path.isdir(path):
        for name in sorted(os.listdir(path)):
            if not name.endswith(".json"):
                continue
            full = os.path.join(path, name)
            try:
                with open(full, "r", encoding="utf-8") as fh:
                    data = json.load(fh)
            except json.JSONDecodeError as exc:
                yield name, exc
                continue
            for rec in data if isinstance(data, list) else [data]:
                yield name, rec
        return

    if path.endswith(".json"):
        try:
            with open(path, "r", encoding="utf-8") as fh:
                data = json.load(fh)
        except json.JSONDecodeError as exc:
            yield os.path.basename(path), exc
            return
        for rec in data if isinstance(data, list) else [data]:
            yield os.path.basename(path), rec
        return

    with open(path, "r", encoding="utf-8") as fh:
        for lineno, line in enumerate(fh, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                yield f"line {lineno}", json.loads(line)
            except json.JSONDecodeError as exc:
                yield f"line {lineno}", exc


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("records", help="datasets.jsonl, a single record .json, or a directory of record .json files")
    ap.add_argument("--strict", action="store_true", help="treat warnings as failures")
    ap.add_argument("--quiet", action="store_true", help="print only the summary")
    args = ap.parse_args()

    rep = Report()
    ids: Counter[str] = Counter()
    urls: Counter[str] = Counter()
    sheets: dict[str, list[str]] = {}
    openings: dict[str, list[str]] = {}
    n = 0

    for where, item in iter_inputs(args.records):
        if isinstance(item, json.JSONDecodeError):
            rep.ctx = where
            rep.err(f"not valid JSON: {item}")
            continue
        rec = item
        n += 1
        dataset_id = str(rec.get("dataset_id", ""))
        rep.ctx = f"{where} [{rec.get('dataset_id', '?')}]"
        check_record(rec, rep)

        # A record under a non-canonical file name is invisible to every tool that looks it up
        # by name. Several workers once wrote '4926ec.json' instead of 'TABEL5_5-4926ec.json',
        # and a retirement pass reported 10 records as "not written yet" while they sat on disk.
        if where.endswith(".json") and dataset_id.strip():
            want = safe_id(dataset_id) + ".json"
            if where != want:
                rep.warn(
                    f"record file is named {where!r} but the canonical name for this dataset is "
                    f"{want!r} - rename it, and match records on the dataset_id inside the file"
                )

        ids[dataset_id] += 1
        urls[str(rec.get("dataset_url", ""))] += 1
        if dataset_id.strip():
            sheets.setdefault(sheet_name(dataset_id).lower(), []).append(dataset_id)
        opening = " ".join(str(rec.get("description", "")).split())[:60].lower()
        if opening:
            openings.setdefault(opening, []).append(dataset_id or where)

    rep.ctx = "workbook"
    for key, count in ids.items():
        if count > 1:
            # The template: "Dataset ID must be unique across Agency". The check is
            # workbook-wide, which also covers it: the ID names a sheet, and sheet names are
            # unique across the whole workbook whatever agency the row belongs to.
            rep.err(f"dataset_id {key!r} appears in {count} rows - the template requires a Dataset ID "
                    "unique across the agency, and one record per dataset")
    for key, count in urls.items():
        if key and count > 1:
            rep.warn(f"dataset_url {key!r} is reused by {count} rows - check the dataset granularity")
    for name, owners in sheets.items():
        distinct = sorted(set(owners))
        if len(distinct) > 1:
            rep.warn(
                f"{len(distinct)} dataset ids reduce to the same indicators-sheet name {name!r} "
                f"({', '.join(distinct[:5])}) - build_workbook.py will disambiguate them with "
                "'~2', '~3', so column D will not read exactly like the source's id"
            )
    # Grouping descriptions by their opening is how six content-free templated descriptions
    # were found on a real run; ten other clusters shared an opening but diverged immediately,
    # so this is a warning to read, not an error.
    for opening, owners in openings.items():
        distinct = sorted(set(owners))
        if len(distinct) > 2:
            rep.warn(
                f"{len(distinct)} descriptions open with the same 60 characters "
                f"({', '.join(distinct[:6])}{' ...' if len(distinct) > 6 else ''}) - check that each "
                f"one states what its own dataset measures: {opening!r}"
            )

    if not args.quiet:
        for line in rep.errors:
            print(line)
        for line in rep.warnings:
            print(line)

    print(f"\n{n} records, {len(rep.errors)} errors, {len(rep.warnings)} warnings")
    if rep.errors:
        return 1
    if args.strict and rep.warnings:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
