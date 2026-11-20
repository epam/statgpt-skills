#!/usr/bin/env python3
"""Audit one field at a time across EVERY record, and cross-check records against the drafts.

Run this before delivering. `validate_records.py` checks the SHAPE of a record: required keys
present, no duplicate rows, no banned hedge words, a unit on every indicator. That is
necessary and nowhere near sufficient. A record can be perfectly well-formed and still say
that an interest rate is measured in billions of rupiah, that a series starts in 1905, or that
a row is called "laos, laos, malaysia".

On a real 109-dataset run, twenty-five defects reached the records. The validator caught
three. Nine were caught by exactly what this script does - tallying one field across the whole
corpus rather than reading records one at a time - because a wrong value that looks plausible
in a single record is obvious when it is 479 rows, or when 105 records in a row say "None":

  unit                  479 rows said "unit not stated by source" on tables whose unit is
                        printed under the sheet title; 149 more carried the source's own
                        language; 71 interest-rate rows were denominated in currency
  regional_coverage     every one of 105 records said "None" on a portal with four
                        "by Provinces" tables
  description           six records shared one templated sentence with the file code
                        substituted in, naming no measurement at all
  time_coverage         two records stated a latest period earlier than their own evidence

The other lever is the draft. `draft_records.py` derived frequency, period bounds, observation
count and a candidate row list from the files by script, so it is a second opinion that costs
nothing to consult. Comparing records against it catches fabricated evidence and
under-supplied indicator lists immediately.

Usage:
    python audit_corpus.py work/                     # every section of the audit
    python audit_corpus.py work/ --only units        # units | regions | descriptions | time | drafts | names
    python audit_corpus.py work/ --top 40            # how many distinct values to print per tally
    python audit_corpus.py work/ --words id,dan,dalam,jumlah     # flag records containing these words

Nothing is modified. Every finding is a dataset id you can hand to next_batch.py or
a re-run (move their record files aside, see SKILL.md Step 4b).
"""

from __future__ import annotations

import argparse
import collections
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _gradec import indicator_rows, load_dir, safe_id  # noqa: E402

SECTIONS = ["units", "regions", "descriptions", "time", "drafts", "names"]

RATE_RE = re.compile(
    r"\b(interest rate|discount rate|policy rate|lending rate|deposit rate|yield|rate of return"
    r"|inflation|index|share|ratio|proportion|percentage|growth|exchange rate)\b", re.I)
MONEY_RE = re.compile(
    r"^(billions?|millions?|thousands?|trillions?) of |^(Rp|USD|EUR|IDR)\b|\b(rupiah|dollars?|euros?|yen)\b",
    re.I)


def load_records(workdir: str) -> list[tuple[str, dict]]:
    records = load_dir(os.path.join(workdir, "records"))
    if not records:
        raise SystemExit(f"no records in {os.path.join(workdir, 'records')}")
    return records


def period_key(period: str) -> tuple[int, int, int, int]:
    """(year, month-of-year, day, granularity rank). Rank matters: a coarser stamp never
    proves a later period, because an annual '2026' stands for a year still in progress and
    is not evidence that data runs past '2026-Q2'."""
    body = str(period).strip()
    for pattern, parts in (
        (r"^(\d{4})$", lambda m: (int(m.group(1)), 12, 31, 0)),
        (r"^(\d{4})-H([1-2])$", lambda m: (int(m.group(1)), int(m.group(2)) * 6, 31, 1)),
        (r"^(\d{4})-Q([1-4])$", lambda m: (int(m.group(1)), int(m.group(2)) * 3, 31, 2)),
        (r"^(\d{4})-(\d{2})$", lambda m: (int(m.group(1)), int(m.group(2)), 31, 3)),
        (r"^(\d{4})-(\d{2})-(\d{2})$", lambda m: (int(m.group(1)), int(m.group(2)), int(m.group(3)), 4)),
    ):
        m = re.match(pattern, body)
        if m:
            return parts(m)
    return (0, 0, 0, 0)


def proves_later(evidence: tuple, claimed: tuple) -> bool:
    if evidence[0] > claimed[0]:
        return True
    if evidence[0] < claimed[0]:
        return False
    return evidence[3] >= claimed[3] and evidence[:3] > claimed[:3]


def header(title: str) -> None:
    print()
    print("=" * 78)
    print(title)
    print("=" * 78)


def tally(title: str, pairs: list[tuple[str, str]], top: int) -> None:
    """Print a value -> count tally with the datasets each value came from."""
    counts: collections.Counter[str] = collections.Counter()
    owners: dict[str, set[str]] = {}
    for dataset_id, value in pairs:
        counts[value] += 1
        owners.setdefault(value, set()).add(dataset_id)
    print(f"\n{title}: {len(counts)} distinct values over {sum(counts.values())} rows")
    for value, count in counts.most_common(top):
        who = sorted(owners[value])
        shown = ", ".join(who[:4]) + (f" +{len(who) - 4}" if len(who) > 4 else "")
        print(f"  {count:6d}  {value[:58]:58s}  {shown}")
    if len(counts) > top:
        print(f"  ... {len(counts) - top} more distinct values (raise --top to see them)")


def audit_units(records, top, words) -> None:
    header("UNITS - every distinct unit in the corpus, most frequent first")
    print("Read this list top to bottom. A unit that is not English, is not a unit, or is the")
    print("wrong KIND of unit for its indicator is obvious here and invisible one record at a time.")
    pairs = [(str(r.get("dataset_id", "?")), row["unit"]) for _, r in records for row in indicator_rows(r)]
    tally("unit", pairs, top)

    unstated: list[tuple[str, int, int]] = []
    mismatched: list[tuple[str, str, str]] = []
    flagged_words: list[tuple[str, str, str]] = []
    for _, rec in records:
        dataset_id = str(rec.get("dataset_id", "?"))
        rows = indicator_rows(rec)
        n = sum(1 for row in rows if row["unit"].strip().lower() == "unit not stated by source")
        if n:
            unstated.append((dataset_id, n, len(rows)))
        for row in rows:
            if RATE_RE.search(row["indicator"]) and MONEY_RE.match(row["unit"].strip()):
                mismatched.append((dataset_id, row["indicator"], row["unit"]))
            for word in words:
                if re.search(r"\b" + re.escape(word) + r"\b", row["unit"], re.I):
                    flagged_words.append((dataset_id, row["unit"], word))

    if unstated:
        total = sum(n for _, n, _ in unstated)
        print(f"\n'unit not stated by source' on {total} rows in {len(unstated)} datasets:")
        for dataset_id, n, rows in sorted(unstated, key=lambda x: -x[1])[:20]:
            print(f"  {dataset_id:20s} {n:4d} of {rows} rows")
        print("  The unit is usually printed in the line under the sheet title - '(Thousands of USD)',")
        print("  '(Millions of USD)', '(Thousands of Ton)'. Check those files before accepting this.")
    if mismatched:
        print(f"\nPOSSIBLE rate or index measured in an amount of money - {len(mismatched)} rows:")
        for dataset_id, name, unit in mismatched[:20]:
            print(f"  {dataset_id:20s} {name[:50]:50s} {unit}")
        print("  A guess from English keywords in the name, so read it rather than trusting it -")
        print("  'stock index turnover' legitimately is an amount of money. Where it is right, an")
        print("  interest rate is not a quantity of currency: re-run those on the strong tier.")
    if flagged_words:
        print(f"\nUnits containing a flagged word ({', '.join(words)}) - {len(flagged_words)} rows:")
        seen: set[tuple[str, str]] = set()
        for dataset_id, unit, word in flagged_words:
            if (dataset_id, unit) in seen:
                continue
            seen.add((dataset_id, unit))
            print(f"  {dataset_id:20s} {unit[:50]:50s} (matched {word!r})")


def audit_regions(records, top, words) -> None:
    header("REGIONAL COVERAGE - the tally that exposed 105 records all saying 'None'")
    pairs = [(str(r.get("dataset_id", "?")), str(r.get("regional_coverage", "")).strip()) for _, r in records]
    tally("regional_coverage", pairs, top)

    none_count = sum(1 for _, v in pairs if v == "None")
    print(f"\n{none_count} of {len(pairs)} records say 'None'.")
    if len(pairs) > 20 and none_count >= 0.9 * len(pairs):
        print("  That is almost every record. On a portal of this size it is worth disbelieving:")
        print("  go and look at whether any dataset's indicator ROWS are regions rather than line")
        print("  items - such a dataset is regional whatever its title says. This is exactly how")
        print("  four 'by Provinces' tables were caught reporting 'None' on a real run: by reading")
        print("  the proportion above, not by any rule about what a region is called.")

    # Deliberately no guess at what a sub-national level is CALLED. There is no closed list of
    # level names across the world's statistical systems, so a vocabulary here would be wrong
    # for most of them - and a check that is wrong in unpredictable places is worse than the
    # tally above, which a reader can act on without being told what to look for.

    # The new template dropped the 'excluded regional values' column; a leftover is dead weight.
    leftover = [str(r.get("dataset_id", "?")) for _, r in records if str(r.get("excluded_regional_values", "")).strip()]
    if leftover:
        print(f"\n{len(leftover)} records still carry 'excluded_regional_values', a column the")
        print(f"  template no longer has: {', '.join(leftover[:10])}")


def audit_descriptions(records, top, words) -> None:
    header("DESCRIPTIONS - grouped by their opening, which is how templated ones surface")
    openings: dict[str, list[str]] = {}
    for _, rec in records:
        dataset_id = str(rec.get("dataset_id", "?"))
        opening = " ".join(str(rec.get("description", "")).split())[:60]
        openings.setdefault(opening, []).append(dataset_id)

    clusters = sorted(((k, v) for k, v in openings.items() if len(v) > 1), key=lambda x: -len(x[1]))
    if clusters:
        print(f"\n{len(clusters)} groups of records share their first 60 characters:")
        for opening, owners in clusters[:top]:
            print(f"  {len(owners):3d}x  {opening!r}")
            print(f"        {', '.join(sorted(owners)[:8])}")
        print("\n  Sharing an opening is fine when the next clause states the distinguishing fact")
        print("  (rupiah vs foreign currency, production vs expenditure side). It is NOT fine when")
        print("  the description names no measurement - six records once read 'This table presents")
        print("  <FILE CODE> data compiled by <agency> from official sources', which told a search")
        print("  layer nothing and made inflation, exports and policy rates indistinguishable.")
    else:
        print("\nNo two descriptions share an opening.")

    short: list[tuple[str, int]] = []
    self_naming: list[str] = []
    for _, rec in records:
        dataset_id = str(rec.get("dataset_id", "?"))
        desc = str(rec.get("description", "")).strip()
        n = len(desc.split())
        if n < 40:
            short.append((dataset_id, n))
        if dataset_id and dataset_id in desc:
            self_naming.append(dataset_id)
    if short:
        print(f"\n{len(short)} descriptions under the 40-word floor:")
        for dataset_id, n in sorted(short, key=lambda x: x[1])[:20]:
            print(f"  {dataset_id:20s} {n} words")
    if self_naming:
        print(f"\n{len(self_naming)} descriptions contain their own dataset id, which is column D,")
        print(f"  not a fact about the data: {', '.join(self_naming[:10])}")


def audit_time(records, top, words) -> None:
    header("TIME AND FREQUENCY - each record against its own evidence")
    pairs = [(str(r.get("dataset_id", "?")), str(r.get("frequency_coverage", "")).strip()) for _, r in records]
    tally("frequency_coverage", pairs, top)

    both = [d for d, v in pairs if "Monthly" in v and "Quarterly" in v]
    if both:
        print(f"\n{len(both)} records claim BOTH Monthly and Quarterly: {', '.join(both[:12])}")
        print("  Sometimes true. Often it is quarter columns written as the quarter's last month")
        print("  (2004-03, 2004-06, 2004-09, 2004-12), read as a monthly series missing nine")
        print("  months a year. Check the header of one sheet before accepting it.")

    contradictions = []
    early_starts = []
    for _, rec in records:
        dataset_id = str(rec.get("dataset_id", "?"))
        stated = str(rec.get("time_coverage", ""))
        bounds = (rec.get("evidence") or {}).get("period_min_max") or {}
        if not isinstance(bounds, dict):
            continue
        starts = [(period_key(v[0]), str(v[0])) for v in bounds.values()
                  if isinstance(v, (list, tuple)) and len(v) == 2 and v[0]]
        m = re.search(r"latest available (\d{4}(?:-(?:Q[1-4]|H[1-2]|\d{2}(?:-\d{2})?))?)", stated)
        if m:
            claimed = period_key(m.group(1))
            later = [str(v[1]) for v in bounds.values()
                     if isinstance(v, (list, tuple)) and len(v) == 2 and v[1]
                     and proves_later(period_key(v[1]), claimed)]
            if later:
                contradictions.append((dataset_id, m.group(1), max(later, key=period_key)))
        for key, value in starts:
            if (0, 0, 0) < key < (1900, 0, 0) or (key[0] and key[0] < 1900):
                early_starts.append((dataset_id, value))

    if contradictions:
        print(f"\n{len(contradictions)} records state a latest period EARLIER than their own evidence:")
        for dataset_id, claimed, actual in contradictions[:20]:
            print(f"  {dataset_id:20s} says {claimed:10s} but evidence goes to {actual}")
        print("  The latest available period is the latest non-empty observation across ALL")
        print("  frequencies; a frequency that ends earlier goes in the trailing note.")
    if early_starts:
        print(f"\n{len(early_starts)} period bounds start before 1900 - almost certainly a date")
        print("  conversion defect, not a real span (a year header stored as a date serial reads")
        print("  as 1905). Reconvert the .xls (references/sources.md section 5), rebuild the drafts, re-run these:")
        for dataset_id, value in early_starts[:20]:
            print(f"  {dataset_id:20s} {value}")


def audit_names(records, top, words) -> None:
    header("INDICATOR NAMES - the checks the validator cannot make")
    repeated_token: list[tuple[str, str]] = []
    flagged_words: list[tuple[str, str, str]] = []
    for _, rec in records:
        dataset_id = str(rec.get("dataset_id", "?"))
        for row in indicator_rows(rec):
            name = row["indicator"]
            # 'laos, laos, malaysia' - a name qualified with a SIBLING rather than a parent.
            # Unique, unit-carrying, hedge-free: the validator is happy with every one of these.
            parts = [p.strip().lower() for p in name.split(",") if p.strip()]
            if len(parts) != len(set(parts)):
                repeated_token.append((dataset_id, name))
            for word in words:
                if re.search(r"\b" + re.escape(word) + r"\b", name, re.I):
                    flagged_words.append((dataset_id, name, word))

    if repeated_token:
        print(f"\n{len(repeated_token)} indicator names repeat a comma-separated token:")
        for dataset_id, name in repeated_token[:20]:
            print(f"  {dataset_id:20s} {name[:70]}")
        print("  This is the signature of a name qualified with its SIBLING instead of its parent.")
        print("  Re-run those datasets; the draft flags such rows 'still_ambiguous'.")
    else:
        print("\nNo indicator name repeats a comma-separated token.")

    if flagged_words:
        print(f"\n{len(flagged_words)} indicator names contain a flagged word ({', '.join(words)}):")
        for dataset_id, name, word in flagged_words[:25]:
            print(f"  {dataset_id:20s} {name[:60]:60s} (matched {word!r})")
        print("  Pass --words with the source language's most common stopwords to find rows")
        print("  where the sheet had no English repeat and the local label was copied through.")
    elif words:
        print(f"\nNo indicator name contains any of: {', '.join(words)}")

    long_names = [(str(r.get("dataset_id", "?")), row["indicator"])
                  for _, r in records for row in indicator_rows(r) if len(row["indicator"]) > 120]
    if long_names:
        print(f"\n{len(long_names)} indicator names are over 120 characters - usually a fold that")
        print("  was not written out:")
        for dataset_id, name in long_names[:10]:
            print(f"  {dataset_id:20s} {name[:90]}...")


def audit_drafts(records, top, words, workdir="") -> None:
    header("RECORDS vs DRAFTS - the second opinion that costs nothing")
    print("The draft was derived from the files by a script, so a record that disagrees with it")
    print("about how many observations exist, or how many rows the table has, is making a claim")
    print("nobody measured.")
    rows_out = []
    missing = 0
    for _, rec in records:
        dataset_id = str(rec.get("dataset_id", ""))
        path = os.path.join(workdir, "drafts", safe_id(dataset_id) + ".json")
        if not os.path.exists(path):
            missing += 1
            continue
        with open(path, "r", encoding="utf-8") as fh:
            draft = json.load(fh)
        # A portal-specific drafter may merge its output under its own key; prefer it.
        for key in list(draft.keys()):
            if isinstance(draft.get(key), dict) and "candidate_indicators" in draft[key]:
                draft = draft[key]
                break
        evidence = rec.get("evidence") or {}
        record_obs = int(evidence.get("observation_count") or 0)
        draft_obs = int(draft.get("observation_count") or 0)
        rows_out.append({
            "id": dataset_id,
            "rec_rows": len(indicator_rows(rec)),
            "draft_rows": len(draft.get("candidate_indicators") or []),
            "rec_obs": record_obs,
            "draft_obs": draft_obs,
            "ratio": (record_obs / draft_obs) if draft_obs else 0.0,
            "rec_freq": str(rec.get("frequency_coverage", "")).strip(),
            "draft_freq": str(draft.get("frequency_coverage", "")).strip(),
        })

    if not rows_out:
        print(f"\nNo drafts found under {os.path.join(workdir, 'drafts')} - nothing to compare.")
        return

    print(f"\n{'dataset':22s} {'rec':>5s} {'draft':>5s} {'rec_obs':>9s} {'draft_obs':>10s} {'ratio':>6s}  frequency")
    bad_obs, bad_freq, thin = [], [], []
    for row in rows_out:
        flags = ""
        if row["draft_obs"] and not 0.5 <= row["ratio"] <= 2.0:
            flags += " OBS?"
            bad_obs.append(row["id"])
        if row["draft_freq"] and row["rec_freq"] != row["draft_freq"]:
            flags += " FREQ?"
            bad_freq.append(row["id"])
        if row["draft_rows"] and row["rec_rows"] < 0.6 * row["draft_rows"]:
            flags += " THIN?"
            thin.append(row["id"])
        if flags:
            print(f"{row['id'][:22]:22s} {row['rec_rows']:5d} {row['draft_rows']:5d} "
                  f"{row['rec_obs']:9d} {row['draft_obs']:10d} {row['ratio']:6.2f}  "
                  f"{row['rec_freq']} | {row['draft_freq']}{flags}")

    print(f"\n{len(rows_out)} records compared, {missing} with no draft on disk.")
    print(f"  observation count implausible vs the draft: {len(bad_obs)}"
          + (f" -> {', '.join(bad_obs[:15])}" if bad_obs else ""))
    print(f"  frequency disagrees with the draft:         {len(bad_freq)}"
          + (f" -> {', '.join(bad_freq[:15])}" if bad_freq else ""))
    print(f"  far fewer rows than the draft found:        {len(thin)}"
          + (f" -> {', '.join(thin[:15])}" if thin else ""))
    if bad_obs or bad_freq or thin:
        print("\n  Where the draft is right, re-run the record - do not patch it by hand. Where the")
        print("  DRAFT is wrong, fix draft_records.py and rebuild: a drafter defect is wrong")
        print("  identically on every dataset, which is the whole reason it is worth fixing there.")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("workdir")
    ap.add_argument("--only", action="append", choices=SECTIONS,
                    help="run only these sections (default: all)")
    ap.add_argument("--top", type=int, default=25, help="distinct values to print per tally (default 25)")
    ap.add_argument("--words", default="",
                    help="comma-separated words to flag inside names and units - use the source "
                         "language's commonest stopwords to find untranslated rows")
    args = ap.parse_args()

    if not os.path.isdir(args.workdir):
        raise SystemExit(f"no such work directory: {args.workdir}")
    records = load_records(args.workdir)
    words = [w.strip() for w in args.words.split(",") if w.strip()]
    wanted = args.only or SECTIONS

    print(f"Auditing {len(records)} records in {args.workdir}")
    if not words:
        print("Tip: --words dan,dalam,jumlah,lainnya finds rows left in the source's own language.")

    for section in SECTIONS:
        if section not in wanted:
            continue
        if section == "units":
            audit_units(records, args.top, words)
        elif section == "regions":
            audit_regions(records, args.top, words)
        elif section == "descriptions":
            audit_descriptions(records, args.top, words)
        elif section == "time":
            audit_time(records, args.top, words)
        elif section == "names":
            audit_names(records, args.top, words)
        elif section == "drafts":
            audit_drafts(records, args.top, words, args.workdir)

    print("\nNothing was modified. Move the records of the dataset ids above aside and re-run them.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
