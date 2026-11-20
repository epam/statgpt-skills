# Datasets tab, columns A-I - field rules

One record per dataset, one row on the `Datasets` tab. Each section below gives: what the field is for, the source of truth, the derivation procedure, the output grammar, and wrong/right pairs.

The dataset's indicators are **not** on this tab: every dataset has its own indicators sheet, named with its **Dataset ID** from column D. That is `references/indicators.md`.

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

There is no dataset number and no "excluded regional values" column. Both were dropped: the dataset's own ID now identifies the row and names its sheet, and regional coverage now enumerates the regions that ARE present, so a region the dataset lacks is simply absent from column B.

Conventions used here: `<>` is a placeholder, `|` alternatives, `[]` optional. All cells are plain text, single paragraph unless stated, ASCII punctuation, English.

---

## A - Reference area / country

**Purpose.** Lets the search layer decide whether this dataset can answer a question about a given country.

**Source of truth.** The area codes that carry **at least one non-empty observation** (Step 4), not the full area codelist and not the portal's blurb.

**Procedure.**
1. Collect the area codes with data.
2. Map each to its English country name and ISO 3166-1 alpha-3 code. Use the standard English short name (`Vietnam`, `South Korea`, `Russia` are acceptable; keep the source's form when it is the official one).
3. Codes that are not countries (aggregates, economic zones, "World") keep their group label and get no ISO3.
4. If the dataset is bilateral (it has a partner / counterpart area dimension), split into reporting areas and partner areas.

**Grammar.**
```
<Name> (<ISO3>)[; <Name> (<ISO3>)]...
<Name> (<ISO3>); partner countries: <Name> (<ISO3>); <Group label>; ...
```

**Rules.**
- Separator is `"; "`. Name and code exactly as `Name (ISO3)`, one space before the parenthesis.
- List every country out, however many there are. Do not compress to a region name.
- A group label (`Euro area`, `World`, `ASEAN`) is allowed, but note in `run.md` that the search may fail to match it to a member-country question; if the members are individually present in the data, list the members too.
- Bilateral data: reporting countries first, then the literal token `partner countries:` and the partner list. Partner group headings from the source (`Europe`, `European Union`, `Other Africa`) may be kept in place, in source order, because they are themselves published aggregates.
- A note that belongs to one code goes inside its parentheses: `People's Republic of China (CHN, including Hong Kong SAR since 1998)`.

**Wrong / right.**
```
wrong: Asia-Pacific economies
right: Indonesia (IDN); Malaysia (MYS); Singapore (SGP); Thailand (THA)

wrong: IDN
right: Indonesia (IDN)

wrong: Indonesia and 47 partner countries
right: Indonesia (IDN); partner countries: United States of America (USA); Japan (JPN); ...
```

---

## B - Regional coverage

**Purpose.** Whether the dataset can answer a question about a given sub-national region.

**This field changed.** It used to name the *levels* a dataset was broken down by (`provinces, municipalities`). It now names **every region the dataset covers, each with its level in parentheses**. The template states the reason plainly: *regions not listed will not be found by the search.* A search layer cannot match a question about Aceh to the word "provinces", so a cell that names only levels routes nobody.

**Source of truth.** The sub-national area codes that carry **at least one non-empty observation** - not the codelist, not the portal's blurb.

**Procedure.**
1. Collect the sub-national area codes with data.
2. Map each to the region's English name.
3. Give each its level in parentheses, using **whatever the source and the country call that level** - `(province)`, `(state)`, `(prefecture)`, `(county)`, `(municipality)`, `(voivodeship)`, `(NUTS 2 statistical region)` are examples, not a list to pick from. There is no closed vocabulary of sub-national levels, so use the source's own term rather than mapping it onto a familiar one; nothing downstream validates the word you choose.
4. National-total-only dataset: the answer is exactly `None`.

**Grammar.**
```
None
<Region> (<level>)[, <Region> (<level>)]...                    # column A holds one country
<Country> (<ISO3>): <Region> (<level>)[, ...][; <Country> (<ISO3>): <Region> (<level>)...]
```

**Rules.**
- Regions are comma-separated; country pairs are semicolon-separated.
- **Write them all out.** Thirty-eight provinces are thirty-eight entries. This is the same rule as the indicators sheets: an unlisted value is invisible forever.
- The level goes in parentheses after every region, not once at the end of the list.
- `None` is written when and only when the dataset has no sub-national breakdown at all. It is never left empty.
- Statistical, non-administrative regions carry that in the level: `Lombardia (NUTS 2 statistical region)`.
- A region the dataset does **not** cover is simply absent from this cell. There is no longer a separate column for it; if a user would reasonably expect a region that is missing, say so in column F.
- A region present but empty for its whole span does not belong here (data beats metadata).

**Wrong / right.**
```
wrong: (empty)                    right: None
wrong: regional                   right: Aceh (province), Bali (province), Banten (province)
wrong: provinces, municipalities  right: Aceh (province), Bali (province), Bandung (municipality)
wrong: 38 provinces               right: ... all 38 named, each with (province)
right: United States (USA): California (state), Texas (state); Japan (JPN): Tokyo (prefecture)
```

A dataset whose indicator rows *are* regions is a regional dataset whatever its title says. Four province tables on a real run shipped with `None` here, which was found only by tallying this column across every record at once - `scripts/audit_corpus.py --only regions` does that.

---

## C - Agency / organization

**Purpose.** Attribution, and disambiguation between similarly named datasets from different publishers.

**Source of truth.** The publisher's own English name, from the site's About / Imprint / Contact page or the SDMX agency scheme.

**Grammar.**
```
<Official English name> (<ACRONYM>)
<Lead name> (<ACR>) / <Second name> (<ACR>)        # jointly published
```

**Rules.**
- Official English name, spelled as the organization spells it, plus its acronym in parentheses. The acronym is mandatory when one exists.
- Do not substitute the portal's brand name for the institution (`Bank Indonesia (BI)`, not `SEKI`).
- Aggregator portals: the agency is the **originating** publisher of that dataset, not the aggregator - unless the aggregator is itself the publisher of the compiled dataset, in which case name the aggregator.
- Keep the same string for every row of the same publisher, character for character.

---

## D - Dataset ID

**Purpose.** Two things at once: stable, checkable identity, and the **name of the dataset's indicators sheet**. `TABEL1_1`'s indicators are on sheet `TABEL1_1`.

**Source of truth.** The source's own identifier.

**Procedure, in order - use the first that exists.**
1. The source's published ID, verbatim and case-sensitive (SDMX `AGENCY:ID(version)`, CKAN name, PxWeb table id, cube id).
2. The table or cube code that appears in the URL (`TABEL1_1` from `/SEKI/tabel/TABEL1_1.xls`).
3. The file stem of the published file, when the file is the only identity the source gives.

**Rules.**
- Never normalize case, never strip a version suffix, never translate, never add a prefix of your own.
- No surrounding whitespace; no trailing punctuation.
- **Unique across the agency.** The template says so outright: "Dataset ID must be unique across Agency." No two rows with the same column C may share a column D. If two datasets would end up with the same ID, you have merged two sources or split one dataset - go back to the granularity sentence from Step 1. Never fix a clash by inventing a suffix in the record; `validate_records.py` stops the build on any repeated ID. (In practice the whole workbook has to be unique anyway, because the ID names a sheet and sheet names are unique per workbook.)

**The Excel sheet-name limit.** Because the ID names a sheet, Excel's limits are the ID's limits: **at most 31 characters, and none of `:` `\` `/` `?` `*` `[` `]`**. Where the source's own ID does not fit, the template says to shorten it or replace those characters with `-`, and column D then carries the shortened form.

Do not do this by hand. Keep the source's verbatim ID in the record; `build_workbook.py` derives the sheet name once, for the whole workbook, writes that form into column D, and prints every ID it had to reshape. Deriving it in one place is what stops a row and its sheet drifting apart - and only a whole-workbook view can notice that two different IDs collapse onto the same 31 characters, which would otherwise lose one dataset's indicators with no error anywhere.

**Wrong / right.**
```
wrong: imf-dot / dot / DOT dataset
right: IMF.STA:DOT(2.0.0)      -> column D and the sheet read IMF.STA-DOT(2.0.0)
wrong: tabel1_1
right: TABEL1_1
```

---

## E - Dataset name

**Purpose.** Human identification; a strong search signal.

**Source of truth.** The official published title.

**Rules.**
- The official title in English, as published, including its numbering when the source numbers its tables (`I.1. Broad Money and its Affecting Factors`).
- Keep the source's capitalization and any parenthetical acronym (`Direction of Trade Statistics (DOTS)`).
- No English title published: translate literally and append the original in parentheses - `Consumer price index (Indeks Harga Konsumen)`.
- Do not append the agency, the frequency, the year range or the file format.
- Do not shorten, do not rewrite for style, do not deduplicate against column H.

---

## F - Description

**Purpose.** The sentence a search layer reads to decide between two datasets with similar titles.

**Must cover, in this order.**
1. **What is measured** - the subject matter and the statistical universe (who / what is counted).
2. **How it is broken down** - the dimensions, and for classifications, the classification name *and version* (`ISIC Rev. 4`, `COICOP 2018`, `the 17-sector classification used since 2018`, `NUTS 2021`).
3. **Value status** - whether values are seasonally or calendar adjusted, preliminary, provisional, revised, projected, or carry breaks in series, and how the source flags them (`the latest month is flagged with an asterisk`).

**Rules.**
- Plain English prose, 40-180 words, single paragraph, no newlines, no bullets, no markdown. 40 is a floor, not a target to skim under.
- Concrete over promotional: no "comprehensive", "rich", "valuable", "one-stop".
- No URLs, no email addresses, no licence text, no navigation instructions.
- **Never name the dataset's own ID.** The ID is column D; a description that has to mention it is describing a file, not a measurement. On a real run six records read *"This table presents TABEL9_3 data compiled by Bank Indonesia from official sources"* - which named no measurement at all and made inflation, the current account, exports, reserve assets and policy rates indistinguishable to a search layer. Every other check passed them.
- Two datasets may open with the same sentence only if the very next clause states what distinguishes them (rupiah vs foreign currency, production vs expenditure side, country of origin vs currency of invoice). Check with `scripts/audit_corpus.py --only descriptions`, which groups every description by its opening.
- Name the publication or section the dataset belongs to when the source does (`Section I. Money and Banking of the Indonesian Economic and Financial Statistics (SEKI)`).
- State what is **not** covered when a user would reasonably expect it (`services are not covered`).
- Mention structurally declared but empty items here (see rule I-14 in `indicators.md`).
- Do not restate column B, J, K verbatim; a short reinforcement of scope is fine.

**Skeleton that satisfies the three requirements.**
```
<What> for <universe>, published in <publication/section>. Broken down by <dimensions>, using <classification and
version>. Values are in <unit/valuation>. <Adjustment / preliminary / revision / break statement>. <What is not
covered.>
```

---

## G - Dataset URL

**Purpose.** Where the user is sent.

**Rules.**
- The **deepest stable public** `https://` URL for this dataset: the dataset page, the table page, the cube page, or the direct file when the source publishes nothing deeper.
- English page when the site has one; otherwise the canonical page.
- Must return 200 to a plain GET with no cookies. Verify each one.
- No session ids, no auth tokens, no expiring signatures, no UI state fragments, no `#!`-only anchors that require JS to resolve, no search-result URLs, no redirects to a login.
- Prefer a human-readable landing page over an API endpoint; use the API endpoint only when no landing page exists.
- One URL per row. If the dataset spans several files, use the landing page that links them all; if none exists, use the current-era file and note it in `run.md`.

---

## H - Time coverage

**Purpose.** Whether the dataset can answer a question about a given period.

**Source of truth.** The minimum and maximum periods with a **non-empty** observation. Empty or zero-filled periods, and periods that exist only as column headers, do not count. Never read this off a sheet name, a title, or a portal blurb.

**Grammar.**
```
From <period> to <period>
From <period> to present (latest available <period>)
```
`<period>` is written at the dataset's own granularity:
```
YYYY | YYYY-Qn | YYYY-Hn | YYYY-MM | YYYY-MM-DD | YYYY-Www
```

**Rules.**
- **The latest available period is the latest non-empty observation across ALL frequencies**, not the end of whichever block you happened to read. A record on a real run said "latest available 1989" while its own evidence recorded monthly data to 2026-07: 1989 was simply where the annual block stopped. A frequency that ends earlier goes in the trailing note.
- `to present (latest available <period>)` when the dataset is still being updated: the source states it is ongoing, or its latest observation is within two of its own publication cycles of today.
- A **fiscal-year** header (`1984/85`) names a year that starts in 1984 and ends in 1985. Say which convention you used in the trailing note; the drafter flags such sheets with `fiscal_year_columns`.
- A fixed end (a discontinued dataset, or projections that end at a stated horizon) is written as the explicit period.
- Several frequencies: give the overall span, then put the differing starts, the breaks, the projection horizon and the frequency-specific starts in parentheses or after a comma:
  ```
  From 1985 to present (latest available 2026-07), monthly from 1989-01
  From 1980 to 2031 (projections from 2026)
  From 1960-01 to present (latest available 2026-05)
  ```
- Gaps inside the span are stated when a user would hit them: `(no data for 1998-2000)`.
- Use the finest granularity that the span's start actually supports: if annual data starts in 1985 and monthly in 1989-01, the span starts `1985` and the monthly start is noted.

**Wrong / right.**
```
wrong: 1985-2026            right: From 1985 to present (latest available 2026-07)
wrong: since the 1980s      right: From 1989-01 to present (latest available 2026-07)
wrong: From 1985 to 2030 (the sheet is named 1985-2030, columns after 2026-07 are empty)
right: From 1985 to present (latest available 2026-07)
```

---

## I - Frequency coverage

**Purpose.** Whether the dataset can answer at the cadence the question implies.

**Closed vocabulary** - use these spellings, nothing else:
```
Daily; Business daily; Weekly; Monthly; Quarterly; Semi-annual; Annual; Irregular
```

**Procedure.**
1. Take the frequencies that actually carry observations.
2. Map source codes: `D` -> Daily, `B` -> Business daily, `W` -> Weekly, `M` -> Monthly, `Q` -> Quarterly, `S`/`H` -> Semi-annual, `A`/`Y` -> Annual, anything event-based or with no fixed cadence -> Irregular.
3. Derive it from the observed period stamps when the source declares no frequency.

**Rules.**
- Separator `"; "`, in the vocabulary's own order (Daily, Business daily, Weekly, Monthly, Quarterly, Semi-annual, Annual, Irregular).
- Only frequencies with data. A dataset whose annual column is empty is `Monthly`, not `Monthly; Annual`.
- Do not invent frequencies by aggregation: monthly data that a user could sum to annual is still `Monthly`.
- `Irregular` for ad-hoc, census, survey-round and event-based releases with no fixed cadence.

**Wrong / right.**
```
wrong: monthly            right: Monthly
wrong: Annual; Monthly    right: Monthly; Annual
wrong: Biannual           right: Semi-annual
wrong: M; Q; A            right: Monthly; Quarterly; Annual
```

---

## Cross-field consistency checks

Run these before closing a row:

1. Column B names a region -> column A contains the country that region belongs to.
2. Column B is not `None` -> every entry carries its level in parentheses.
3. The dataset's indicator rows are regions -> column B is not `None`, and it names those regions.
4. Column A says `partner countries:` -> column F says the data is bilateral, and the indicators sheet has one row per partner (`exports to Japan`), not one row saying "by partner country".
5. Column H's granularity is consistent with column I: a `YYYY-MM` span implies `Monthly` is in I.
6. Column H says `to present` -> the latest observation is genuinely recent for that frequency, and is the latest across all of them.
7. Column F names a classification -> the indicators sheet uses that same classification's category wording, one row per category.
8. The units on the indicators sheet match the units column F states, and each unit is the right **kind** for its indicator: a rate, a ratio, an index or a share is never an amount of money.
9. Column F does not contain column D.
10. Columns C, D, E, G all refer to the same dataset: G resolves to a page that shows the E title and the D identifier.
11. A sheet named with column D exists and is not empty.

Checks 1-3 and 8-9 are the ones a well-formed record fails silently. `scripts/validate_records.py` makes every mechanical part of them, and `scripts/audit_corpus.py` makes the rest by tallying one field across every record at once.
