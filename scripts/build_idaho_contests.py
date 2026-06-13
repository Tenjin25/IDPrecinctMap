from __future__ import annotations

import json
import re
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
OPENELECTIONS_DIR = ROOT / "data" / "openelections-data-id"
CANVASS_2022_DIR = ROOT / "data" / "2022_General_Canvass" / "2022_General_Canvass"
CONTESTS_DIR = ROOT / "data" / "contests"
DISTRICT_CONTESTS_2022_DIR = ROOT / "data" / "district_contests"
DISTRICT_CONTESTS_2024_DIR = ROOT / "data" / "district_contests_2024_lines"
DISTRICT_CONTESTS_2026_DIR = ROOT / "data" / "district_contests_2026_lines"

DISTRICT_YEARS = {2022, 2024}
STATEWIDE_OTHER_YEARS = {1994, 1996, 1998, 2000, 2002, 2004, 2006, 2008, 2010, 2012, 2014, 2016, 2018, 2020, 2022}

PALETTE = [
    (-30.0, "#08306b"),
    (-20.0, "#08519c"),
    (-10.0, "#2171b5"),
    (-5.0, "#6baed6"),
    (5.0, "#cbd5e1"),
    (10.0, "#fcae91"),
    (20.0, "#fb6a4a"),
    (30.0, "#de2d26"),
]

STATEWIDE_OFFICE_PATTERNS: list[tuple[re.Pattern[str], dict[str, str]]] = [
    (re.compile(r"^President$", re.IGNORECASE), {"contest_type": "president", "office": "President of the United States"}),
    (
        re.compile(r"^(United States Senate|U\.S\. Senate|U\.S\. Senator)$", re.IGNORECASE),
        {"contest_type": "us_senate", "office": "United States Senator"},
    ),
    (re.compile(r"^Governor$", re.IGNORECASE), {"contest_type": "governor", "office": "Governor"}),
    (re.compile(r"^Lieutenant Governor$", re.IGNORECASE), {"contest_type": "lieutenant_governor", "office": "Lieutenant Governor"}),
    (re.compile(r"^(Secretary of State|of State)$", re.IGNORECASE), {"contest_type": "secretary_of_state", "office": "Secretary of State"}),
    (re.compile(r"^(Attorney General|General)$", re.IGNORECASE), {"contest_type": "attorney_general", "office": "Attorney General"}),
    (re.compile(r"^(State Controller|Controller)$", re.IGNORECASE), {"contest_type": "state_controller", "office": "State Controller"}),
    (re.compile(r"^(State Treasurer|Treasurer)$", re.IGNORECASE), {"contest_type": "state_treasurer", "office": "State Treasurer"}),
    (
        re.compile(r"^(Superintendent of Public Instruction|Publ Instr)$", re.IGNORECASE),
        {"contest_type": "superintendent_public_instruction", "office": "Superintendent of Public Instruction"},
    ),
    (re.compile(r"^Auditor$", re.IGNORECASE), {"contest_type": "state_auditor", "office": "Auditor"}),
]

DISTRICT_OFFICE_PATTERNS: list[tuple[re.Pattern[str], dict[str, str]]] = [
    (re.compile(r"^U\.S\. House$", re.IGNORECASE), {"contest_type": "us_house", "scope": "congressional", "office": "U.S. House"}),
    (
        re.compile(r"^U\.S\. Representative\s+(\d+)(?:st|nd|rd|th)\s+District$", re.IGNORECASE),
        {"contest_type": "us_house", "scope": "congressional", "office": "U.S. House"},
    ),
    (
        re.compile(r"^(\d+)(?:st|nd|rd|th)\s+District$", re.IGNORECASE),
        {"contest_type": "us_house", "scope": "congressional", "office": "U.S. House"},
    ),
    (re.compile(r"^State Senate$", re.IGNORECASE), {"contest_type": "state_senate", "scope": "state_senate", "office": "State Senate"}),
    (re.compile(r"^State House$", re.IGNORECASE), {"contest_type": "state_house", "scope": "state_house", "office": "State House"}),
]

CANVASS_2022_STATEWIDE_SPECS: list[dict[str, object]] = [
    {
        "sheet_name": "US Sen",
        "party_row": 2,
        "candidate_row": 3,
        "data_start_row": 4,
        "contests": [
            {"contest_type": "us_senate", "office": "United States Senator", "start_col": 1, "end_col": 6},
        ],
    },
    {
        "sheet_name": "Gov",
        "party_row": 3,
        "candidate_row": 4,
        "data_start_row": 5,
        "contests": [
            {"contest_type": "governor", "office": "Governor", "start_col": 1, "end_col": 7},
        ],
    },
    {
        "sheet_name": "Lt Gov & SoS",
        "party_row": 3,
        "candidate_row": 4,
        "data_start_row": 5,
        "contests": [
            {"contest_type": "lieutenant_governor", "office": "Lieutenant Governor", "start_col": 1, "end_col": 4},
            {"contest_type": "secretary_of_state", "office": "Secretary of State", "start_col": 4, "end_col": 7},
        ],
    },
    {
        "sheet_name": "SC & ST",
        "party_row": 3,
        "candidate_row": 4,
        "data_start_row": 5,
        "contests": [
            {"contest_type": "state_controller", "office": "State Controller", "start_col": 1, "end_col": 4},
            {"contest_type": "state_treasurer", "office": "State Treasurer", "start_col": 4, "end_col": 6},
        ],
    },
    {
        "sheet_name": "AG & SOPI",
        "party_row": 3,
        "candidate_row": 4,
        "data_start_row": 5,
        "contests": [
            {"contest_type": "attorney_general", "office": "Attorney General", "start_col": 1, "end_col": 3},
            {
                "contest_type": "superintendent_public_instruction",
                "office": "Superintendent of Public Instruction",
                "start_col": 3,
                "end_col": 5,
            },
        ],
    },
]


def norm_county(county_name: str) -> str:
    name = (county_name or "").replace(" County", "").strip().upper()
    return "".join(ch for ch in name if ch.isalnum() or ch in {" ", "-", "."}).strip()


def normalize_precinct(precinct: str) -> str:
    return (precinct or "").strip().upper()


def is_summary_precinct(precinct: str) -> bool:
    text = normalize_precinct(precinct)
    if not text:
        return False
    return (
        "CO TOTAL" in text
        or "CO. TOTAL" in text
        or "COUNTY TOTAL" in text
    )


def normalize_precinct_cell(value: object) -> str:
    if pd.isna(value):
        return ""
    if isinstance(value, (int, float)):
        numeric = float(value)
        if numeric.is_integer():
            return str(int(numeric))
    return normalize_precinct(str(value))


def pick_color(margin_pct: float) -> str:
    signed = float(margin_pct or 0)
    for threshold, color in PALETTE:
        if signed <= threshold:
            return color
    return "#a50f15"


def normalize_party(raw: str) -> str:
    text = (raw or "").strip().upper().replace(".", "")
    if text.startswith("DEM"):
        return "DEM"
    if text.startswith("REP"):
        return "REP"
    if text in {"", "NA", "NON", "NAN"}:
        return ""
    return "OTHER"


def extract_year_from_path(path: Path) -> int | None:
    match = re.match(r"^(\d{4})\d{4}__id__general__precinct\.csv$", path.name, re.IGNORECASE)
    return int(match.group(1)) if match else None


def statewide_general_precinct_files() -> list[tuple[int, Path]]:
    files: list[tuple[int, Path]] = []
    seen: set[Path] = set()

    candidate_roots = [OPENELECTIONS_DIR, ROOT / "data"]
    for base_dir in candidate_roots:
        if not base_dir.exists():
            continue
        for year_dir in sorted(p for p in base_dir.iterdir() if p.is_dir() and p.name.isdigit()):
            for path in sorted(year_dir.glob("*__general__precinct.csv")):
                resolved = path.resolve()
                if resolved in seen:
                    continue
                year = extract_year_from_path(path)
                if year is None:
                    continue
                seen.add(resolved)
                files.append((year, path))
    return sorted(files)


def parse_statewide_office(office_raw: str, district_raw: str = "") -> dict[str, object] | None:
    office = (office_raw or "").strip()
    if not office:
        return None
    for pattern, meta in STATEWIDE_OFFICE_PATTERNS:
        if pattern.match(office):
            return {"contest_type": str(meta["contest_type"]), "office": str(meta["office"])}
    return None


def parse_district_office(office_raw: str, district_raw: str) -> dict[str, object] | None:
    office = (office_raw or "").strip()
    district = (district_raw or "").strip()
    if not office:
        return None

    for pattern, meta in DISTRICT_OFFICE_PATTERNS:
        match = pattern.match(office)
        if not match:
            continue

        if meta["contest_type"] == "us_house":
            district_num = None
            if match.groups():
                district_num = int(match.group(1))
            else:
                digits = re.sub(r"[^0-9]", "", district)
                district_num = int(digits) if digits else None
            if district_num is None:
                return None
            return {
                "contest_type": "us_house",
                "scope": "congressional",
                "office": "U.S. House",
                "district_num": district_num,
            }

        if meta["contest_type"] == "state_senate":
            digits = re.sub(r"[^0-9]", "", district)
            if not digits:
                return None
            return {
                "contest_type": "state_senate",
                "scope": "state_senate",
                "office": "State Senate",
                "district_num": int(digits),
            }

        if meta["contest_type"] == "state_house":
            m = re.match(r"^\s*(\d+)\s*([A-Z])\s*$", district, re.IGNORECASE)
            if not m:
                return None
            district_num = int(m.group(1))
            seat = m.group(2).upper()
            return {
                "contest_type": f"state_house_{seat.lower()}",
                "scope": "state_house",
                "office": f"State House Seat {seat}",
                "district_num": district_num,
            }

    return None


def summarize_votes(group: pd.DataFrame) -> dict[str, object]:
    party = group["party_norm"].fillna("").astype(str)
    dem_rows = group[party.eq("DEM")]
    rep_rows = group[party.eq("REP")]
    other_mask = party.eq("OTHER")

    dem_votes = int(pd.to_numeric(dem_rows["votes"], errors="coerce").fillna(0).sum())
    rep_votes = int(pd.to_numeric(rep_rows["votes"], errors="coerce").fillna(0).sum())
    other_votes = int(pd.to_numeric(group.loc[other_mask, "votes"], errors="coerce").fillna(0).sum())
    total_votes = dem_votes + rep_votes + other_votes
    margin = rep_votes - dem_votes
    margin_pct = ((rep_votes - dem_votes) / total_votes * 100.0) if total_votes else 0.0
    winner = "REP" if margin > 0 else ("DEM" if margin < 0 else "TIE")

    return {
        "dem_votes": dem_votes,
        "rep_votes": rep_votes,
        "other_votes": other_votes,
        "total_votes": total_votes,
        "dem_candidate": str(dem_rows["candidate"].iloc[0]).strip() if not dem_rows.empty else "",
        "rep_candidate": str(rep_rows["candidate"].iloc[0]).strip() if not rep_rows.empty else "",
        "margin": margin,
        "margin_pct": round(margin_pct, 4),
        "winner": winner,
        "color": pick_color(margin_pct),
    }


def build_precinct_rows(df: pd.DataFrame) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for row_key, group in df.groupby("row_key", sort=True):
        rows.append({"county": row_key, **summarize_votes(group)})
    return rows


def build_district_results(df: pd.DataFrame) -> dict[str, dict[str, object]]:
    results: dict[str, dict[str, object]] = {}
    for district_num, group in df.groupby("district_num", sort=True):
        if pd.isna(district_num):
            continue
        results[str(int(district_num))] = summarize_votes(group)
    return results


def write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def build_rows_from_file(year: int, path: Path) -> pd.DataFrame:
    df = pd.read_csv(path)
    df = df.rename(columns={col: col.strip().lower() for col in df.columns})
    if not {"county", "precinct", "office", "district", "party", "candidate", "votes"}.issubset(df.columns):
        raise RuntimeError(f"Unexpected OpenElections schema in {path}")

    df["county_norm"] = df["county"].fillna("").astype(str).map(norm_county)
    df["precinct_norm"] = df["precinct"].fillna("").astype(str).map(normalize_precinct)
    df = df[~df["precinct_norm"].map(is_summary_precinct)].copy()
    df["row_key"] = df["county_norm"] + " - " + df["precinct_norm"]
    df["votes"] = pd.to_numeric(df["votes"], errors="coerce").fillna(0).astype(int)
    df["party_norm"] = df["party"].fillna("").astype(str).map(normalize_party)
    df["candidate"] = df["candidate"].fillna("").astype(str).str.strip()
    df["office"] = df["office"].fillna("").astype(str).str.strip()
    df["district"] = df["district"].fillna("").astype(str).str.strip()
    df["year"] = year
    return df


def parse_precinct_canvass_sheet(path: Path, sheet_name: str, header_row_index: int) -> pd.DataFrame:
    raw = pd.read_excel(path, sheet_name=sheet_name, header=None)
    if raw.empty:
        return pd.DataFrame()

    office_row = raw.iloc[header_row_index].tolist()
    party_row = raw.iloc[header_row_index + 1].tolist()
    candidate_row = raw.iloc[header_row_index + 2].tolist()
    data_rows = raw.iloc[header_row_index + 3 :].copy()

    records: list[dict[str, object]] = []
    current_county = ""

    for _, row in data_rows.iterrows():
        precinct_cell = row.iloc[0]
        precinct_text = normalize_precinct_cell(precinct_cell)
        if not precinct_text:
            continue
        if is_summary_precinct(precinct_text):
            continue

        non_key_values = [v for v in row.iloc[1:].tolist() if not pd.isna(v) and str(v).strip() != ""]
        if not non_key_values:
            current_county = norm_county(precinct_text)
            continue

        if not current_county:
            continue

        for col_idx in range(1, len(row)):
            candidate = "" if pd.isna(candidate_row[col_idx]) else str(candidate_row[col_idx]).strip()
            if not candidate:
                continue
            office_label = "" if pd.isna(office_row[col_idx]) else str(office_row[col_idx]).strip()
            party_label = "" if pd.isna(party_row[col_idx]) else str(party_row[col_idx]).strip()
            votes = pd.to_numeric(row.iloc[col_idx], errors="coerce")
            if pd.isna(votes):
                continue
            records.append(
                {
                    "county_norm": current_county,
                    "precinct_norm": precinct_text,
                    "office_label": office_label,
                    "party_label": party_label,
                    "candidate": candidate,
                    "votes": int(votes),
                }
            )

    df = pd.DataFrame(records)
    if not df.empty:
        df["row_key"] = df["county_norm"] + " - " + df["precinct_norm"]
        df["party_norm"] = df["party_label"].map(normalize_party)
    return df


def parse_2022_statewide_precinct_sheet(path: Path, spec: dict[str, object]) -> dict[str, pd.DataFrame]:
    raw = pd.read_excel(path, sheet_name=str(spec["sheet_name"]), header=None)
    if raw.empty:
        return {}

    party_row = raw.iloc[int(spec["party_row"])].tolist()
    candidate_row = raw.iloc[int(spec["candidate_row"])].tolist()
    data_rows = raw.iloc[int(spec["data_start_row"]) :].copy()
    contest_specs = list(spec.get("contests") or [])

    records_by_type: dict[str, list[dict[str, object]]] = {
        str(contest["contest_type"]): [] for contest in contest_specs
    }
    current_county = ""

    for _, row in data_rows.iterrows():
        precinct_text = normalize_precinct_cell(row.iloc[0])
        if not precinct_text:
            continue
        if is_summary_precinct(precinct_text):
            continue

        non_key_values = [v for v in row.iloc[1:].tolist() if not pd.isna(v) and str(v).strip() != ""]
        if not non_key_values:
            current_county = norm_county(precinct_text)
            continue

        if not current_county:
            continue

        for contest in contest_specs:
            contest_type = str(contest["contest_type"])
            office_label = str(contest["office"])
            start_col = int(contest["start_col"])
            end_col = int(contest["end_col"])
            for col_idx in range(start_col, min(end_col, len(row))):
                candidate = "" if pd.isna(candidate_row[col_idx]) else str(candidate_row[col_idx]).strip()
                if not candidate:
                    continue
                votes = pd.to_numeric(row.iloc[col_idx], errors="coerce")
                if pd.isna(votes):
                    continue
                party_label = "" if pd.isna(party_row[col_idx]) else str(party_row[col_idx]).strip()
                records_by_type[contest_type].append(
                    {
                        "county_norm": current_county,
                        "precinct_norm": precinct_text,
                        "row_key": current_county + " - " + precinct_text,
                        "office_label": office_label,
                        "party_label": party_label,
                        "party_norm": normalize_party(party_label),
                        "candidate": candidate,
                        "votes": int(votes),
                    }
                )

    out: dict[str, pd.DataFrame] = {}
    for contest in contest_specs:
        contest_type = str(contest["contest_type"])
        frame = pd.DataFrame(records_by_type.get(contest_type) or [])
        if not frame.empty:
            out[contest_type] = frame
    return out


def add_2022_statewide_payloads(
    contest_manifest_files: list[dict[str, object]],
) -> None:
    statewide_path = CANVASS_2022_DIR / "22 General Statewide - Precinct.xlsx"
    if not statewide_path.exists():
        return

    frames_by_type: dict[str, pd.DataFrame] = {}
    office_by_type: dict[str, str] = {}
    for spec in CANVASS_2022_STATEWIDE_SPECS:
        parsed = parse_2022_statewide_precinct_sheet(statewide_path, spec)
        for contest in list(spec.get("contests") or []):
            contest_type = str(contest["contest_type"])
            office_by_type[contest_type] = str(contest["office"])
        for contest_type, frame in parsed.items():
            if contest_type in frames_by_type:
                frames_by_type[contest_type] = pd.concat([frames_by_type[contest_type], frame], ignore_index=True)
            else:
                frames_by_type[contest_type] = frame

    for contest_type, frame in sorted(frames_by_type.items()):
        rows = build_precinct_rows(frame)
        if not rows:
            continue
        file_name = f"{contest_type}_2022.json"
        write_json(
            CONTESTS_DIR / file_name,
            {
                "year": 2022,
                "contest_type": contest_type,
                "meta": {
                    "office": office_by_type.get(contest_type, contest_type),
                    "source": "2022_General_Canvass.zip",
                    "aggregation": "precinct",
                },
                "rows": rows,
            },
        )
        contest_manifest_files.append(
            {
                "year": 2022,
                "contest_type": contest_type,
                "file": file_name,
                "rows": len(rows),
                "office": office_by_type.get(contest_type, contest_type),
            }
        )


def add_existing_contest_manifest_entries(contest_manifest_files: list[dict[str, object]]) -> None:
    existing_keys = {
        (int(entry["year"]), str(entry["contest_type"]))
        for entry in contest_manifest_files
        if "year" in entry and "contest_type" in entry
    }
    preserve_specs = [
        (2024, "president", "president_2024.json", "President of the United States"),
    ]
    for year, contest_type, file_name, office in preserve_specs:
        if (year, contest_type) in existing_keys:
            continue
        path = CONTESTS_DIR / file_name
        if not path.exists():
            continue
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        rows = payload.get("rows") or []
        contest_manifest_files.append(
            {
                "year": year,
                "contest_type": contest_type,
                "file": file_name,
                "rows": len(rows),
                "office": office,
            }
        )


def add_2022_district_payloads(
    manifest_rows: list[dict[str, object]],
) -> None:
    legislative_path = CANVASS_2022_DIR / "22 General Legislative - Precinct.xlsx"
    statewide_path = CANVASS_2022_DIR / "22 General Statewide - Precinct.xlsx"
    if not legislative_path.exists() or not statewide_path.exists():
        return

    senate_results: dict[str, dict[str, object]] = {}
    house_a_results: dict[str, dict[str, object]] = {}
    house_b_results: dict[str, dict[str, object]] = {}

    leg_book = pd.ExcelFile(legislative_path)
    for sheet_name in leg_book.sheet_names:
        m = re.search(r"(\d+)$", sheet_name)
        if not m:
            continue
        district_num = str(int(m.group(1)))
        sheet_df = parse_precinct_canvass_sheet(legislative_path, sheet_name, header_row_index=2)
        if sheet_df.empty:
            continue

        senate_df = sheet_df[sheet_df["office_label"].str.upper().eq("ST SEN")].copy()
        house_a_df = sheet_df[sheet_df["office_label"].str.upper().eq("ST REP A")].copy()
        house_b_df = sheet_df[sheet_df["office_label"].str.upper().eq("ST REP B")].copy()

        if not senate_df.empty:
            senate_results[district_num] = summarize_votes(senate_df)
        if not house_a_df.empty:
            house_a_results[district_num] = summarize_votes(house_a_df)
        if not house_b_df.empty:
            house_b_results[district_num] = summarize_votes(house_b_df)

    statewide_book = pd.ExcelFile(statewide_path)
    congressional_results: dict[str, dict[str, object]] = {}
    for sheet_name, district_num in [("US Rep 1", "1"), ("US Rep 2", "2")]:
        if sheet_name not in statewide_book.sheet_names:
            continue
        sheet_df = parse_precinct_canvass_sheet(statewide_path, sheet_name, header_row_index=2)
        if sheet_df.empty:
            continue
        congressional_results[district_num] = summarize_votes(sheet_df)

    payload_specs = [
        ("congressional", "us_house", "U.S. House", congressional_results, "congressional_us_house_2022.json"),
        ("state_house", "state_house_a", "State House Seat A", house_a_results, "state_house_state_house_a_2022.json"),
        ("state_house", "state_house_b", "State House Seat B", house_b_results, "state_house_state_house_b_2022.json"),
        ("state_senate", "state_senate", "State Senate", senate_results, "state_senate_state_senate_2022.json"),
    ]

    for scope, contest_type, office_label, results, file_name in payload_specs:
        if not results:
            continue
        payload = {
            "year": 2022,
            "scope": scope,
            "contest_type": contest_type,
            "meta": {
                "office": office_label,
                "source": "2022_General_Canvass.zip",
            },
            "general": {
                "results": results,
            },
        }
        write_json(DISTRICT_CONTESTS_2022_DIR / file_name, payload)
        manifest_rows.append(
            {
                "year": 2022,
                "scope": scope,
                "contest_type": contest_type,
                "file": file_name,
                "districts": len(results),
                "office": office_label,
            }
        )


def main() -> None:
    CONTESTS_DIR.mkdir(parents=True, exist_ok=True)
    DISTRICT_CONTESTS_2022_DIR.mkdir(parents=True, exist_ok=True)
    DISTRICT_CONTESTS_2024_DIR.mkdir(parents=True, exist_ok=True)
    DISTRICT_CONTESTS_2026_DIR.mkdir(parents=True, exist_ok=True)

    contest_manifest_files: list[dict[str, object]] = []
    district_manifest_2022: list[dict[str, object]] = []
    district_manifest_2024: list[dict[str, object]] = []

    add_2022_district_payloads(district_manifest_2022)

    for year, path in statewide_general_precinct_files():
        df = build_rows_from_file(year, path)

        statewide_frames: dict[str, tuple[str, pd.DataFrame]] = {}
        district_frames: dict[tuple[str, str], tuple[str, pd.DataFrame]] = {}

        for office_name, office_df in df.groupby("office", sort=True):
            if year in STATEWIDE_OTHER_YEARS:
                parsed_statewide = parse_statewide_office(office_name, str(office_df["district"].iloc[0]))
                if parsed_statewide and not (parsed_statewide["contest_type"] == "president" and year == 2024):
                    statewide_frames[parsed_statewide["contest_type"]] = (str(parsed_statewide["office"]), office_df.copy())

            district_groups: list[pd.DataFrame] = []
            if year in DISTRICT_YEARS and office_name.lower() == "state house":
                district_groups = [group.copy() for _, group in office_df.groupby(office_df["district"].astype(str).str.strip().str.upper().str[-1], sort=True)]
            else:
                district_groups = [office_df.copy()]

            for district_group in district_groups:
                parsed_district = parse_district_office(office_name, str(district_group["district"].iloc[0]))
                if not parsed_district:
                    continue
                is_legislative_scope = str(parsed_district["scope"]) in {"state_house", "state_senate"}
                if is_legislative_scope and year not in DISTRICT_YEARS:
                    continue
                key = (str(parsed_district["scope"]), str(parsed_district["contest_type"]))
                district_frames[key] = (str(parsed_district["office"]), district_group)

        for contest_type, (office_label, office_df) in sorted(statewide_frames.items()):
            rows = build_precinct_rows(office_df)
            file_name = f"{contest_type}_{year}.json"
            write_json(
                CONTESTS_DIR / file_name,
                {
                    "year": year,
                    "contest_type": contest_type,
                    "meta": {
                        "office": office_label,
                        "source": path.name,
                        "aggregation": "precinct",
                    },
                    "rows": rows,
                },
            )
            contest_manifest_files.append(
                {
                    "year": year,
                    "contest_type": contest_type,
                    "file": file_name,
                    "rows": len(rows),
                    "office": office_label,
                }
            )

        for (scope, contest_type), (office_label, office_df) in sorted(district_frames.items()):
            district_meta = parse_district_office(str(office_df["office"].iloc[0]), str(office_df["district"].iloc[0]))
            if district_meta is None:
                continue
            office_df = office_df.copy()
            office_df["district_num"] = office_df["district"].map(
                lambda raw: (
                    int(re.sub(r"[^0-9]", "", str(raw))) if re.sub(r"[^0-9]", "", str(raw)) else None
                )
            )
            results = build_district_results(office_df)
            file_name = f"{scope}_{contest_type}_{year}.json"
            payload = {
                "year": year,
                "scope": scope,
                "contest_type": contest_type,
                "meta": {
                    "office": office_label,
                    "source": path.name,
                },
                "general": {
                    "results": results,
                },
            }

            if year == 2022:
                write_json(DISTRICT_CONTESTS_2022_DIR / file_name, payload)
                district_manifest_2022.append(
                    {
                        "year": year,
                        "scope": scope,
                        "contest_type": contest_type,
                        "file": file_name,
                        "districts": len(results),
                        "office": office_label,
                    }
                )
            elif year == 2024:
                write_json(DISTRICT_CONTESTS_2024_DIR / file_name, payload)
                district_manifest_2024.append(
                    {
                        "year": year,
                        "scope": scope,
                        "contest_type": contest_type,
                        "file": file_name,
                        "districts": len(results),
                        "office": office_label,
                    }
                )
    add_existing_contest_manifest_entries(contest_manifest_files)
    write_json(CONTESTS_DIR / "manifest.json", {"files": sorted(contest_manifest_files, key=lambda x: (x["year"], x["contest_type"]))})
    write_json(DISTRICT_CONTESTS_2022_DIR / "manifest.json", {"files": sorted(district_manifest_2022, key=lambda x: (x["year"], x["scope"], x["contest_type"]))})
    write_json(DISTRICT_CONTESTS_2024_DIR / "manifest.json", {"files": sorted(district_manifest_2024, key=lambda x: (x["year"], x["scope"], x["contest_type"]))})
    write_json(DISTRICT_CONTESTS_2026_DIR / "manifest.json", {"files": []})


if __name__ == "__main__":
    main()
