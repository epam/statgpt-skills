# Worker quick reference - the whole job on one page

This is the only reference a dataset worker reads by default. Open the full documents
(`field-rules.md`, `indicators.md`, `sources.md`) **only** when a rule below says "see full
rules", or when you hit a case this page does not cover. Reading them all costs about 12k
tokens per worker, which is why this page exists.

## The record

One JSON file per dataset, at `<WORKDIR>/records/<safe_id>.json`:

```json
{
  "reference_area": "Indonesia (IDN)",
  "regional_coverage": "None",
  "agency": "Bank Indonesia (BI)",
  "dataset_id": "TABEL1_1",
  "dataset_name": "I.1. Broad Money and its Affecting Factors",
  "description": "40-180 words: what is measured; how it is broken down, with the classification and its version; whether values are adjusted, preliminary or revised; what a user might expect but will not find.",
  "dataset_url": "https://www.bi.go.id/SEKI/tabel/TABEL1_1.xls",
  "time_coverage": "From 1985 to present (latest available 2026-07), monthly from 1989-01",
  "frequency_coverage": "Monthly",
  "indicators": [
    {"indicator": "broad money (M2)", "unit": "billions of Rp"},
    {"indicator": "time deposits in rupiah", "unit": "billions of Rp"}
  ],
  "evidence": {"structure_urls": [], "data_urls": [], "observation_count": 0,
               "period_min_max": {"Monthly": ["1989-01", "2026-07"]},
               "areas_with_data": ["IDN"], "data_read": "full"}
}
```

Nine fields, then `indicators`, then `evidence`. There is no `dataset_number` and no
`excluded_regional_values` - if you have seen those in an older record, the template dropped
them.

## The nine fields

| Field | Rule |
|---|---|
| `reference_area` | `Name (ISO3)`, `"; "` separated, every country written out. Group labels allowed without a code. Bilateral: reporting countries, then `partner countries:` and the list. |
| `regional_coverage` | **Every sub-national region with data, written out, each with its level in parentheses**: `Aceh (province), Bali (province)`. Not the levels alone - a region not listed is never found. Several countries: `Country (ISO3): regions` pairs, `"; "` separated. National totals only: exactly `None`. |
| `agency` | `Official English name (ACRONYM)`. Joint: `Lead (ACR) / Second (ACR)`. Use the value the orchestrator gave you unless this dataset is published by someone else. |
| `dataset_id` | The source's own id, verbatim and case-sensitive. No trimming, no case changes, keep version suffixes like `(2.0.0)`. It also names this dataset's indicators sheet; the build shortens it if Excel cannot spell it, so you never do that yourself. Unique across the agency: two datasets never share an id. |
| `dataset_name` | The official published English title, including its table numbering. No English title: literal translation with the original in parentheses. |
| `description` | Plain prose, 40-180 words, single paragraph, no URLs, no marketing words. Must cover what is measured, the breakdowns *and the classification version*, and the adjustment / preliminary / revision status. **Never write the dataset id into it** - name the measurement instead. |
| `dataset_url` | Deepest stable public `https://` page (or file) for this dataset; must answer 200 to a plain GET; no session tokens, no UI state. |
| `time_coverage` | `From <period> to <period>` or `From <period> to present (latest available <period>)`. Periods: `YYYY`, `YYYY-Qn`, `YYYY-MM`, `YYYY-MM-DD`. Differing starts, breaks and projections go in a trailing note after `, ` or `; `. **Derive from non-empty observations only** - never from sheet names or titles. The latest available period is the latest observation across **all** frequencies, not the end of the annual block. |
| `frequency_coverage` | From this closed list, in this order, `"; "` separated: `Daily; Business daily; Weekly; Monthly; Quarterly; Semi-annual; Annual; Irregular`. Only frequencies that carry data. |

Forbidden everywhere: `etc.`, `various`, `including but not limited to`, `multiple indicators`, `main indicators`, `TBD`, `not specified`, `...`.

`evidence.observation_count` is a count of non-empty observation cells. **It is not your row count, and not a multiple of it.** When a draft exists, use the draft's `observation_count`: a script counted it from the files.

## The indicators sheet

One object per row of the dataset's own indicators sheet: `{"indicator": ..., "unit": ...}`.

1. **An indicator is a measured quantity** - what a single number in the dataset is a number *of*, after stripping where (reference area), when (period), how often (frequency) and adjustment status.
2. **Rows come from the source's own line items**: stub labels of every data block and every sheet, including historical / era sheets; or, for cubes, the measure dimension's codes.
3. **Write out every breakdown category as its own row** - sector, partner country, product, instrument, tenor, maturity, purpose, holder, ownership, bank group, expenditure division. 17 sectors are 17 rows.
   - right: `time deposits in rupiah` / `time deposits in foreign currency`
   - wrong: `time deposits, rupiah and foreign currency separately`
   - wrong: `outstanding loans by economic sector (17 sectors: agriculture, ...)`
4. **Every hierarchy level that carries numbers gets a row** - the aggregate *and* its components.
5. **Naming**: the source's own wording, English, lower case except proper nouns and acronyms; `of which` rows resolved against the parent (`rupiah demand deposits, of which electronic money`); sub-items after a comma (`claims on the private sector, loans`); partners with the source's preposition (`exports to Japan`); memo items keep `memo item: `; era limits noted in the name (`import guarantee deposits (1985-2003 sheets only)`).
   - **English.** If the sheet has no English repeat for a row, translate it - do not copy the local label through. Ask the orchestrator for the glossary in `recipe.md`. Strip list numbering (`4. Pemerintah`) and a leading `*`; for a bilingual `Local / English` label keep only the English half.
   - **Resolve a repeated label against its real parent, not against the row above.** On a list of partner countries or sectors the row above is a *sibling*, and chaining it produces names like `laos, laos, malaysia` or `Agriculture, Mining`. When a draft marks a row `still_ambiguous` or `suggestion_reliable: false`, open the sheet and see which block the row actually sits in. A name whose comma-separated parts repeat is always wrong.
6. **Unit in its own field, never in the name.** `billions of Rp`, `millions of USD`, `2022=100`, `percent`, `percent per annum`, `percent of GDP`, `persons`, `thousand tonnes`, `per 100,000 population`. Same indicator in two units = two rows.
   - **In English, always.** If the source writes `Miliar Rp`, `dalam miliar rupiah`, `Persen Per Tahun`, `Ribu USD`, translate it: `billions of Rp`, `percent per annum`, `thousands of USD`. These are the same units as their English forms, never separate ones.
   - **Sanity-check the kind of unit.** An interest rate, a yield, an index or a share is not an amount of money - a whole table of rates once shipped as `Miliar Rp` when it was `percent per annum`. Use the source's own unit statement; this is a check on your reading of it, not a list to choose from.
   - `unit not stated by source` only after looking in **all three** places: the header block, the line under the sheet title, and the footnotes. The unit is very often in the parenthetical under the title - `(Thousands of USD)`, `(Millions of USD)`, `(Thousands of Ton)`. 479 rows once shipped unitless on tables whose files stated the unit plainly.
7. **Only what has data.** A line item with no non-empty observation anywhere is not published - leave it out, and mention it in `description` if the portal advertises it.
8. **Complete, never truncated.** 240 published line items = 240 rows. Typical table: 10-200 rows. If a cube's breakdown cross-product would exceed 2,000 rows, expand each dimension separately against the measure and say so in `description` (see full rules, `indicators.md` I-2).
9. Never a row: areas (partners excepted), periods, frequencies, units, adjustment variants, section headings with no numbers, the dataset name.

## How to read the data (short form)

- **Spreadsheets**: every sheet of every file, including era sheets. Stub column = indicator rows; header rows = periods; footnote block = units, classification version, `r`/`*` flags. `.xls` needs a conversion to `.xlsx` first (`references/sources.md` section 5); a date-typed header cell whose value is a plausible year (2005) is that year, not a 1905 date.
  - The leftmost text column is not always the labels you want. On a bilingual portal the English labels can sit far to the right, past the last data column, under a header reading `Items`.
  - A literal `0` and a `-` are not observations. A row of them is not a published series.
  - Quarter columns are sometimes written as the quarter's **last month** (`2004-03`, `2004-06`, `2004-09`, `2004-12`). That is quarterly data, not a monthly series missing nine months a year.
  - A period bound before 1900 is a date-conversion defect, not a real span. Say so; do not "correct" it by guessing.
  - Open a draft with an explicit encoding (`open(path, encoding="utf-8")`).
- **SDMX**: `availableconstraint` (2.1) / `availability` (3.0) gives the codes that actually carry data plus the time range; then `?firstNObservations=1` and `?lastNObservations=1` per frequency. Whole-flow CSV only if availability is unsupported.
- **PxWeb**: the table's `variables` for codes, a query over the whole time variable for the span, CSV/json-stat2 for the rest (`status` marks empty cells).
- **CKAN / files**: download every distribution.
- Coverage always comes from observations you saw. Empty and zero-filled periods are not data.

For anything else - OData, Socrata, ArcGIS, JSON-stat, JS-only portals - see `sources.md`.

## Before you finish

1. Every indicator row has a non-empty unit, in English, of the right kind for that indicator, and no unit inside the name.
2. No row contains `by <dimension>`, `separately`, `respectively`, or a category count in parentheses.
3. No indicator name repeats a comma-separated part, and nothing is left in the source's language.
4. All hierarchy levels and all breakdown categories are written out.
5. `time_coverage` and `frequency_coverage` come from non-empty observations, and the latest period is the latest across every frequency.
6. `regional_coverage` names the regions themselves, or is exactly `None`. If the dataset's rows are regions, it is not `None`.
7. `description` does not contain the dataset id, and says what *this* dataset measures.
8. `evidence.observation_count` is a count of cells, not a multiple of the row count.
9. The URL answered 200 to a plain GET.
10. Validate and fix every error:
    `python <SKILL_DIR>/scripts/validate_records.py <WORKDIR>/records/<safe_id>.json`

**Never delete or recreate a directory you did not create.** `records/`, `drafts/` and
`catalog/` hold other workers' finished work. Write your own files; touch nothing else.
