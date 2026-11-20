# Source adapters - detection, enumeration, structure, data

Run the probes in order. The first that answers is your adapter. Log the adapter and its base endpoints in `run.md` before you crawl anything.

Always: identify with a normal browser user agent, obey `robots.txt`, cache every response under `raw/`, retry 429/5xx with exponential backoff, and keep concurrency at 2-4 requests.

---

## 0. Universal probes

Try these against the portal host before assuming there is no API:

```
GET  /robots.txt                      # and any sitemap it names
GET  /sitemap.xml
GET  /api                             # many portals self-document here
GET  /swagger/index.html  /openapi.json  /swagger/v1/swagger.json
GET  /.well-known/dcat                # DCAT-AP catalogues
GET  /data.json                       # US-style catalogue
GET  /catalog.json  /catalogue.xml
```

And, decisive when nothing else is: **open the data explorer in a browser and watch the network tab**. Whatever XHR the UI fires to fill its dataset list and its chart is the API you should use. Any browser-automation tool your runtime offers - Playwright, Puppeteer, Selenium, or a built-in browser tool - can dump that request list after you drive the UI once.

---

## 1. SDMX (.Stat Suite / dotstat, ECB, IMF, Eurostat, BIS, OECD, national .Stat instances)

**Detect.** URL or page contains `/sdmx`, `/rest/`, `dataflow`, `SDMX-JSON`, `.Stat`, `dotstatsuite`, `sdmxcentral`; or the UI XHRs hit `/rest/data/...`.

**Enumerate datasets.**
```
GET {base}/rest/dataflow/all/all/latest?format=sdmx-json          # 2.1
GET {base}/rest/dataflow?format=sdmx-json                          # 3.0
Accept: application/vnd.sdmx.structure+json;version=1.0
```
One dataflow = one dataset. Column D = `AGENCY:ID(VERSION)`; note that a `:` is not legal in an Excel sheet name, so the build writes `AGENCY-ID(VERSION)` into column D (field-rules D).

**Structure.**
```
GET {base}/rest/datastructure/{agency}/{dsdId}/latest?references=all&format=sdmx-json
GET {base}/rest/dataflow/{agency}/{id}/latest?references=all
```
Gives dimensions, codelists, concept schemes, and the `UNIT_MEASURE` / `UNIT_MULT` / `BASE_PER` attributes. The measure dimension is the one whose concept is a measure or indicator concept (see `indicators.md` section 2a).

**Data, cheaply.**
```
GET {base}/rest/availableconstraint/{flowRef}/all/all?mode=exact&references=none   # 2.1 codes with data
GET {base}/rest/availability/{context}/{key}/{componentId}                          # 3.0
GET {base}/rest/data/{flowRef}/all?lastNObservations=1&format=csv
GET {base}/rest/data/{flowRef}/all?firstNObservations=1&format=csv
GET {base}/rest/data/{flowRef}/all?format=csv                                       # full pull, last resort
```
`availableconstraint` is the single most useful call in this skill: it returns, per dimension, only the codes that actually carry data, plus the time range. That answers columns A, B, I and the candidate indicator rows in one request - and it tells you which breakdown combinations actually carry data, which is exactly what has to be written out row by row (indicators.md, rule I-1).

**Notes.** `dimensionAtObservation=AllDimensions` for flat JSON. Some servers cap response size - then page by the first dimension's codes. Version suffixes matter: keep `(1.0)` / `(2.0.0)` in column D exactly as returned.

---

## 2. PxWeb (Nordic and many European NSIs, and lots of others)

**Detect.** `/pxweb/`, `/api/v1/{lang}/`, `px-x-` table ids, `PxWebApi`.

**Enumerate.** Walk the tree from the database root; nodes are folders, leaves are tables.
```
GET {base}/api/v1/en/                          # databases
GET {base}/api/v1/en/{db}/                     # folders
GET {base}/api/v1/en/{db}/{path}/              # until leaves with "type":"t"
GET {base}/api/v2beta/tables?pageSize=1000     # PxWeb 2 API, if present
```
One table = one dataset; column D = the table id (`px-x-0102020000_101`, `TABEL07`).

**Structure.**
```
GET {base}/api/v1/en/{db}/{path}/{table}       # variables + values + valueTexts
```
The variable named `Contents` / `Tabellinnhold` / `Indicator` is usually the measure dimension.

**Data.**
```
POST {base}/api/v1/en/{db}/{path}/{table}
{"query":[{"code":"Tid","selection":{"filter":"all","values":["*"]}}],"response":{"format":"json-stat2"}}
```
PxWeb enforces a cell cap (often 100k, and a request-per-10s limit). Split by the largest dimension and keep to the rate limit; json-stat2 `status` marks the empty cells, which is what column H needs.

---

## 3. CKAN / DKAN / DCAT portals (data.gov style, many open-data portals)

**Detect.** `/api/3/action/`, `/dataset/` listing pages, `package_search` in the UI XHRs.

**Enumerate.**
```
GET {base}/api/3/action/package_list
GET {base}/api/3/action/package_search?rows=1000&start=0        # has "count" -> completeness gate
```

**Structure + data.** Each package has `resources`; download every distribution (CSV, XLSX, JSON, SDMX). The resource files are the only real structure; CKAN metadata is frequently stale, so derive columns A, B, H, I from the files. `datastore_search` works when the resource was ingested:
```
GET {base}/api/3/action/datastore_search?resource_id={id}&limit=5
GET {base}/api/3/action/datastore_search_sql?sql=SELECT min(...),max(...) FROM "{id}"
```

**Granularity.** One CKAN package = one dataset, even with several resources. A package whose resources are yearly files is still one dataset (rule 7).

---

## 4. JSON-stat, OData, Socrata, ArcGIS

- **JSON-stat**: `class:"dataset"`, `dimension`, `value`. The `status` array marks missing cells - use it for column H. Catalogue via a `class:"collection"` document.
- **OData** (`/odata/v4/`, `$metadata`): `GET {base}/$metadata` for entity sets (datasets), `?$top=1&$orderby=Period asc|desc` for the span, `?$apply=groupby(...)` for the code sets.
- **Socrata** (`/api/views`, `/resource/{id}.json`): `GET {base}/api/views?limit=1000` enumerates; SoQL `$select=min(:period),max(:period)` bounds time.
- **ArcGIS / Feature services** (`/FeatureServer/0/query`): `?returnCountOnly=true`, `?outStatistics=[...]` for min/max, `?f=json` on the layer for fields.

---

## 5. Plain HTML + files (Bank Indonesia SEKI, many central banks and ministries)

**Detect.** No API anywhere; the portal is a page of links to `.xls`, `.xlsx`, `.csv`, `.pdf`, or a numbered table list.

**Enumerate.** Crawl the listing pages exhaustively, collect every file link and the table number / title next to it. Group files by table code: `TABEL1_1.xls`, `TABEL1_1_2002_2017.xls` are **one** dataset. The table code is column D; the deepest stable file or table URL is column G.

This enumeration is usually worth **mechanizing rather than delegating**: one static listing page, one small parser, and the orchestrator pays no context because only the counts are printed. Have a separate worker prove the result complete.

**Listing-page markup is often malformed.** A `<tr>`-based parse of one real central-bank page matched nothing while 108 `.xls` links were plainly present: the rows opened with `<td>` and only `</tr>` ever closed them. Splitting on the *closing* tag gave all 108. The lesson generalizes into a check: **count the file links and the parsed rows separately, and disbelieve the parser when they disagree.** That contradiction is the only reason anyone noticed.

**Structure + data.** Download each file, then open **every sheet**:
- read the header rows to find period columns and unit statements;
- read the stub column as the line-item list (`indicators.md` 2a), remembering that a bilingual publisher may repeat the labels in English in a far-right column under a header like `Items`;
- read the line under the sheet title - it very often carries the unit, e.g. `(Thousands of USD)`;
- read the footnote block - it carries the units, the `r` / `*` flags, and the classification version;
- treat each era sheet as its own layout; union the line items, note era limits per rule I-9.

Tooling: `.xlsx` with `openpyxl`. For `.xls`, **check the toolchain before you plan around it** - the documented `libreoffice --headless --convert-to xlsx` path assumes LibreOffice is installed, and plenty of machines have no LibreOffice. A short script with `xlrd` (read) and `openpyxl` (write) converts a whole tree without it: every sheet, every cell, numbers as numbers.

Whichever you use, watch for the trap that a hand-rolled converter walks straight into: a publisher writes a **year** header (2005) in a cell Excel has formatted as a date, so the stored value is the serial `2005`, and `xldate_as_tuple` turns it into `1905-06-28`. That produced period spans starting `1905-07` on 34 datasets. A date-typed cell whose raw value is a plausible year *is* a year; real period serials are far larger.

`pandas.read_excel(..., sheet_name=None, header=None)` shows the raw grid before any header inference. Never let pandas guess the header row for a stub-and-era layout.

**PDF-only datasets.** Extract the tables only if they are machine-extractable and you can verify the numbers; otherwise mark the row partial and say so. Do not transcribe by eye.

**Probing for unlisted files.** A numbering gap in a table series (`TABEL5_40`, then `TABEL5_42`) may hide a published dataset the index page forgot. Two rules make such a probe trustworthy:

1. **Identify a hit by content, not by status.** Many hosts answer `200` with an HTML error page for a file that does not exist, so a status code proves nothing. Check the content type *and* the magic bytes (`D0 CF 11 E0` for legacy `.xls`, `PK..` for `.xlsx`). Read the decoded body, not a raw stream - reading a still-gzipped body is what made one probe report zero hits for every code, including files that demonstrably existed.
2. **Run the probe against a file you know exists, first.** If it cannot return true for that, its verdicts are worthless. The final URL sweep of column G follows the same rule: check a known-good URL first, and do not trust the sweep until that check passes.

A dataset found this way is real and public, so include it - and say in its record and in `run.md` that it is unlisted, so a reviewer who disagrees can drop one row.

---

## 6. JavaScript-only explorers with no documented API

**Procedure.**
1. Open the explorer with whatever browser automation you have (Playwright, Puppeteer, Selenium, a runtime browser tool). With none available, do this step by hand in a normal browser and copy the two request URLs out of the network tab.
2. Do one full interaction by hand: pick a dataset, open the table, change a filter.
3. Dump the network requests. Identify the catalogue call and the data call.
4. Reproduce those calls with `curl` / `requests`, including the headers the app sends (`Accept`, `X-Requested-With`, any public API key visible in the bundle).
5. Only if that fails: drive the UI for every dataset and read the rendered DOM. Log that this is what you did, because it is slow and fragile.

Do not defeat a CAPTCHA, a login wall or a paid tier. Mark those datasets unreachable.

---

## 7. Aggregator portals

When the portal republishes other agencies' data (a data commons, a national aggregator, a DCAT harvester), resolve column C per dataset from the originating publisher field, and prefer the originator's own deep URL for column G when the aggregator exposes it. Note the aggregator in column F if it did the compiling.

---

## 8. Per-dataset evidence to record

Whatever the adapter, store in the record's `evidence`:

```
structure_urls[]        the structure calls or files you read
data_urls[]             the data calls or files you read
observation_count       non-empty observations seen
period_min_max{}        per frequency, [min, max] of non-empty periods
areas_with_data[]       area codes with at least one non-empty observation
items_with_data{}       line item -> non-empty observation count
data_read               "full" | "partial"
```

This is what makes a row checkable by someone who did not run the crawl, and it is what you cite in the final report.

`observation_count` and `period_min_max` are the two a script can recount, which makes them the two that catch a fabricated record: `scripts/audit_corpus.py --only drafts` compares them against the mechanized draft. Write them as counts you actually made, never as a multiple of the row count.
