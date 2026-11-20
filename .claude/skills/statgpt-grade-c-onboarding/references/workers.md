# Orchestration - checkpoints, workers, context discipline

A portal with 237 datasets cannot be indexed inside one agent's context. Reading the data is
the expensive part, and raw observations are worthless once the record is written. So: **the
orchestrator holds the plan, the workers hold the data, and the disk holds the result.**

The failure this design exists to prevent: an agent that keeps every downloaded table in
context, slows down as the window fills, and has nothing on disk when it is stopped.

---

## 1. Roles

| Role | Runs | Model | Holds in context | Writes |
|---|---|---|---|---|
| **Orchestrator** (you) | once | STRONG | the plan, the catalogue counts, one status line per dataset | `run.md`, `recipe.md`, launches workers, runs the scripts |
| **Enumeration worker** | one per portal section | CHEAP | that section's listing pages | `work/catalog/<section>.json` |
| **Calibration worker** | 2 per portal shape | STRONG | one dataset each, in depth | its records, and the facts you turn into `recipe.md` |
| **Batch worker** | one per 8-12 datasets | CHEAP | those datasets' structures and data | `work/records/<safe_id>.json` per dataset (or `work/blocked/<safe_id>.json`) |
| **A script** | once per portal shape | none | nothing | `work/drafts/<safe_id>.json` - the mechanical half of every record, for free |

A worker's context dies with the worker. That is the point: it can read a 40-sheet workbook,
write a 2 KB record, and take the 40 sheets to the grave. But every worker launch costs ~15k
tokens before it does anything useful, so the number of launches is the budget - see section 4.

---

## 2. The work directory is the single source of truth

```
work/
  run.md                     decisions, adapter, endpoints, oddities   (orchestrator)
  recipe.md                  <=40 lines: how to read this portal's
                             datasets, written after calibration       (orchestrator)
  plan.json                  files and sheets per dataset, for the
                             mechanical extractor                      (orchestrator)
  drafts/<safe_id>.json      mechanically extracted candidates         (draft_records.py)
  catalog/<section>.json     catalogue fragments                        (enumeration workers)
  catalog.json               merged catalogue = the to-do list          (orchestrator)
  raw/<safe_id>/...          downloads and API responses                (dataset workers)
  notes/<safe_id>.md         a worker's own evidence notes, optional    (dataset workers)
  records/<safe_id>.json     ONE finished record per dataset, including
                             its indicator rows                        (dataset workers)
  records_backup/            copy of every finished record              (orchestrator)
  records_retired/<reason>/  records a clean-up pass replaced           (orchestrator)
  blocked/<safe_id>.json     {"dataset_id","url","reason"} per failure  (dataset workers)
  datasets.jsonl             compiled, regenerated at will              (compile_index.py)
  progress.md                counts, partials, what is left             (compile_index.py)
```

**The records directory is the most valuable thing in the run, so it gets a guard.** On a real
run a batch worker removed and recreated `work/records/` mid-wave, destroying 21 finished
records and both strong-tier calibration records - the most expensive artifacts on disk. After
every wave, copy each new record file into `work/records_backup/`, and copy back any record
that is in the backup but has gone from `work/records/`. If anything had to be copied back,
something deleted finished records - find out what before launching more.

The batch prompt in section 5 also carries an explicit never-delete rule. A guard and a
prohibition catch different halves of this: the prohibition stops the careful worker, the
mirror survives the careless one.

**Records are retired, never deleted.** When a clean-up pass finds a batch got a unit, a
coverage string or an indicator list wrong, move those records aside with a reason and let
`next_batch.py` re-queue them: move each file to `work/records_retired/<reason>/` (for
example `work/records_retired/wrong-units/`), so the run stays auditable and a reviewer can
see what an earlier pass produced. Remove it from `work/records_backup/` too, or the next
backup check copies it straight back. Find the files by the `dataset_id` **inside** each file
rather than by the file name, because several workers on a real run wrote `4926ec.json` instead of
`TABEL5_5-4926ec.json` and a name-based lookup silently reported 10 of 12 existing records as
"not written yet".

**`safe_id` is never invented by an agent.** Ask for it:

```bash
python <skill>/scripts/next_batch.py work/ --size 40 --batch-size 10
# batch 1 - 10 datasets - section(s): SEKI
# safe_id                dataset_id   section   url   title
TABEL_1-9f2a1c   TABEL_1   SEKI   https://...   I.1. Broad Money ...
```

It is the sanitized id plus a hash of the exact id, because dataset ids stay verbatim and
case-sensitive (field-rules D): a portal that publishes both `TABEL_1` and `Tabel_1` would
otherwise put two records in one file on Windows and macOS, and one dataset would vanish
without a trace. `compile_index.py` matches records by the `dataset_id` inside the file, so
the file name only has to be unique - but it does have to be unique.

**Checkpoint rule.** A dataset is finished when its record file exists on disk. Not when the
worker reports, not when the workbook is built. At any moment, `compile_index.py work/ --out
index.xlsx` turns what exists into a deliverable. Run it after every wave. If the run is
killed at wave 30 of 50, the first 30 waves are already a workbook.

---

## 3. Context discipline for the orchestrator

Hard rules. Breaking these is how the previous run turned into 2.5 hours and a stall.

1. **Never read a file under `raw/`.** No `cat`, no `head`, no file-reading tool of any kind, not even "just to
   check the header". If you want to know something about raw data, a worker looks.
2. **Never ask a worker to put the record in its reply.** The record goes to disk; the reply
   is one line. Never echo a record, an indicator row, or a description into your own context
   or into `run.md`. Indicator lists are now the bulkiest part of a record - a single dataset
   can carry hundreds of rows - so this rule matters more than it did.
3. **Cap every tool result.** Pipe to `tail -5`, `wc -l`, `--quiet`, `--status`. A Bash call
   that can print thousands of lines gets a `| head -20` before you run it, not after.
4. **Enumerate through workers.** Listing pages are bulky; you want the counts, not the HTML.
5. **Keep `run.md` to decisions.** Adapter, endpoints, granularity sentence, completeness
   proof, rate limits, judgment calls, blocked datasets. It is prose about choices, not data.
6. **Your own context budget is about a quarter of the window.** If a step would cost more,
   it is a worker's job. When you notice yourself summarizing data rather than counting it,
   you have already broken rule 1.

---

## 4. What a worker costs, and how to not pay it 237 times

Every worker launch costs roughly **15k tokens before it fetches a single byte**: about 13k
for the agent's own boot (system prompt plus tool schemas) and about 2k for reading
`quickref.md`. If it opens `field-rules.md`, `indicators.md` and `sources.md` instead, that
alone is another 12k.

One worker per dataset, on the strongest model, is therefore the most expensive possible way
to run this skill: 237 datasets x ~25k tokens of overhead is about 6M tokens spent on boot
screens. A real run did exactly that and cost $155.

Spend in this order, and stop as soon as the datasets are covered:

| Lever | Effect |
|---|---|
| **1. Mechanize** - `draft_records.py` reads the files and derives indicator candidates, period bounds, frequencies, observation counts and unit hints | 0 tokens per dataset |
| **2. Batch** - one worker for 8-12 datasets that share a shape or a section | 237 workers -> ~25 |
| **3. Cheap tier** - batch workers on the cheapest model that passes the tier test below; the strong tier only for calibration and for genuinely messy datasets | 5-25x cheaper per token |
| **4. `quickref.md` only** - the full references are for edge cases and for you, not for every worker | 12k -> 2k per worker |
| **5. One status line back** - never a record, never an indicator list | keeps *your* context flat |

Applied together: ~25 batch workers x ~15k boot on a cheap model, plus the actual reading -
one to two orders of magnitude below one-strong-worker-per-dataset.

### Two tiers, no model names

This skill does not name models, because it is not tied to one runtime or one vendor. It
needs two tiers, and you pick them from whatever your runtime offers:

- **STRONG** - the most capable model you have. Used by you (the orchestrator), by the two
  calibration workers, and by the `--retry` / `--thin` clean-up passes.
- **CHEAP** - the least expensive model that passes the tier test below. Used by every
  enumeration worker and every batch worker, which is the overwhelming majority of the run.

**The tier test.** Do not guess whether a cheap model is good enough - measure it once:

1. Pick one dataset that a STRONG calibration worker already finished. Note its record's
   indicator row count.
2. Run that same dataset again with a CHEAP batch worker, pointed at a throwaway work
   directory so its record does not overwrite the strong one.
3. Compare:
   - `validate_records.py` on the cheap record: **0 errors**;
   - indicator row count within about 20% of the strong record's, and no row missing that the
     strong record had at a different hierarchy level;
   - no fold warnings (`by <dimension>`, `separately`, category counts);
   - `time_coverage` and `frequency_coverage` identical.
4. All four hold: run the whole fan-out on CHEAP. Any of them fails: try the next tier up and
   test again. Re-test after the first real wave, on one dataset, and again if you change the
   prompt.

If your runtime has only one model, everything below still applies: mechanizing and batching
are where most of the saving is, and they do not depend on model choice at all.

*Runtime-specific note, ignore it if it does not apply to you:* a worker is whatever your
runtime calls a subagent, task or child session (in Claude Code, the Agent tool with its `model`
field; elsewhere, the launcher's own config names the model). What
the skill needs from a worker is only this: a fresh context, the ability to fetch URLs and run
shell commands, the ability to write files inside the work directory, and a text reply. If your
runtime has no subagents at all, see section 8.

### Mechanize before you fan out

If 8 or more datasets are files with a stub column and period headers:

```bash
# download once (no tokens), convert legacy .xls to .xlsx once (references/sources.md
# section 5: a year header stored as a date serial is a YEAR, not 1905), then derive the
# mechanical half for every dataset at once
python <skill>/scripts/draft_records.py work/ --plan work/plan.json
```

`work/plan.json` is a list of `{dataset_id, dataset_url, dataset_name, files, sheets, unit}`
built from `catalog.json` - one small script, not one agent per dataset. Each draft lands in
`work/drafts/<safe_id>.json` with the candidate indicator rows (with indentation, observation
counts and which sheets each appears on), the non-empty period bounds per frequency, and the
unit hints. The batch worker then **reviews a 3 KB draft** instead of reading 40 sheets.

Drafts are not records: reference area, regional coverage, description and the final
indicator wording still need the worker.

Each draft lands in `work/drafts/<safe_id>.json`. Read the drafter's summary line: it says how
many candidate rows it flagged `still_ambiguous` or non-English, and which datasets have no
English label column at all. Those are the datasets that need a glossary in `recipe.md` and the
ones a cheap worker will get wrong if you do not tell it to look.

**A drafter defect is the most expensive kind.** It is wrong identically on every dataset, so
calibrate against two strong-tier records before the fan-out and re-check with
`audit_corpus.py --only drafts` afterwards. On a real run the generic drafter was wrong about
the label column, the year assignment and what counts as an observation, which between them
mislabelled the frequency of 87 of 108 datasets; all three are fixed in `draft_records.py` now,
but the check is what told anyone.


### The wave loop

```bash
python <skill>/scripts/next_batch.py work/ --size 40 --batch-size 10   # 4 batch workers
# ... launch those 4 workers at once, on the CHEAP tier, collect their status lines ...
# ... back up work/records/ and restore anything that vanished (section 2) ...
python <skill>/scripts/compile_index.py work/ --status                  # n of N, partials, thin rows
```

- 3 to 5 batch workers concurrently. `next_batch.py` reads what is already on disk, so a
  re-run never re-does a finished dataset - never keep the pending list in your head.
- **Check the new wave against the batches still in flight before launching it.** `next_batch.py`
  only knows what is on disk, and a dataset whose worker has not written yet still looks
  pending. Two workers were once sent to the same two datasets and overwrote each other
  mid-run. Keep the in-flight dataset ids until their workers return, and diff the next wave
  against them.
- The records backup after every wave (section 2). If it had to restore anything, something
  deleted finished records - find out what before launching more.
- Every few waves: `compile_index.py work/ --out <OUT>`, so a complete workbook always exists.
- Tell the user progress as `n of N` after each wave, in one short line.
- Clean-up passes near the end: `--retry` for the datasets marked partial, `--thin` for
  records with fewer than three indicator rows (usually a collapsed table). Those two passes
  deserve the STRONG tier - they are the datasets the cheap pass got wrong.
- Then the audit pass, which is where most real defects are found: see section 8.

**Budgets.** About 4 minutes and 15 tool calls per dataset inside a batch; a batch worker
that runs out writes what it has, marks the unfinished datasets `"partial"`, and returns.
Nothing is allowed to hang: no dataset is worth stalling the run.

**When per-dataset workers are still right.** A messy dataset (a JS-only explorer, a cube
with an odd measure structure, a table whose layout changes between eras) earns its own
worker on the STRONG tier. That is a handful of datasets per portal, not all of them.

---

## 5. The batch worker prompt

One worker, several datasets. Fill the placeholders and send it as the worker's whole task;
keep the rest verbatim - the reading list and the prohibitions are what keep the run cheap.

Launch it on the CHEAP tier (see "Two tiers, no model names" above). Use the STRONG tier only
for the two calibration datasets and for the `--retry` / `--thin` clean-up passes.

```
You are a dataset worker for the Grade C Dataset Discovery Index. You have several datasets.

Read, in this order, and nothing else unless a rule in them sends you further:
  <SKILL_DIR>/references/quickref.md     the whole job on one page - the record, the ten
                                         fields, the indicator rules, how to read the data
  <WORKDIR>/recipe.md                    this portal's recipe, if the file exists
Open <SKILL_DIR>/references/field-rules.md, indicators.md or sources.md ONLY for a case
quickref.md does not cover. Each of them costs about as much as this whole task.

Shared for every dataset below:
  adapter:   <ADAPTER>, base endpoint(s): <ENDPOINTS>
  agency:    <AGENCY>        # use verbatim unless a dataset is published by someone else
  work dir:  <WORKDIR>       # write only inside it
  drafts:    <WORKDIR>/drafts/<safe_id>.json, when present - START FROM IT: it already has
             the candidate indicator rows, the non-empty period bounds per frequency, the
             observation count and the unit hints, extracted from the files themselves.
             Verify and correct it; do not re-read the whole file to redo work a script did.
             Open it with an explicit encoding: open(path, encoding="utf-8").

NEVER DELETE OR RECREATE A DIRECTORY. <WORKDIR>/records/, drafts/ and catalog/ hold other
workers' finished work, and a worker that wiped records/ once destroyed 23 finished records.
Create and write your OWN files; remove nothing.

Your datasets (safe_id, dataset_id, section, url, title):
<PASTE THE next_batch.py BLOCK FOR THIS BATCH>

For each dataset, in order:
1. If a draft exists, read it. Otherwise harvest the structure and read the ACTUAL data -
   every sheet of every file, or availability plus first/last observation queries. Save what
   you fetch under <WORKDIR>/raw/<safe_id>/. Never infer coverage from titles, sheet names
   or portal blurbs; empty and zero-filled periods are not data, and neither is a literal 0
   or a '-'.
2. Compose the record per quickref.md - nine fields, then indicators, then evidence. There is
   no dataset_number and no excluded_regional_values.
3. Indicator rows: one row per indicator per unit, unit in its own field. WRITE OUT every
   breakdown category as its own row - sector, partner country, product, instrument, tenor,
   purpose, holder, bank group, expenditure division. "by economic sector", "separately" or
   "(17 sectors: ...)" in a row name is wrong: the 17 sectors are 17 rows. Keep every
   hierarchy level that carries numbers, aggregates and components alike.
   - Where the draft marks a row still_ambiguous or suggestion_reliable: false, the script
     could NOT tell which block that row belongs to. Open the sheet and look. Do not copy the
     suggestion: chaining the row above produced names like "laos, laos, malaysia", because on
     a list of countries the row above is a sibling, not a parent.
   - Every unit in English and of the right KIND: an interest rate, a share, an index or an
     exchange rate is never an amount of money. Before writing "unit not stated by source",
     read the parenthetical line under the sheet title - that is where it usually is.
4. regional_coverage: name every sub-national region with data, each with its level in
   parentheses - "Aceh (province), Bali (province)". Exactly "None" only when the dataset has
   no sub-national breakdown at all. If the dataset's own rows ARE regions, it is not "None".
5. description: 40-180 words saying what THIS dataset measures. Never put the dataset id in
   it; naming the file code instead of the measurement tells a search layer nothing.
6. evidence.observation_count is a COUNT OF NON-EMPTY OBSERVATION CELLS. It is not your row
   count and not a multiple of it. When a draft exists, use the draft's observation_count.
   time_coverage's latest period is the latest observation across ALL frequencies, not the end
   of the annual block.
7. Verify the dataset URL answers 200 to a plain GET.
8. Write <WORKDIR>/records/<safe_id>.json - that exact file name, nothing shorter - then
   validate it and fix every error:
     python <SKILL_DIR>/scripts/validate_records.py <WORKDIR>/records/<safe_id>.json
9. Move on. Do not hold the previous dataset's data in mind; it is on disk and it is done.

Budget: about 4 minutes and 15 tool calls per dataset. If a dataset runs out of budget,
write what you have with evidence.data_read = "partial" and evidence.note saying what is
missing, and go to the next one. If a dataset cannot be read at all (404, login wall,
paywall, robots prohibition), write <WORKDIR>/blocked/<safe_id>.json =
{"dataset_id": ..., "url": ..., "reason": "..."} and go on. Never work around access
controls. Never stall the batch on one dataset.

If something about the DATA looks wrong rather than just hard - a period starting in 1905, a
header you cannot interpret, a draft that disagrees with the sheet - say so in your NOTE. Two
workers independently reporting the same anomaly was the strongest signal available on a real
run, and it is how three portal-wide defects were found.

If you discover something about this portal that the next worker would need - a sheet naming
rule, where the units hide, an era split - append at most three lines to <WORKDIR>/recipe.md.

Reply with ONE line PER DATASET and nothing else - no records, no indicator lists, no
descriptions, no summaries of the data:
DATASET <dataset_id> | STATUS complete|partial|blocked | INDICATOR ROWS <n> | OBS <n> | SPAN <min>..<max> | FREQ <value> | NOTE <at most 15 words>
```

For a single messy dataset that earns its own STRONG-tier worker, use the same prompt with
one row in the dataset list and a budget of 10 minutes and 40 tool calls.

---

## 6. The enumeration worker prompt

```
You are an enumeration worker for the Grade C Dataset Discovery Index.

Read <SKILL_DIR>/references/sources.md, section <ADAPTER_SECTION>.

Section to enumerate: <SECTION_NAME> at <SECTION_URL>
Adapter: <ADAPTER>, base endpoint(s): <ENDPOINTS>
Dataset granularity for this portal: <ONE SENTENCE FROM THE ORCHESTRATOR>

List EVERY dataset in this section, then prove the list is complete by one of:
the API's own total matching your count; pagination to an empty page; a second exhaustive
crawl returning the same count; or a cross-check against a sitemap, bulk metadata file,
empty-query search or A-Z index.

Write <WORKDIR>/catalog/<SECTION_SLUG>.json:
{"section": "<SECTION_NAME>", "total_reported": <int or null>,
 "completeness": "<one sentence on how you proved it>",
 "datasets": [{"dataset_id": "...", "title": "...", "url": "...", "structure_ref": "...",
               "notes": "..."}]}

dataset_id is the source's own identifier, verbatim and case-sensitive (field-rules D).
Do not include reports, PDFs, calculators, regulation pages or anything without statistical
series. Note anything you deliberately excluded in "notes" on the fragment.

Reply with ONE line and nothing else:
SECTION <name> | DATASETS <n> | COMPLETENESS <at most 12 words> | EXCLUDED <n>
```

---

## 7. The audit pass - what actually finds defects

On a real 109-dataset run, twenty-five defects reached the records. **`validate_records.py`
caught three.** It checks the *shape* of a record - required keys, no duplicate rows, no
hedge words, a unit on every indicator - and a record can be perfectly well-formed and still
say that an interest rate is measured in billions of rupiah, that a series starts in 1905, or
that a row is called `laos, laos, malaysia`.

Shape validation is necessary and not sufficient. Budget a pass for this, on the orchestrator,
before delivering. Ranked by what they caught:

**1. Audit one field across every record at once - nine defects.**

```bash
python <skill>/scripts/audit_corpus.py work/                       # every section
python <skill>/scripts/audit_corpus.py work/ --only units          # one at a time
python <skill>/scripts/audit_corpus.py work/ --words dan,dalam,jumlah   # untranslated rows
```

It tallies every distinct `unit`, `regional_coverage` and `frequency_coverage`, groups every
description by its opening, and checks each record's stated period against its own evidence. A
wrong value that looks plausible in one record is obvious when it is 479 rows, or when 105
records in a row say `None`. This is cheap - it reads records, not data - and it prints dataset
ids whose records you retire straight away (section 2).

**2. Cross-check records against the mechanized draft.** `audit_corpus.py --only drafts` prints
record versus draft for frequency, observation count and row count, one line per disagreement.
The draft came from the files by script, so it is a second opinion that costs nothing. Where
the draft is right, re-run the record. Where the **draft** is wrong, fix `draft_records.py` and
rebuild: a drafter defect is wrong identically on every dataset, which is exactly why it is
worth fixing there rather than in a hundred prompts.

**3. Verify the URLs the way the field rule says.** One plain GET per distinct column G URL,
with no `Range` header and no `HEAD`; a URL passes on 200 with a body that is the dataset, not
an HTML error page. Run the same check on a URL you are sure of first (point 4).

**4. Test any checker against a known positive first.** A completeness probe once reported zero
unlisted datasets for two hours because it read a still-compressed response body and never
matched the file's magic bytes. The question that broke it open was not "is the portal
complete?" but "does this probe return true for a file I know exists?". Any checker that can
only report absence gets run against a present case before you believe it. That is why
the URL check starts on a known-good URL, and why a cheap `Range` probe is not a substitute for the plain GET the
field rule asks for - on one portal a single URL served the file on a plain GET and returned an
HTML error page when a `Range` header was sent.

**5. Calibrate on two datasets before the fan-out.** Two strong-tier workers reading one table
each, cell by cell, produced the findings that corrected 87 of 108 frequency verdicts and
located the English label column. Two worker launches; they saved the run.

**6. Read what workers volunteer.** Status lines are capped at one line per dataset, but their
notes carry real signal: the 1905 spans, the quarter-end headers, the overwritten files. Two
workers independently reporting the same anomaly is the strongest evidence you will get.

**When an audit finds something, fix it in the right place.** A bad record is re-run, never
hand-patched - patching a record nobody re-read just moves the lie. A bad *drafter* is fixed in
the script and every affected record re-run. Only mechanically derived evidence (an observation
count the script can recount) is ever repaired in place, and never a name, a unit or a coverage
string.

---

## 8. If the runtime has no subagents

Same discipline, sequentially, and the cost rules matter even more because there is no cheaper
tier to delegate to: mechanize with `draft_records.py` first, work from the drafts, and keep
`quickref.md` as the only reference you re-read. Process one dataset, write its record file, and then
explicitly drop the raw data from your working set - do not summarize it, do not keep it
"for later". Re-read only `catalog.json` and `progress.md` between datasets. Run
`compile_index.py` every few datasets so the workbook on disk stays current. It is slower
than fanning out, but it still cannot stall with everything trapped in one context.
