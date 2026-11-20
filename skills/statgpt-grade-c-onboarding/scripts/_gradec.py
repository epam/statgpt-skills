"""Shared helpers for the Grade C index scripts."""

from __future__ import annotations

import hashlib
import json
import os
import re
import sys

# Datasets tab, columns A-I, in order. There is no dataset number: the dataset's own ID
# (column D) is both the row's identity and the name of its indicators sheet, so the two
# cannot drift apart the way a positional number could.
FIELD_ORDER = [
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
    "evidence",
]

DATASET_COLUMNS = [
    "reference_area",
    "regional_coverage",
    "agency",
    "dataset_id",
    "dataset_name",
    "description",
    "dataset_url",
    "time_coverage",
    "frequency_coverage",
]

DATASET_HEADERS = [
    "Reference area / country",
    "Regional coverage",
    "Agency / organization",
    "Dataset ID",
    "Dataset name",
    "Description",
    "Dataset URL",
    "Time coverage",
    "Frequency coverage",
]

INDICATOR_HEADERS = ["Indicator", "Units of measure"]


def safe_id(dataset_id: str) -> str:
    """File-name form of a dataset id: sanitized stem + a hash of the exact id.

    The hash is not decoration. Dataset ids are kept verbatim and case-sensitively
    (field-rules D), so a portal can publish both 'TABEL_1' and 'Tabel_1' - which are the
    same file name on Windows and macOS, and one record would silently overwrite the other.
    Hashing the exact id keeps every dataset on its own file on every filesystem.

    Never invent this name in an agent: ask scripts/next_batch.py for it.
    """
    stem = re.sub(r"[^A-Za-z0-9._-]", "_", dataset_id)[:60].strip("._-") or "dataset"
    digest = hashlib.sha1(dataset_id.encode("utf-8")).hexdigest()[:6]
    return f"{stem}-{digest}"


# Excel's own limits on a sheet name, plus the characters the template names explicitly.
# The template makes the Dataset ID the name of the dataset's indicators sheet, so a source
# id that Excel cannot spell has to be reshaped - and column D then carries the reshaped
# form, because the ID and its sheet must be the same string.
SHEET_NAME_MAX = 31
SHEET_NAME_BAD = r':\/?*[]'
# Reserved by the workbook itself, or by Excel.
SHEET_NAME_RESERVED = {"instructions", "datasets", "history"}


def sheet_name(dataset_id: str) -> str:
    """The indicators-sheet name, and therefore the column D value, for one dataset id.

    Verbatim wherever Excel allows it (field-rules D keeps the source's spelling, case,
    punctuation and version suffix). Where it does not, the forbidden characters become '-'
    and the name is cut to 31 characters, exactly as the template's Instructions sheet says.
    Use sheet_name_map() instead when there is more than one dataset: only the map can see
    that two different ids collapsed onto the same name.
    """
    text = "".join("-" if ch in SHEET_NAME_BAD else ch for ch in str(dataset_id).strip())
    text = " ".join(text.split()).strip("'")
    if len(text) > SHEET_NAME_MAX:
        text = text[:SHEET_NAME_MAX].rstrip(" '-")
    if not text or text.lower() in SHEET_NAME_RESERVED:
        text = ("ds-" + text)[:SHEET_NAME_MAX]
    return text


def sheet_name_map(dataset_ids) -> dict[str, str]:
    """dataset_id -> indicators-sheet name, for a whole workbook at once.

    Sanitizing and cutting to 31 characters can map two distinct ids onto one name, and
    Excel compares sheet names case-insensitively. Two datasets silently sharing a sheet
    would lose one dataset's indicators with no error anywhere, so a collision is resolved
    here, deterministically, by appending '~2', '~3' ... inside the 31-character budget.
    First id in wins, so the mapping is stable as long as the catalogue order is.
    """
    out: dict[str, str] = {}
    taken: dict[str, str] = {}
    for dataset_id in dataset_ids:
        key = str(dataset_id)
        if key in out:
            continue
        base = sheet_name(key)
        name = base
        n = 1
        while name.lower() in taken:
            n += 1
            suffix = "~%d" % n
            name = base[: SHEET_NAME_MAX - len(suffix)].rstrip(" '-") + suffix
        taken[name.lower()] = key
        out[key] = name
    return out


def load_catalog(workdir: str) -> list[dict]:
    """Entries from <workdir>/catalog.json, accepting a bare list or {"datasets": [...]}."""
    path = os.path.join(workdir, "catalog.json")
    if not os.path.exists(path):
        return []
    with open(path, "r", encoding="utf-8") as fh:
        data = json.load(fh)
    entries = data.get("datasets", []) if isinstance(data, dict) else data
    out: list[dict] = []
    for entry in entries:
        if isinstance(entry, str):
            out.append({"dataset_id": entry})
        elif isinstance(entry, dict):
            out.append(entry)
    return out


def load_dir(path: str, warn: bool = True) -> list[tuple[str, dict]]:
    """Every JSON object in a directory of record files, as (file name, object) pairs."""
    if not os.path.isdir(path):
        return []
    out: list[tuple[str, dict]] = []
    for name in sorted(os.listdir(path)):
        if not name.endswith(".json"):
            continue
        full = os.path.join(path, name)
        try:
            with open(full, "r", encoding="utf-8") as fh:
                data = json.load(fh)
        except json.JSONDecodeError as exc:
            if warn:
                print(f"WARN  {full}: invalid JSON ({exc}) - skipped", file=sys.stderr)
            continue
        for rec in data if isinstance(data, list) else [data]:
            if isinstance(rec, dict):
                out.append((name, rec))
    return out


def entry_id(entry: dict) -> str:
    return str(entry.get("dataset_id", "")).strip()


def indicator_rows(rec: dict) -> list[dict]:
    """The record's indicators as {"indicator": ..., "unit": ...} rows.

    Accepts the legacy v1 shape (a list of "name (unit)" strings, or one "; "-joined string)
    so that progress reporting still works on an old run, but does not repair it: such a
    record is re-run.
    """
    value = rec.get("indicators")
    if isinstance(value, str):
        value = [p.strip() for p in value.split(";") if p.strip()]
    if not isinstance(value, list):
        return []
    out: list[dict] = []
    for item in value:
        if isinstance(item, dict):
            name = str(item.get("indicator", item.get("name", ""))).strip()
            unit = str(item.get("unit", item.get("units", ""))).strip()
            if name or unit:
                out.append({"indicator": name, "unit": unit})
        elif str(item).strip():
            out.append({"indicator": str(item).strip(), "unit": ""})
    return out


def indicator_count(rec: dict) -> int:
    return len(indicator_rows(rec))


def is_legacy_indicators(rec: dict) -> bool:
    """True when the record still carries v1 indicators (strings with the unit in parentheses)."""
    value = rec.get("indicators")
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, list):
        return any(not isinstance(item, dict) for item in value)
    return False
