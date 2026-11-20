---
name: statgpt-grade-c-onboarding
description: >-
  Build a Grade C Dataset Discovery Index workbook (StatGPT Grade C onboarding) from the URL of a
  statistical data portal or data explorer. Enumerates every dataset the portal publishes,
  mechanizes what a script can extract, fans out batched subagents to read the actual data,
  checkpoints each dataset to disk, and compiles a Datasets tab with one row per dataset (area,
  regional coverage, agency, ID, name, description, URL, time and frequency coverage) plus one
  indicators sheet per dataset listing every indicator and its unit, breakdowns written out row
  by row. Use when asked for Grade C onboarding, a Grade C index or a dataset discovery index, or
  to index, inventory, catalogue or profile the datasets of a statistical agency, central bank,
  or SDMX / PxWeb / CKAN / JSON-stat portal - even when the user just pastes a portal URL and
  says "onboard this as Grade C".
compatibility: >-
  Python 3.9+ with openpyxl; network access to the portal. Optional: requests, xlrd or
  LibreOffice for legacy .xls, browser automation for JavaScript-only explorers, and subagents
  (the run is far cheaper with them).
---

# Grade C Dataset Discovery Index

## What you are producing

One `.xlsx` workbook:

- `Instructions` - the field specification, copied verbatim from the template.
- `Datasets` - **one row per dataset**, nine columns A-I, in this fixed order:

| Col | Field |
|-----|-------|
| A | Reference area / country |
| B | Regional coverage |
| C | Agency / organization |
| D | Dataset ID |
| E | Dataset name |
| F | Description |
| G | Dataset URL |
| H | Time coverage |
| I | Frequency coverage |

- **one indicators sheet per dataset**, named with that dataset's **ID** from column D - `TABEL1_1`'s indicators are on sheet `TABEL1_1`. Two columns: `Indicator` | `Units of measure`, one row per indicator per unit.

A 237-dataset portal therefore produces a workbook with 239 sheets.

The consumer of this workbook is a **search layer**: given a user question it picks one row and sends the user to that source link. Everything follows from that. A vague row is worse than no row, because it wins searches it cannot answer. An indicator missing from a dataset's sheet is invisible forever.

**Breakdowns are written out as rows, never folded.** A table broken down by 17 economic sectors gets 17 rows, not one row saying "by economic sector". Same for partner countries, products, instruments, tenors and expenditure divisions. This is the rule the template is most explicit about.

**Enumerated values are written out everywhere the same rule applies.** Column B names every sub-national region the dataset covers, each with its level in parentheses (`Aceh (province), Bali (province)`) - not the levels alone. A region not listed will not be found, exactly as an indicator not listed will not be found.

Write everything in **English**, as plain text.

There is **no dataset number** and **no "excluded regional values"** column. The dataset's own ID identifies the row and names its sheet; a region the dataset lacks is simply absent from column B. Records from an older run carrying `dataset_number` or `excluded_regional_values` still load - those keys are ignored, and the validator says so once.

## How the work is organised

You are the **orchestrator**. You do not read datasets yourself.

```
recon (you)  ->  enumeration workers  ->  catalog.json  ->  waves of dataset workers
                                                                      |
                                            one record file per dataset on disk
                                                                      |
                                       compile_index.py  ->  datasets.jsonl  ->  .xlsx
```

- Datasets are read by **subagents in batches** - one worker for 8-12 datasets that share a shape - each writing one small record file per dataset and returning **one status line per dataset**. Their context - the sheets, the API responses, the observations - dies with them.
- Before fanning out, **mechanize**: `draft_records.py` derives the candidate indicator rows, the period bounds, the frequencies and the unit hints straight from the files, for free. Workers then review a small draft instead of reading 40 sheets. A defect in the drafter is wrong identically on every dataset, so it is checked against the two calibration records before the fan-out.
- Workers run on the **cheap tier** and read one page (`references/quickref.md`), not three documents. The strong tier is for you, for two calibration datasets, and for the clean-up passes. The skill names no models: `references/workers.md` section 4 defines the two tiers and a four-check test that tells you which of your runtime's models qualifies as cheap.
- A dataset is done when `work/records/<safe_id>.json` exists. **The disk is the state of the run**, not your context.
- `compile_index.py` turns whatever records exist right now into a complete workbook. Run it after every wave. If the run is interrupted at any point, everything finished so far is already a deliverable.

**Read `references/workers.md` before Step 1.** It holds the work-directory layout, the context rules, the wave sizes and the exact worker prompts. Do not improvise the worker prompts: the prohibitions in them are what keep this run from collapsing into one enormous context.

## Inputs

- **`INPUT_URL`** (required) - the portal / data explorer root, or the deepest page that lists datasets.
- `OUT` (optional) - output workbook path. Default `<RUN_DIR>/Grade_C_Dataset_Discovery_Index_<AGENCY_ACRONYM>_<YYYY_MM_DD>.xlsx`.
- `RUN_DIR` (optional) - where the run's `work/` directory and the workbook live. Default `grade-c-runs/<agency-or-domain-slug>/` under the current directory. Never put it inside this skill's folder, and never let run output get committed: if the current directory is a git repository, make sure `grade-c-runs/` is git-ignored there before Step 0 (add it to `.git/info/exclude` when it is not in `.gitignore`). The StatGPT docs repository is public - portal data and run notes must not land in it.

`<skill>` and `<SKILL_DIR>` in the commands below mean the directory holding this `SKILL.md`. All `work/` paths are relative to `RUN_DIR`: run the scripts from there.
- `SCOPE` (optional) - a portal subsection, when the user names one. With no scope, **the whole portal is in scope**.

If `INPUT_URL` is missing, ask for it. Ask nothing else: every other decision is already made below. If a case is genuinely not covered, choose the reading that makes the row *more* falsifiable, and record the choice in `run.md`.

## What this skill needs from your runtime

It is runtime-neutral: nothing in it depends on a particular vendor's agent, tool names, model names, or on anything remembered from an earlier session. Everything a run needs is this directory plus the `work/` directory it creates.

**Required**
- Python 3.9 or newer with `openpyxl` (`pip install openpyxl`) - the scripts do the workbook and the validation.
- A shell, to run those scripts.
- Network access to the portal, from either a fetch tool or Python (`requests`, `urllib`).

**Optional, per portal**
- `xlrd` (`pip install xlrd`) or LibreOffice when the source publishes legacy `.xls`, to convert it to `.xlsx` (`references/sources.md` section 5). Check which you actually have before planning a step around it.
- Browser automation of any kind (Playwright, Puppeteer, Selenium, a built-in browser tool) for JavaScript-only data explorers. Without it, those portals need one manual step, described in `references/sources.md` section 6.
- A subagent mechanism - whatever your runtime calls subagents, tasks or child sessions. This is what makes the run cheap and keeps the orchestrator's context flat. **Without one, follow `references/workers.md` section 8**, which does the same work sequentially.

**Model tiers** are referred to as STRONG and CHEAP, never by name; `references/workers.md` section 4 says how to pick them from what you have, and gives a four-check test for whether a cheap model is good enough. With a single model available, the mechanization and batching rules still apply and still carry most of the saving.

## Non-negotiable rules

1. **No sampling.** Every dataset in scope gets a row, and every dataset's data gets read. If the portal has 1,400 datasets the answer is 1,400 rows, not "a representative 50". Batch it, checkpoint it, keep going; never present a partial index as complete.
2. **Checkpoint before you continue.** Each dataset's record is written to its own file the moment it is finished. Nothing important lives only in an agent's context, ever. Compile to the workbook every few waves.
3. **Data beats metadata.** Coverage claims on the portal, in a PDF, in a dataflow annotation or in a sheet title are *hints*. Columns A, B, H and I, and every row of the indicators sheets, are derived from observations a worker actually saw. When metadata and data disagree the data wins, and the disagreement goes in `run.md`.
4. **Never invent.** No indicator, area, period or unit may appear in a row unless it was seen in the source's structure *and* confirmed to carry at least one real observation. Empty and zero-filled placeholder periods are not data, and neither is a literal `0` or a `-`. An observation count is counted, never multiplied out of a row count.
5. **Verbatim, unique identifiers.** Dataset IDs keep the source's exact spelling, case, punctuation and version suffix, and no two datasets of one agency share an ID - the template requires it. The one exception is forced by Excel: the ID names the dataset's indicators sheet, so an ID over 31 characters or containing `: \ / ? * [ ]` is reshaped - by `build_workbook.py`, once, for the whole workbook, never by hand.
6. **No hedging vocabulary.** `etc.`, `various`, `and more`, `and others`, `including but not limited to`, `multiple indicators`, `several`, `TBD`, `N/A`, `unknown` are forbidden in every cell. If you do not know, go and find out.
7. **Indicators are enumerated and expanded, not summarized.** Every line item, every hierarchy level that carries numbers, every breakdown category gets its own row with its own unit. See `references/indicators.md`; it gets the most work and the most verification.
8. **One record per dataset, at the source's own granularity.** A dataset is whatever unit the source itself identifies and links to: an SDMX dataflow, a PxWeb table, a CKAN package, a cube, a numbered table with its own code. Era-split files of one table are one dataset. A dataflow is never split into one row per country.
9. **Every URL is verified.** Column G must answer 200 to a **plain GET**, point at the deepest stable public page for that dataset, and carry no session token, no expiring signature and no UI state. A cheaper probe is not a substitute: on one portal a `Range` request returned an error page for a URL that a plain GET served correctly.
10. **Nothing hangs.** Workers have a time and tool-call budget; when it runs out they write a partial record and return. A stalled dataset is logged and skipped, never waited on.
11. **Validate, then audit, before delivering.** `scripts/validate_records.py` must pass with zero errors, and warnings are read and either fixed or explained. But it only checks a record's *shape*: on a real run twenty-five defects reached the records and it caught three. `scripts/audit_corpus.py` is the other half - see Step 4b. Never treat a clean validation as a clean index.
    **The validator checks only what is knowable** - closed standards (ISO 3166-1 alpha-3, the frequency vocabulary), the template's own grammar, Excel's documented limits, and computable facts. It must never encode a guess about the world: there is no closed list of sub-national level names, or of units of measure, and a rule built from one portal's vocabulary is wrong on the next portal, silently and unpredictably. Judgment of that kind goes in the audit, where a reader decides, not in a check that gates the build.
12. **A record is re-run, not patched.** When a check finds a bad unit, coverage string or indicator list, retire the record and re-run the dataset. Hand-editing a record you never read the data for just moves the error somewhere harder to find. Only mechanically recountable evidence is ever repaired in place - never a name, a unit or a coverage string.
13. **Fix a systematic defect in the script, not in the prompt.** The drafter runs once per dataset for free, so a bug in it is wrong identically on every record - and a rule added to a worker prompt is obeyed unevenly by a hundred cheap workers. Where a judgment can be mechanized, mechanize it.
14. **Pay for reading data, not for booting agents.** A worker launch costs about 15k tokens before it fetches anything. Mechanize first, batch 8-12 datasets per worker, run workers on the cheap tier with `quickref.md` as their only reference, and reserve the strong tier for calibration and clean-up. One worker per dataset on the strong tier costs about a hundred times more for the same workbook - see `references/workers.md` section 4.

## Workflow

### Step 0 - Set up the run

Create the work directory from `references/workers.md` section 2:

```bash
mkdir -p <RUN_DIR> && cd <RUN_DIR>
mkdir -p work/catalog work/records work/blocked work/raw work/notes
```

Start `work/run.md` with `INPUT_URL`, the date, `OUT`, and the scope in one or two sentences. Keep `work/` next to the output workbook so the run survives a restart. Large downloads may live in a temp directory outside `work/`, but record files never do.

### Step 1 - Identify the source and pick an access adapter (you, briefly)

Fetch `INPUT_URL` and run the detection probes in `references/sources.md` in order. Answer three questions and write the answers in `run.md`:

1. **Who publishes this?** Official English name + acronym, from the site's own About / Imprint page, never guessed from the domain. This is column C for every row, unless the portal aggregates several publishers, in which case workers resolve it per dataset.
2. **Is there a machine interface?** SDMX 2.1/3.0, PxWeb, CKAN, JSON-stat, OData, Socrata, a plain JSON catalogue, an XML/CSV index, or nothing but HTML and files. Prefer: documented API > bulk catalogue file > HTML scraping with a headless browser > hand navigation.
3. **What is the dataset granularity here?** One sentence, for example "one dataset = one SDMX dataflow", or "one dataset = one numbered SEKI table, published as several era `.xls` files". Every worker gets this sentence.

Keep this step small: a handful of fetches, a JS-only portal's XHR list, the base endpoints. Do not start reading datasets.

### Step 2 - Enumerate every dataset through workers

Split the portal into sections (a database, a publication, a menu branch, an API collection). Launch **one enumeration worker per section**, using the prompt in `references/workers.md` section 6, 3-5 at a time. Each writes `work/catalog/<section>.json` and returns one line.

Then merge the fragments into `work/catalog.json`: one list of `{"dataset_id", "title", "url", "section"}` entries, in the portal's own order. While merging, count the entries per section and look for repeated `dataset_id`s and for one id with two different URLs.

Completeness gate - do not leave this step until `run.md` records, per section, one of:

- the API reported a total and the count matches; or
- pagination ran to an empty page with consistent page sizes; or
- a second exhaustive crawl returned the same count; or
- a cross-check against a sitemap, bulk metadata file, empty-query search or A-Z index.

Resolve duplicates and url conflicts before fanning out: a bad catalogue multiplies into hundreds of wasted worker runs.

### Step 3 - Calibrate, mechanize, then fan out in batches

Read `references/workers.md` section 4 before this step; it holds the cost arithmetic and the exact commands.

**3a. Calibrate (2 workers, STRONG tier).** Pick two datasets that represent the portal's main shape and run them as single-dataset workers. From what they report, write `work/recipe.md` - at most 40 lines: which files to fetch and how, which sheets matter, where the stub column and the header row are, where units are stated, how indicator names should read, which era sheets exist, what the traps are. Every later worker gets this file, which is what lets them run on a cheap model.

**3b. Mechanize (0 tokens per dataset).** If 8 or more datasets are files with a stub column and period headers, download them, convert legacy `.xls` in one command, build `work/plan.json` from the catalogue, and run:

```bash
python <skill>/scripts/draft_records.py work/ --plan work/plan.json
```

Legacy `.xls` files are converted to `.xlsx` first; `references/sources.md` section 5 says how, and names the date trap a naive conversion falls into.

Each draft carries the candidate indicator rows (with a dataset-unique suggested name, observation counts and the sheets each appears on), the non-empty period bounds per frequency, the frequency, the observation count and the unit hints. This is the reading that would otherwise burn a worker's whole budget.

**Check the drafts against the two calibration records before you fan out.** If the drafter's frequency, period bounds and row count do not reproduce what the two strong-tier workers found by hand, the drafter is wrong - and it is wrong identically on every dataset. On a real run this comparison changed the frequency verdict on 87 of 108 datasets. Read the drafter's summary line too: it reports how many candidate rows it flagged `still_ambiguous`, and which datasets have no English label column at all. Those are the datasets that need a translation glossary in `recipe.md`.

**3c. Fan out in batches (CHEAP tier).** Ask for the wave, never assemble it from memory:

```bash
python <skill>/scripts/next_batch.py work/ --size 40 --batch-size 10
```

It prints one block per worker - 8-12 pending datasets from the same section, each line `safe_id`, `dataset_id`, section, url, title - skipping everything already on disk. Launch 3-5 of those blocks concurrently with the batch prompt from `references/workers.md` section 5, on the CHEAP tier (`references/workers.md` section 4 defines the two tiers and the test that tells you which model qualifies). Each worker, per dataset:

- starts from `work/drafts/<safe_id>.json` when it exists, otherwise reads the structure and the actual data itself;
- composes the record per `references/quickref.md`, writing out every breakdown category as its own row;
- validates its own record file and fixes every error;
- writes `work/records/<safe_id>.json` and returns **one status line per dataset**.

Before launching a wave, **diff it against the batches still in flight**: `next_batch.py` only knows what is on disk, so a dataset whose worker has not written yet still looks pending, and two workers sent to the same dataset overwrite each other.

Between waves, and never more than that:

```bash
python <skill>/scripts/compile_index.py work/ --status          # n of N, partials, thin rows, next up
python <skill>/scripts/compile_index.py work/ --out <OUT>       # every few waves: full flush to the workbook
```

After every wave, also copy `work/records/` to `work/records_backup/` and check that no record that existed before the wave has disappeared (`references/workers.md` section 2). Re-launch failures once with a note about what failed. A dataset that fails twice gets a `work/blocked/<safe_id>.json` and a line in the report. Report progress to the user as `n of N` per wave, in one short line.

**3d. Clean-up passes (STRONG tier, small).** `next_batch.py work/ --retry` re-runs the datasets marked partial; `--thin` re-runs records with fewer than three indicator rows - the signature of a table collapsed into its section headings, or of folded breakdowns. These are the datasets the cheap pass got wrong, so they are worth the STRONG tier.

### Step 4 - Compile, validate, build

```bash
python <skill>/scripts/compile_index.py work/ --out <OUT>
```

This merges `work/records/*.json` in catalogue order into `work/datasets.jsonl`, runs `validate_records.py`, and builds the workbook with the template's formatting. It refuses to write the workbook while any validation error stands.

Fix errors by re-running the affected dataset's worker, not by hand-editing a record you never read the data for. Read every warning and either fix it or explain it in the report.

### Step 4b - Audit the corpus (do not skip this)

A clean validation is not a clean index. `validate_records.py` checks the **shape** of a record; on a real run twenty-five defects reached the records and it caught three. The rest were found by looking at one field across every record at once, and by comparing records against the mechanized draft:

```bash
python <skill>/scripts/audit_corpus.py work/                          # all sections
python <skill>/scripts/audit_corpus.py work/ --words dan,dalam,jumlah # untranslated rows
```

Verify column G as rule 9 says: a plain GET per distinct URL, after the same check has returned 200 for a URL you know is good.

The audit tallies every distinct unit, regional coverage and frequency, groups descriptions by their opening, checks each record's stated period against its own evidence, and prints record-versus-draft for observation count, frequency and row count. Then retire the bad records: move each record file to `work/records_retired/<reason>/`, never delete it, and drop it from `work/records_backup/` too. Find the file by the `dataset_id` inside it, not by its name. `next_batch.py` then lists those datasets as pending again.

Re-run the affected datasets on the STRONG tier, with the verified fact quoted in the prompt. Where the **draft** was wrong rather than the record, fix `draft_records.py`, rebuild the drafts and re-run every record derived from a bad one. Repeat Step 4 and this step until the audit is quiet or every remaining finding is explained in the report.

`references/workers.md` section 7 ranks these checks by what they actually caught, and says which defect each one exists for.

### Step 5 - Report

In the chat, not in a file:

- datasets enumerated, rows written, rows partial, rows blocked;
- how completeness was proven, per section;
- the adapter and endpoints used;
- datasets that could not be read, and why;
- what the audit pass found and what was re-run because of it;
- warnings left standing, each with the reason it is correct as it stands;
- every judgment call a reviewer could reasonably have made differently.

## Record format

One JSON object per dataset, in `work/records/<safe_id>.json`. Nine fields, then `indicators`, then `evidence` - there is no `dataset_number` and no `excluded_regional_values`.

```json
{
  "reference_area": "Indonesia (IDN)",
  "regional_coverage": "None",
  "agency": "Bank Indonesia (BI)",
  "dataset_id": "TABEL1_1",
  "dataset_name": "I.1. Broad Money and its Affecting Factors",
  "description": "Money and banking table from the Indonesian Economic and Financial Statistics (SEKI) ...",
  "dataset_url": "https://www.bi.go.id/SEKI/tabel/TABEL1_1.xls",
  "time_coverage": "From 1985 to present (latest available 2026-07), monthly from 1989-01",
  "frequency_coverage": "Monthly",
  "indicators": [
    {"indicator": "broad money (M2)", "unit": "billions of Rp"},
    {"indicator": "narrow money (M1)", "unit": "billions of Rp"},
    {"indicator": "time deposits in rupiah", "unit": "billions of Rp"},
    {"indicator": "time deposits in foreign currency", "unit": "billions of Rp"}
  ],
  "evidence": {
    "structure_urls": ["..."],
    "data_urls": ["..."],
    "observation_count": 148230,
    "period_min_max": {"Monthly": ["1989-01", "2026-07"]},
    "areas_with_data": ["IDN"],
    "items_with_data": {"broad money (M2)": 451},
    "data_read": "full"
  }
}
```

`indicators` is the dataset's indicators sheet, in the source's own order: one object per sheet row, unit in its own field, never inside the name. `evidence` never reaches the workbook - it exists so a reviewer can re-check a row without re-running the crawl, and `observation_count` plus `period_min_max` are the two fields a script can recount, which is what makes a fabricated record detectable.

`assets/template.xlsx` is the reference template: the Instructions sheet, the Datasets header with formatted rows below it, and one example - row 2 plus its indicators sheet `TABEL1_1`. `build_workbook.py` copies the cell styles of that example row and sheet onto every row and sheet it writes, then removes the example. `assets/example_records.jsonl` holds the same example as a record, with all 36 of its indicator rows.

Records from an older run, with `indicators` as `"name (unit)"` strings, are rejected by the validator; re-run those datasets.

## Files in this skill

| File | Read it when |
|------|--------------|
| `references/workers.md` | before Step 1 - layout, context rules, the cost model, the worker prompts, the audit pass |
| `references/quickref.md` | the one page a worker reads - the record, the fields, the indicator rules |
| `references/sources.md` | picking the adapter and writing the fetch calls (Steps 1-3) |
| `references/field-rules.md` | composing any of columns A-I - the dataset worker reads this |
| `references/indicators.md` | composing a dataset's indicators sheet - the dataset worker reads this in full |
| `scripts/draft_records.py` | Step 3b - the mechanical half of every file-based record, for free |
| `scripts/next_batch.py` | Step 3c - what to launch next, batched, with the record file names |
| `scripts/compile_index.py` | Steps 3-4, after every wave |
| `scripts/validate_records.py` | inside a worker, on its own record; and via compile_index |
| `scripts/audit_corpus.py` | **Step 4b** - one field across every record, and records against the drafts |
| `scripts/build_workbook.py` | called by compile_index; standalone for a one-off build |

## Failure handling

- **Portal blocks automated access** - drive it through browser automation with a normal user agent at human-paced request rates, and say so in the report. Do not work around a login, a paywall or an explicit robots prohibition; those datasets go to `work/blocked/`.
- **A dataset has no stable URL** - use the deepest stable thing that exists (the file URL, the table page, the dataflow page) and note the compromise in the record's `evidence.note`.
- **Hundreds of datasets** - that is the normal case. Waves, checkpoints, a full flush every few waves, `n of N` to the user.
- **A worker returns more than its status line** - ignore the extra text, do not copy it anywhere, and tighten the prompt for the next wave.
- **Two datasets look identical** - keep both rows if the source keeps both IDs, and make column F state what distinguishes them, because that is the sentence the search layer needs.
- **A check reports nothing at all** - do not conclude "nothing is wrong" until the check has been run against a case you know is positive. A completeness probe reported zero unlisted datasets for two hours because it never matched anything, including files that demonstrably existed.
- **Two checks disagree** - that is a finding, not noise. Six defects on a real run were caught only because one check contradicted another; the one that reports success is as likely to be the broken one.

## Maintaining this skill

- Keep it agent-neutral: name no vendor, product, tool or model in `SKILL.md`, `references/` or `scripts/`; refer to model tiers as STRONG and CHEAP.
- Keep the frontmatter valid for the Agent Skills format: `name` equals the folder name, `description` is at most 1024 characters.
- After changing a script, check that the template's own example still builds and matches `assets/template.xlsx`:
  `python <skill>/scripts/build_workbook.py <skill>/assets/example_records.jsonl --out <scratch>/example.xlsx`
