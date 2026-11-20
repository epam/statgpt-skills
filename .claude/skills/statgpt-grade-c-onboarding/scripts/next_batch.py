#!/usr/bin/env python3
"""Print the next wave of datasets to hand to dataset workers.

It reads the catalogue and the records already on disk, and prints only what is still
pending - with the record file name each worker must write. Never invent that name: it
carries a hash of the exact dataset id so that two ids differing only in case (both kept
verbatim, as the field rules require) cannot land on the same file on Windows or macOS.

Usage:
    python next_batch.py work/                            # next 30 pending datasets, one line each
    python next_batch.py work/ --size 40 --batch-size 10  # 4 worker blocks of 10 datasets
    python next_batch.py work/ --size 4
    python next_batch.py work/ --section SEKI
    python next_batch.py work/ --retry            # only datasets marked partial
    python next_batch.py work/ --json             # machine-readable
    python next_batch.py work/ --thin             # rows with fewer than 3 indicators, to redo

Output is one tab-separated line per dataset:
    safe_id <TAB> dataset_id <TAB> section <TAB> url <TAB> title
"""

from __future__ import annotations

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _gradec import entry_id, indicator_count, load_catalog, load_dir, safe_id  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("workdir")
    ap.add_argument("--size", type=int, default=30, help="how many datasets to print (default 30)")
    ap.add_argument("--batch-size", type=int, default=1,
                    help="datasets per worker (default 1); with more than 1, the output is grouped "
                         "into one block per worker, taken from the same catalogue section")
    ap.add_argument("--section", help="only datasets from this catalogue section")
    ap.add_argument("--retry", action="store_true", help="datasets whose record is marked partial")
    ap.add_argument("--thin", action="store_true", help="datasets whose record has fewer than 3 indicators")
    ap.add_argument("--all", action="store_true", help="ignore --size and print every match")
    ap.add_argument("--json", action="store_true", help="print JSON instead of TSV")
    args = ap.parse_args()

    catalog = load_catalog(args.workdir)
    if not catalog:
        raise SystemExit(f"no usable {os.path.join(args.workdir, 'catalog.json')} - merge the work/catalog/ fragments into it first (SKILL.md Step 2)")

    records = {str(r.get("dataset_id", "")).strip(): r for _, r in load_dir(os.path.join(args.workdir, "records"))}
    blocked = {str(r.get("dataset_id", "")).strip() for _, r in load_dir(os.path.join(args.workdir, "blocked"))}

    pending = []
    for entry in catalog:
        ds_id = entry_id(entry)
        if not ds_id:
            continue
        if args.section and str(entry.get("section", "")) != args.section:
            continue
        rec = records.get(ds_id)
        if args.retry:
            take = rec is not None and (rec.get("evidence") or {}).get("data_read") == "partial"
        elif args.thin:
            take = rec is not None and indicator_count(rec) < 3
        else:
            take = rec is None and ds_id not in blocked
        if take:
            pending.append(entry)

    total = len([e for e in catalog if entry_id(e)])
    selected = pending if args.all else pending[: args.size]

    if args.json:
        print(json.dumps(
            [
                {
                    "safe_id": safe_id(entry_id(e)),
                    "dataset_id": entry_id(e),
                    "section": e.get("section", ""),
                    "url": e.get("url", "") or e.get("dataset_url", ""),
                    "title": e.get("title", "") or e.get("dataset_name", ""),
                    "structure_ref": e.get("structure_ref", ""),
                    "notes": e.get("notes", ""),
                }
                for e in selected
            ],
            ensure_ascii=False,
            indent=1,
        ))
        return 0

    mode = "partial to retry" if args.retry else ("thin to redo" if args.thin else "pending")
    print(f"# {len(pending)} {mode} of {total} catalogue datasets; "
          f"{len(records)} records on disk, {len(blocked)} blocked. Showing {len(selected)}.")

    def line(entry: dict) -> str:
        ds_id = entry_id(entry)
        url = entry.get("url", "") or entry.get("dataset_url", "")
        title = (entry.get("title", "") or entry.get("dataset_name", ""))[:90]
        return f"{safe_id(ds_id)}\t{ds_id}\t{entry.get('section', '')}\t{url}\t{title}"

    if args.batch_size > 1:
        # One worker per batch. Datasets are grouped by section first, so a batch usually
        # shares one download, one structure and one set of conventions; batches are then
        # filled to size, so a section's remainder rides along instead of paying a whole
        # worker's fixed cost for one dataset.
        ordered_sel = sorted(selected, key=lambda e: str(e.get("section", "")))
        batch = 0
        for start in range(0, len(ordered_sel), args.batch_size):
            batch += 1
            chunk = ordered_sel[start : start + args.batch_size]
            sections = sorted({str(e.get("section", "")) or "(none)" for e in chunk})
            print(f"\n# batch {batch} - {len(chunk)} datasets - section(s): {', '.join(sections)}")
            print("# safe_id\tdataset_id\tsection\turl\ttitle")
            for entry in chunk:
                print(line(entry))
        print(f"\n# {batch} workers for {len(selected)} datasets")
    else:
        print("# safe_id\tdataset_id\tsection\turl\ttitle")
        for entry in selected:
            print(line(entry))
    if not selected and not args.retry and not args.thin:
        print("# nothing pending - every catalogue dataset has a record or is blocked")
    return 0


if __name__ == "__main__":
    sys.exit(main())
