from __future__ import annotations

import json
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
CANVASS_PATH = ROOT / "data" / "2022_General_Canvass" / "2022_General_Canvass" / "22 General Statewide - Precinct.xlsx"
CONTESTS_DIR = ROOT / "data" / "contests"
MANIFEST_PATH = CONTESTS_DIR / "manifest.json"

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

STATEWIDE_SPECS: list[dict[str, object]] = [
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


def normalize_precinct(value: object) -> str:
    if pd.isna(value):
        return ""
    if isinstance(value, (int, float)):
        numeric = float(value)
        if numeric.is_integer():
            return str(int(numeric))
    return str(value).strip().upper()


def normalize_party(raw: str) -> str:
    text = (raw or "").strip().upper().replace(".", "")
    if text.startswith("DEM"):
        return "DEM"
    if text.startswith("REP"):
        return "REP"
    if text in {"", "NA", "NON", "NAN"}:
        return ""
    return "OTHER"


def pick_color(margin_pct: float) -> str:
    signed = float(margin_pct or 0)
    for threshold, color in PALETTE:
        if signed <= threshold:
            return color
    return "#a50f15"


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


def parse_sheet(spec: dict[str, object]) -> dict[str, pd.DataFrame]:
    raw = pd.read_excel(CANVASS_PATH, sheet_name=str(spec["sheet_name"]), header=None)
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
        precinct_text = normalize_precinct(row.iloc[0])
        if not precinct_text:
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


def write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def load_manifest() -> list[dict[str, object]]:
    if not MANIFEST_PATH.exists():
        return []
    payload = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    files = payload.get("files") or []
    return [entry for entry in files if isinstance(entry, dict)]


def upsert_manifest_entries(manifest_rows: list[dict[str, object]], new_entries: list[dict[str, object]]) -> list[dict[str, object]]:
    by_key: dict[tuple[int, str], dict[str, object]] = {}
    for entry in manifest_rows:
        year = int(entry.get("year"))
        contest_type = str(entry.get("contest_type") or "")
        if contest_type:
            by_key[(year, contest_type)] = entry
    for entry in new_entries:
        by_key[(int(entry["year"]), str(entry["contest_type"]))] = entry
    return sorted(by_key.values(), key=lambda x: (int(x["year"]), str(x["contest_type"])))


def main() -> None:
    if not CANVASS_PATH.exists():
        raise FileNotFoundError(f"Missing workbook: {CANVASS_PATH}")

    frames_by_type: dict[str, pd.DataFrame] = {}
    office_by_type: dict[str, str] = {}

    for spec in STATEWIDE_SPECS:
        parsed = parse_sheet(spec)
        for contest in list(spec.get("contests") or []):
            office_by_type[str(contest["contest_type"])] = str(contest["office"])
        for contest_type, frame in parsed.items():
            if contest_type in frames_by_type:
                frames_by_type[contest_type] = pd.concat([frames_by_type[contest_type], frame], ignore_index=True)
            else:
                frames_by_type[contest_type] = frame

    new_entries: list[dict[str, object]] = []
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
        new_entries.append(
            {
                "year": 2022,
                "contest_type": contest_type,
                "file": file_name,
                "rows": len(rows),
                "office": office_by_type.get(contest_type, contest_type),
            }
        )

    manifest_rows = load_manifest()
    merged = upsert_manifest_entries(manifest_rows, new_entries)
    write_json(MANIFEST_PATH, {"files": merged})


if __name__ == "__main__":
    main()
