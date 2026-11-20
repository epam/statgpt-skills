# Indicators sheets - one sheet per dataset

Every dataset gets its own sheet in the workbook, named with its **Dataset ID** from column D of the `Datasets` tab: `TABEL1_1`'s indicators live on sheet `TABEL1_1`. Each sheet has exactly two columns:

| Indicator | Units of measure |
|---|---|
| broad money (M2) | billions of Rp |
| narrow money (M1) | billions of Rp |

This is the field the search layer actually searches. An indicator that is not listed here will never be found. Read this file in full every run.

Template wording: *"List every indicator the dataset contains - indicators not listed will not be found by the search. Write out breakdowns (by sector, partner country, expenditure division, instrument, tenor) as individual rows, not as a group name."*

**One row per indicator per unit. Breakdowns are written out, never folded.** This is the opposite of summarizing: a table with 17 sectors gets 17 rows, not one row saying "by economic sector".

---

## 1. What an indicator is

> **An indicator is one measured quantity the dataset publishes: the thing a single number in the dataset is a measurement *of*, after you strip away where it was measured, when it was measured, and how often.**

Stripped away, always:

| Stripped | Why | Where it goes instead |
|---|---|---|
| Reference area / region / partner **as an axis** | *where*, not *what* | columns A and B |
| Time period, vintage, release date | *when*, not *what* | column H |
| Frequency | *how often*, not *what* | column I |
| Seasonal / working-day adjustment, preliminary / revised status | a variant of the same measurement | column F |
| Observation status, confidentiality, decimals, footnote flags | not measurements | nowhere |

The unit of measure is **not** stripped - it goes in the second column of the indicators sheet, one unit per row.

A partner country is the one exception to "area is an axis": in bilateral data the counterpart is part of what is measured, and the template names partner country among the breakdowns to write out. `exports to Japan` is an indicator row; the *reporting* country stays in column A.

### The operational test

Point at any single number in the dataset and ask: **"What is this a number of?"** The shortest complete answer that mentions no date and no frequency is the indicator; the unit it is expressed in goes in the unit column.

```
Cell: Indonesia, 2026-07, 9,123,456.78, billions of Rp, stub row "Time deposits (Rp)"
"What is this a number of?" -> time deposits in rupiah
Row: time deposits in rupiah | billions of Rp
```

### The three-question admission test

A label becomes a row only if all three answers are yes:

1. **Measurement** - can a number with a unit be attached to it? (`broad money (M2)` yes; `Monthly` no; `billions of Rp` no)
2. **Not an axis** - is it not a time period, a frequency, a unit, a quality flag, or a reporting area?
3. **Standalone** - would the user question *"what is / was &lt;label&gt;?"* be answerable from this dataset as a time series?

### Indicator is not series

```
series = indicator x reporting area x frequency x time
```

The indicators sheet lists **indicators**, so a dataset covering 38 provinces has the same sheet as one covering the national total. The provinces are named in column B; sectors, partners, instruments and tenors are rows.

---

## 2. Where the rows come from

**Rule I-1.** The sheet lists the dataset's own **published line items, with every breakdown category written out**, and nothing else.

### 2a. Spreadsheet and HTML table sources

The rows are the **stub labels** - every row header of every data block, at every hierarchy level that has numbers next to it - plus the column headers when the columns hold different measured concepts instead of periods or areas.

Read every sheet of every file, including the historical / era sheets. A line item that only exists in the 2002-2017 sheet is still an indicator; it gets a row with a period note (rule I-9).

Where the source publishes several panels of the same measure (one panel per bank group, one per province group), the panels *are* the published cross-product: enumerate them as the source does.

### 2b. Cube sources (SDMX, PxWeb, JSON-stat, OData, Socrata)

1. Identify the **measure dimension** - the one whose codes answer "what is measured". Typical ids: `INDICATOR`, `MEASURE`, `SERIES`, `SUBJECT`, `ITEM`, `VARIABLE`, `CONCEPT`, `TRANSACTION`, `STO`, `FLOW`, `EXPENDITURE`.
2. Identify the **content dimensions** - everything that is not reporting area, time, frequency, unit, adjustment or a status flag: sector, product, partner, instrument, tenor / maturity, purpose, holder, ownership, sex, age, education, expenditure division, bank group.
3. Enumerate the combinations of measure x content dimensions **that actually carry data** (from the availability call), one row each. Compose the row name from the source's own labels, measure first, then the qualifiers.

```
INDICATOR=exports, PARTNER=JPN   ->  exports to Japan                     | millions of USD
INDICATOR=loans,   SECTOR=A      ->  loans to agriculture, forestry and fishery | billions of Rp
```

**Rule I-2 (the 2,000-row guard).** If that cross-product exceeds 2,000 rows for one dataset, expand it marginally instead: every measure code, then every category of each content dimension against the measure total - and say so in column F, in one sentence ("the indicators sheet lists each measure and each sector and each partner separately; the full sector x partner cross-product is not enumerated"). Never silently truncate, never write a folded row instead.

### 2c. Single-measure datasets

A dataset with one measure and several content dimensions (`OBS_VALUE` plus a unit attribute) still gets one row per content combination with data. A genuinely single-series dataset gets one row - that is legitimate, and `--status` flagging it as thin is just asking you to confirm.

---

## 3. Never a row

**Rule I-3.** These never become rows, however prominent they are in the UI:

- reporting areas and sub-national regions (partner / counterpart areas are rows, see section 1);
- time periods, years, quarters, "latest", release vintages;
- frequencies;
- units, currencies, scales, index base periods - the unit column carries those;
- adjustment (seasonally adjusted, calendar adjusted, trend-cycle) and data status (preliminary, revised, provisional) - column F, or a note inside the row name when it applies to that one line item;
- price basis as a separate row when the source publishes only one basis; when it publishes both, current-price and constant-price series are different rows (`GDP at current prices`, `GDP at constant 2010 prices`);
- table, section and chapter headings that carry no numbers of their own;
- the dataset name repeated as an indicator;
- collection, methodology, source-agency and licence metadata;
- a totals or summary row that the source does not itself publish.

---

## 4. Writing out breakdowns

**Rule I-4 (expand).** Every breakdown category the source publishes gets its own row. Sector, partner country, product, instrument, tenor, purpose, holder, ownership, bank group, expenditure division, sex, age - all of them.

```
right: time deposits in rupiah                 | billions of Rp
       time deposits in foreign currency       | billions of Rp
wrong: time deposits, rupiah and foreign currency separately | billions of Rp
wrong: time deposits, by currency (2 currencies) | billions of Rp
```

**Rule I-5 (hierarchies).** Every level that carries numbers gets a row - the aggregate *and* its components, in the source's own order.

```
quasi money                                    | billions of Rp
time deposits in rupiah                        | billions of Rp
time deposits in foreign currency              | billions of Rp
other savings deposits in rupiah               | billions of Rp
other savings deposits in foreign currency     | billions of Rp
```

**Rule I-6 (composing a name).** Use the source's own wording and its own composition style:

- parent, then the qualifier after a comma: `claims on the private sector, loans` / `claims on the private sector, other claims`;
- `of which` rows resolved against their parent: `rupiah demand deposits, of which electronic money`;
- currency and similar splits as a preposition phrase: `time deposits in rupiah`, `deposits in foreign currency`;
- partners and destinations with the source's preposition: `exports to Japan`, `imports from China`, `remittances from ASEAN`;
- keep the classification's own category wording: `loans to wholesale and retail trade and repair of motor vehicles and motorcycles`.

**Rule I-7 (memo items).** Below-the-line memo / "of which" items are rows. Keep the source's marking so the search layer knows their status: `memo item: loans to the Central Government`.

**Rule I-8 (no folding, ever).** Forbidden in a row name: `by <dimension>`, `separately`, `respectively`, `each with`, `breakdown`, `with its members`, a category count in parentheses (`(17 sectors: ...)`), or a comma list standing in for rows. The validator warns on all of these.

**Rule I-9 (era-limited items).** An item with data in only part of the span gets a row, with the limit in the name:

```
import guarantee deposits (1985-2003 sheets only)              | billions of Rp
claims on official entities and state enterprises (pre-2004 sheets only) | billions of Rp
rupiah saving deposits withdrawable at any time (reclassified into M1 since August 2021) | billions of Rp
```

---

## 5. Naming rules

**Rule I-10.**

- English. If the source labels only in the local language, translate, and keep the local term or code in parentheses when users search by it: `value added tax (PPN)`, `Bank Indonesia Certificate (SBI)`.
- Lower case, except proper nouns, acronyms and index names: `GDP`, `M2`, `CPI`, `Bank Indonesia`, `ASEAN`, `State Banks` when that is the published entity name.
- No leading dataset name, no reporting area, no period, no frequency, no unit.
- Expand an acronym once, the first time it appears on the sheet.
- Drop stub numbering and typography (`1.1.`, `a)`, leading dashes, repeated spaces); keep meaningful qualifiers (`gross`, `net`, `outstanding`, `at current prices`).
- One line of text, no newlines. Aim under 120 characters: a longer name is usually a fold that was not written out.
- ASCII punctuation - no curly quotes, no en dashes, no non-breaking spaces. Fix mojibake at the source encoding, not in the text.

**Rule I-11 (no duplicate rows).** Two rows must not be the same measurement in the same unit. The same indicator in two units is two rows (see I-13).

---

## 6. Units of measure

**Rule I-12.** Every row has a unit. The unit column is never blank, and the unit is never repeated inside the indicator name.

| Kind | Write it as |
|---|---|
| Currency with scale | `billions of Rp`, `millions of USD`, `thousands of EUR` |
| Index | `2022=100`, `index, 2015=100` |
| Percent | `percent`, `percent per annum`, `percent of GDP`, `percentage points` |
| Counts | `persons`, `number of establishments`, `number of transactions` |
| Physical | `thousand tonnes`, `GWh`, `barrels per day`, `hectares` |
| Rates and ratios | `ratio`, `per 1,000 live births`, `per 100,000 population` |
| Growth | `percent change year on year`, `percent change from previous period` |

- Use the source's own scale; never rescale the values.
- Index without a stated base: `index, base period not stated by source`. Genuinely unitless: `unitless`. No unit anywhere in the header, footnotes or metadata page: `unit not stated by source` - and only after looking in all three. The parenthetical line **under the sheet title** is where publishers most often put it: `(Ribu USD)` / `(Thousands of USD)`, `(Juta USD)` / `(Millions of USD)`, `(Ribu Ton)` / `(Thousands of Ton)`. On one run 479 rows shipped as "not stated" on export and balance-of-payments tables whose files stated the unit in exactly that place - on tables where the unit is the entire point.

**Rule I-12a (the unit is in English).** A unit copied from the source's own language is not a different unit, it is an untranslated one. `Miliar Rp` is `billions of Rp`; `dalam miliar rupiah` is `billions of Rp`; `Persen Per Tahun` is `percent per annum`; `Ribu USD` is `thousands of USD`. 149 rows on one run carried the untranslated form alongside rows that carried the English one, splitting one unit into two.

**Rule I-12b (sanity-check the unit against what the indicator is).** Before writing a unit, ask whether it could measure that quantity at all. Some illustrative pairs - not a closed mapping, and the source's own unit statement always wins over anything here:

| If the indicator is | it is usually | and is not |
|---|---|---|
| an interest rate, yield, rate of return | `percent per annum` | an amount of money |
| a share, ratio, proportion | `percent`, `percent of GDP`, `ratio` | an amount of money |
| an index | `2022=100` | an amount of money |
| an exchange rate | units of one currency per unit of another, as the source states it | `billions of USD` |
| a headcount | `persons`, `thousands of people` | an amount of money |

Two whole interest-rate tables once shipped with every row marked `Miliar Rp`. An interest rate is not a quantity of rupiah, and the table's own title said so.

This is judgment, so it is **not** in `validate_records.py`: units are unbounded, and a rule built from one portal's vocabulary would be wrong on the next one in ways nobody could predict. `scripts/audit_corpus.py --only units` instead tallies every distinct unit in the corpus for a reader to look at - which is how this was found. One record at a time it looked plausible; as a list of 24 distinct units it did not.

**Rule I-13 (one row per unit).** An indicator published in two units is two rows:

```
central government debt      | billions of Rp
central government debt      | percent of GDP
```

---

## 7. What must not be listed

**Rule I-14 (evidence).** A row requires at least one non-empty observation. A line item declared in a codelist, or sitting in the source as an empty stub, is not published data - leave it out, and if the portal advertises it prominently, say so in column F ("the published structure also declares X, which currently carries no data").

**Rule I-15 (completeness).** No truncation, no sampling, no "main indicators". If a table has 240 published line items, the sheet has 240 rows.

---

## 8. Sheet mechanics

- Sheet name = the dataset's ID from column D of `Datasets`: `TABEL1_1`, `IMF.STA-DOT(2.0.0)`. `build_workbook.py` derives it from each record's `dataset_id`, so a row and its sheet cannot drift apart. Excel allows at most 31 characters and none of `:` `\` `/` `?` `*` `[` `]`, so an ID that does not fit is reshaped - by the script, once, for the whole workbook, with the reshaped form written into column D and every change printed. Never reshape one by hand in a record.
- Row 1 is exactly `Indicator` | `Units of measure`. No extra columns, no blank rows between rows, no totals row, no colour coding.
- Order: the source's own order (stub order, or codelist order). It carries the publisher's hierarchy and makes review possible.
- Expect roughly 10-200 rows for a normal statistical table. Under 3 rows means the table was collapsed; `compile_index.py --status` and `next_batch.py --thin` list those datasets so they can be re-run.

---

## 9. Worked examples

### 9a. Monetary aggregates table (the template's own example, sheet `TABEL1_1`)

Source stub rows: `Broad Money (M2)`, `Narrow Money (M1)`, `Currency outside commercial banks and rural banks`, `Rupiah demand deposits`, `- of which: electronic money`, `Foreign currency demand deposits`, `Quasi Money`, `Time deposits (Rp)`, `Time deposits (FX)`, `Savings deposits (Rp)`, `Savings deposits (FX)`, `Securities other than shares`, `Factors affecting Broad Money`, `Net foreign assets`, `Claims on non-residents`, `Liabilities to non-residents`, ... plus pre-2004 items.

```
broad money (M2)                                        | billions of Rp
narrow money (M1)                                       | billions of Rp
currency outside commercial banks and rural banks       | billions of Rp
rupiah demand deposits                                  | billions of Rp
rupiah demand deposits, of which electronic money       | billions of Rp
foreign currency demand deposits                        | billions of Rp
quasi money                                             | billions of Rp
time deposits in rupiah                                 | billions of Rp
time deposits in foreign currency                       | billions of Rp
other savings deposits in rupiah                        | billions of Rp
other savings deposits in foreign currency              | billions of Rp
securities other than shares                            | billions of Rp
factors affecting broad money                           | billions of Rp
net foreign assets                                      | billions of Rp
claims on non-residents                                 | billions of Rp
liabilities to non-residents                            | billions of Rp
...
import guarantee deposits (1985-2003 sheets only)       | billions of Rp
claims on official entities and state enterprises (pre-2004 sheets only) | billions of Rp
```

36 rows for a table that a folded style would have squeezed into 20 entries. Note what happened: the currency split became two rows each, `of which` was resolved against its parent, aggregates kept their own rows alongside their components, and the era-limited items kept a note.

### 9b. Loans by bank group and economic sector

The source publishes one panel per bank group, each panel broken down by 17 sectors. Both dimensions are written out, following the published panels:

```
outstanding loans in rupiah and foreign currency, all bank groups                      | billions of Rp
outstanding loans in rupiah and foreign currency to agriculture, forestry and fishery  | billions of Rp
outstanding loans in rupiah and foreign currency to mining and quarrying               | billions of Rp
... one row per sector ...
outstanding loans of State Banks to agriculture, forestry and fishery                  | billions of Rp
... one row per sector per published bank-group panel ...
outstanding loans to household consumption, housing                                    | billions of Rp
outstanding loans to household consumption, vehicles                                   | billions of Rp
```

Wrong, and what the validator warns about:

```
outstanding loans by economic sector (17 sectors of the classification used since 2018: agriculture, ...) | billions of Rp
outstanding loans of State Banks by economic sector and household consumption | billions of Rp
```

### 9c. Bilateral trade dataflow

`DIM: FREQ, REF_AREA, COUNTERPART_AREA, FLOW, TIME_PERIOD`. The reporting country is column A; `partner countries:` also goes in column A; the partner breakdown is written out as rows.

```
exports, free on board, to Japan          | millions of USD
exports, free on board, to United States  | millions of USD
imports, cost insurance and freight, from Japan | millions of USD
trade balance with Japan                  | millions of USD
```

### 9d. SDMX dataflow with an INDICATOR dimension

`DIM: FREQ, REF_AREA, INDICATOR, UNIT_MEASURE, TIME_PERIOD`, `INDICATOR` with 12 codes of which 10 carry data, two of those in two units.

12 rows: one per code with data, named from the codelist's English label, plus the second unit rows (I-13). The two empty codes are omitted (I-14) and mentioned in column F.

---

## 10. Self-check before finishing a dataset

A "no" means fix the sheet, not explain it.

1. Does every row have a non-empty unit, in English, of the right kind for that indicator (I-12a, I-12b), and is the unit absent from the indicator name?
2. Is any row a fold - `by <dimension>`, `separately`, `respectively`, a category count, a comma list standing in for rows?
3. Did every row come from a source label, not from a phrase you invented? Does any name repeat one of its own comma-separated parts - the signature of a label qualified with its sibling instead of its parent?
4. Does every row have at least one real observation behind it?
5. Are all hierarchy levels present - aggregates *and* components?
6. Are partner, sector, instrument, tenor and purpose categories written out individually?
7. Are era-limited and memo items marked?
8. Any duplicate indicator + unit pair?
9. Does the row count look like the table (10-200 typical; under 3 means collapsed; over 2,000 needs the I-2 note in column F)?
10. Would a user asking about the smallest line item in this table be routed here by this sheet?
