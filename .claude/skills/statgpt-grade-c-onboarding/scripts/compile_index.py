#!/usr/bin/env python3
"""Compile per-dataset record files into datasets.jsonl, and optionally into the workbook.

This is the flush point of a fan-out run: every dataset worker writes one small JSON file
under <workdir>/records/, and this script turns whatever exists right now into a deliverable.
It is safe to run at any moment, as often as you like - nothing here needs the crawl to be
finished, and nothing is lost if the run is interrupted.

Usage:
    python compile_index.py work/                          # merge + progress report
    python compile_index.py work/ --status                  # progress report only, no writing
    python compile_index.py work/ --out index.xlsx          # merge, validate, build the workbook
    python compile_index.py work/ --out index.xlsx --skip-validation

Reads:
    <workdir>/catalog.json     the enumerated dataset list (for order and for what is missing)
    <workdir>/records/*.json   one finished record per dataset
    <workdir>/blocked/*.json   datasets that produced no row, each with a reason

Writes:
    <workdir>/datasets.jsonl   catalog order, records only
    <workdir>/progress.md      a short, human-readable state of the run
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from _gradec import FIELD_ORDER, indicator_count, is_legacy_indicators, load_catalog, load_dir  # noqa: E402


def ordered(records: list[tuple[str, dict]], catalog: list[dict]) -> tuple[list[dict], list[str]]:
    by_id: dict[str, dict] = {}
    dupes: list[str] = []
    for name, rec in records:
        key = str(rec.get("dataset_id", "")).strip() or f"__file__{name}"
        if key in by_id:
            dupes.append(key)
        by_id[key] = rec
    out = []
    seen = set()
    for entry in catalog:
        key = str(entry.get("dataset_id", "")).strip()
        if key and key in by_id:
            out.append(by_id[key])
            seen.add(key)
    for key, rec in by_id.items():
        if key not in seen:
            out.append(rec)
    return out, dupes


def tidy(rec: dict) -> dict:
    out = {k: rec[k] for k in FIELD_ORDER if k in rec}
    for k, v in rec.items():
        if k not in out:
            out[k] = v
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("workdir")
    ap.add_argument("--out", help="also validate and build this .xlsx")
    ap.add_argument("--status", action="store_true", help="report progress without writing anything")
    ap.add_argument("--skip-validation", action="store_true")
    ap.add_argument("--strict", action="store_true")
    ap.add_argument("--template", help="passed through to build_workbook.py")
    args = ap.parse_args()

    workdir = args.workdir
    if not os.path.isdir(workdir):
        raise SystemExit(f"no such work directory: {workdir}")

    catalog = load_catalog(workdir)
    records = load_dir(os.path.join(workdir, "records"))
    blocked = load_dir(os.path.join(workdir, "blocked"))

    rows, dupes = ordered(records, catalog)
    have = {str(r.get("dataset_id", "")).strip() for r in rows}
    blocked_ids = {str(r.get("dataset_id", "")).strip() for _, r in blocked}
    missing = [
        str(e.get("dataset_id", "")).strip()
        for e in catalog
        if str(e.get("dataset_id", "")).strip() and str(e.get("dataset_id", "")).strip() not in have
        and str(e.get("dataset_id", "")).strip() not in blocked_ids
    ]
    partial = [
        str(r.get("dataset_id", "")) for r in rows if (r.get("evidence") or {}).get("data_read") == "partial"
    ]
    indicator_total = sum(indicator_count(r) for r in rows)
    thin = [str(r.get("dataset_id", "")) for r in rows if indicator_count(r) < 3]
    legacy = [str(r.get("dataset_id", "")) for r in rows if is_legacy_indicators(r)]

    lines = [
        "# Run progress",
        "",
        f"- catalog datasets: {len(catalog)}",
        f"- records written:  {len(rows)}",
        f"- blocked:          {len(blocked)}",
        f"- still to do:      {len(missing)}",
        f"- marked partial:   {len(partial)}",
        f"- indicator rows:   {indicator_total}"
        + (f" (mean {indicator_total / len(rows):.1f} per dataset)" if rows else ""),
    ]
    if legacy:
        lines.append(
            f"- records still in the old single-cell indicator format: {len(legacy)} -> "
            f"{', '.join(legacy[:10])} (re-run those datasets)"
        )
    if thin:
        lines.append(f"- rows with fewer than 3 indicators (check for collapsing): {len(thin)} -> {', '.join(thin[:15])}")
    if dupes:
        lines.append(f"- duplicate dataset ids among record files: {', '.join(sorted(set(dupes))[:15])}")
    if partial:
        lines.append(f"- partial: {', '.join(partial[:15])}" + (" ..." if len(partial) > 15 else ""))
    if blocked:
        lines.append(
            "- blocked: "
            + ", ".join(f"{r.get('dataset_id', '?')} ({str(r.get('reason', ''))[:40]})" for _, r in blocked[:10])
        )
    if missing:
        lines.append(f"- next up: {', '.join(missing[:25])}" + (" ..." if len(missing) > 25 else ""))

    report = "\n".join(lines)
    print(report)

    if args.status:
        return 0

    with open(os.path.join(workdir, "progress.md"), "w", encoding="utf-8", newline="\n") as fh:
        fh.write(report + "\n")

    jsonl = os.path.join(workdir, "datasets.jsonl")
    with open(jsonl, "w", encoding="utf-8", newline="\n") as fh:
        for rec in rows:
            fh.write(json.dumps(tidy(rec), ensure_ascii=False) + "\n")
    print(f"\nWrote {jsonl} ({len(rows)} records)")

    if not args.out:
        return 0

    cmd = [sys.executable, os.path.join(HERE, "build_workbook.py"), jsonl, "--out", args.out]
    if args.template:
        cmd += ["--template", args.template]
    if args.skip_validation:
        cmd.append("--skip-validation")
    if args.strict:
        cmd.append("--strict")
    print()
    return subprocess.call(cmd)


if __name__ == "__main__":
    sys.exit(main())
