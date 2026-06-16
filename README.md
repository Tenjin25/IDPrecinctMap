# IDPrecinctMap

Interactive Idaho election map and data workspace. The app is a single-page frontend in `index.html` backed by prebuilt JSON, CSV, and GeoJSON assets under `data/`.

The repository mixes two concerns:

- a browser app for exploring statewide, congressional, state house, and state senate results
- a build workspace for generating contest payloads, district-line derivatives, crosswalks, and validation reports

## What is in this repo

- `index.html`
  - the full frontend application
  - loads county, precinct, district, contest, demographics, and crosswalk data directly from `data/`
- `data/`
  - source-year election folders such as `data/1994`, `data/1998`, `data/2022`, `data/2024`
  - generated statewide contest payloads in `data/contests`
  - generated district contest payloads in `data/district_contests_2022_lines` and `data/district_contests_2026_lines`
  - legacy district payloads in `data/district_contests`
  - supporting geometry, crosswalks, CVAP, demographics, centroids, and reports
- `scripts/`
  - Python and Node build scripts for contest generation, district derivation, census assets, and validation
- `package.json`
  - minimal Node dependency file; this repo currently uses `xlsx` and `playwright`

## Key data products

### County/statewide contest payloads

`data/contests/`

These are the county-level contest slices used by the county view dropdown and by county aggregation logic in the app. The manifest is:

- `data/contests/manifest.json`

Each payload is named like:

- `governor_2022.json`
- `state_treasurer_1998.json`
- `secretary_of_state_2002.json`

These payloads are generated from source CSVs and include county rows plus contest metadata.

### District contest payloads

There are three district contest directories in the repo:

- `data/district_contests`
  - legacy 2022-era district payloads
  - kept as a fallback
- `data/district_contests_2022_lines`
  - current derived dataset for 2022 district lines
  - this was previously named `district_contests_2024_lines`
  - the rename reflects the real line vintage: the 2024 cycle is still using 2022 lines
- `data/district_contests_2026_lines`
  - derived district payloads for 2026 lines

`index.html` is now wired so:

- the primary district contest directory is `data/district_contests_2022_lines`
- the old `data/district_contests` directory is treated as a legacy fallback
- 2026-line district views load from `data/district_contests_2026_lines`
- 2022-line state house seat selectors may also pull `state_house_a` / `state_house_b` from the legacy fallback directory when those seat entries are not present in the renamed 2022-lines manifest
- canonical Idaho house manifests now prefer one `state_house` entry per year, backed by `state_house_state_house_<year>.json` files with seat-level rows keyed like `19A` and `19B`

### Reports

`data/reports/`

Useful generated outputs include:

- `district_contest_validation_report.json`
- `district_contest_validation_summary.csv`

These are produced by the validation script after district contest regeneration.

## Current contest-loading setup

The frontend uses manifest-driven loading.

For county/statewide contests:

- `index.html` reads `data/contests/manifest.json`
- the county dropdown is populated from that manifest
- payloads are loaded by filename from `data/contests/`

For district views:

- `index.html` resolves the active district-lines year
- it selects the appropriate manifest directory from `data/district_contests_2022_lines` or `data/district_contests_2026_lines`
- it falls back to legacy `data/district_contests` only when needed

District VoteHub tooltips are intentionally compact:

- top line: district code such as `CD-01`, `HD-19`, or `SD-14`
- second line: chamber label such as `Congressional District`, `State House`, or `State Senate`
- Idaho state house remains double-stacked for seat A / seat B, but each stacked card uses the same compact header pattern

For Idaho state house specifically:

- the frontend now prefers unified `contest_type: "state_house"` payloads
- older `state_house_a` / `state_house_b` requests are treated as compatibility aliases
- the selector should show one `State House (year)` option instead of separate seat A / seat B options when a canonical yearly payload exists

The frontend also normalizes statewide office keys so older aliases and current payload names resolve consistently:

- `treasurer` <-> `state_treasurer`
- `controller` <-> `state_controller`
- `auditor` <-> `state_auditor`
- `superintendent` <-> `superintendent_public_instruction`

That normalization matters because historical payloads and UI labels have not always used the same contest key names.

## Cache busting

`index.html` contains:

- `DATA_CACHE_BUSTER`
- `APP_BUILD_ID`

When data manifests or payload paths change, bump those values so browsers fetch fresh files instead of using cached manifests or contest JSON.

This is especially important after:

- regenerating `data/contests/manifest.json`
- renaming district contest directories
- changing which manifest directory a view should load

## Setup

### Node dependencies

Install the small Node dependency set:

```powershell
npm install
```

Current dependencies:

- `xlsx`
- `playwright`

### Python

The build scripts assume a working Python environment with the libraries required by the specific scripts you run. There is no pinned Python environment file in this repo right now, so install packages as needed for the script surface you are using.

## Running the app

This repo is a static app. The safest way to run it locally is through a simple HTTP server so fetches and cache behavior match normal browser expectations.

Example:

```powershell
py -m http.server 8000
```

Then open:

- `http://localhost:8000/`

Opening `index.html` directly can work for inspection, but a local server is better for debugging data fetches and manifest issues.

## Build scripts

### Main statewide contest build

```powershell
py scripts/build_idaho_contests.py
```

Purpose:

- rebuilds county/statewide contest payloads in `data/contests`
- updates `data/contests/manifest.json`
- writes district-oriented payload manifests used as inputs to downstream district derivation

### 2022-lines and 2026-lines district contest build

```powershell
node scripts/build_idaho_statewide_district_contests_2022_lines.js
```

Purpose:

- builds district contest payloads for the renamed `data/district_contests_2022_lines`
- builds congressional payloads for `data/district_contests_2026_lines`
- updates the manifests in both directories
- synthesizes canonical Idaho house files such as `state_house_state_house_2022.json` and `state_house_state_house_2024.json` from the legacy split-seat files when needed

### Remove uncontested contests from manifests

```powershell
node scripts/filter_uncontested_manifest_entries.js
```

Purpose:

- filters contest manifests so uncontested entries do not appear in selection UIs
- now uses a real candidate-count test rather than requiring both Democratic and Republican candidates

### Validate district contest outputs

```powershell
node scripts/validate_idaho_statewide_district_contests.js
```

Purpose:

- checks district payload coverage against manifests
- produces report artifacts under `data/reports/`

### Other notable scripts

- `scripts/build_idaho_2022_statewide_contests.py`
  - 2022-specific statewide contest builder
- `scripts/build_idaho_2010_2014_general_statewide_contests.js`
  - targeted builder for 2010 and 2014 statewide contests
- `scripts/build_idaho_census_assets.py`
  - county and VTD geometry asset build
- `scripts/build_idaho_crosswalks_2008_to_modern.py`
- `scripts/build_idaho_crosswalks_nhgis_to_modern.py`
- `scripts/build_idaho_vtd20_district_crosswalks.py`
  - crosswalk generation between precincts and district geometries
- `scripts/convert_2022_statewide_precinct_workbook_to_openelections_csv.py`
- `scripts/convert_raw_races_to_openelections.py`
  - conversion helpers for raw election sources

## Recommended refresh workflow

When statewide contest source data changes:

1. Rebuild statewide contests.
2. Rebuild district contest derivatives.
3. Filter uncontested manifest entries.
4. Run validation.
5. Bump the cache-buster in `index.html` if payloads or manifests consumed by the frontend changed.

In commands:

```powershell
py scripts/build_idaho_contests.py
node scripts/build_idaho_statewide_district_contests_2022_lines.js
node scripts/filter_uncontested_manifest_entries.js
node scripts/validate_idaho_statewide_district_contests.js
```

## Recent Idaho-specific maintenance notes

This repo recently had an audit of statewide executive contests across historical source CSVs. The important results:

- missing contested statewide executive races were restored to the generated payload set
- the contest filter logic was changed from "DEM and REP both present" to "at least two real candidates"
- `district_contests_2024_lines` was renamed to `district_contests_2022_lines`
- `index.html` was updated to use the renamed directory and to normalize statewide office aliases during contest loading

This matters because older historical Idaho offices are not consistently named across data sources and prior generated artifacts.

## Troubleshooting

### A contest exists on disk but does not appear in the county dropdown

Check:

1. `data/contests/manifest.json` contains the contest entry.
2. The browser is not using a stale cached manifest.
3. `DATA_CACHE_BUSTER` in `index.html` was bumped after the last manifest/data refresh.
4. You are in county view, not a district-only view.

### District view is loading the wrong line set

Check:

1. `getActiveDistrictContestsDir()` in `index.html`
2. `CONFIG.paths.district_contests_dir`
3. `CONFIG.paths.district_contests_dirs`
4. the active district-lines year in the UI state
5. whether the needed legacy 2022 state house seat files exist only in `data/district_contests` rather than `data/district_contests_2022_lines`

### A historical statewide office is missing

Check:

1. the relevant yearly source CSV under `data/<year>/`
2. `scripts/build_idaho_contests.py`
3. `data/contests/manifest.json`
4. whether the manifest filter removed the contest as uncontested

## Working notes

- `data/district_contests/manifest.json` may sometimes show up as a generated leftover during local rebuilds; treat it carefully and do not assume it is the authoritative active district manifest.
- there are no packaged npm scripts in `package.json`; builds are run directly via `py` and `node`.
- this repo is currently best understood as a maintained local data workspace plus static app, not a polished packaged library.

## Contribution guidance

When editing this repo:

- prefer updating build scripts and regenerating outputs rather than hand-editing generated contest JSON
- keep line-vintage naming explicit
- update `index.html` path hooks when directory names or manifest layout change
- bump the cache-buster whenever frontend-loaded assets materially change
