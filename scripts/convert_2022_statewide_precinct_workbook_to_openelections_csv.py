from __future__ import annotations

import csv
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
SOURCE_PATH = ROOT / "data" / "2022_General_Canvass" / "2022_General_Canvass" / "22 General Statewide - Precinct.xlsx"
OUTPUT_PATH = ROOT / "data" / "2022" / "20221108__id__general__precinct.csv"


CONTEST_SPECS: list[dict[str, object]] = [
    {
        "sheet_name": "US Sen",
        "party_row": 2,
        "candidate_row": 3,
        "data_start_row": 4,
        "contests": [
            {
                "office": "United States Senate",
                "district": "NA",
                "start_col": 1,
                "end_col": 5,
            },
        ],
    },
    {
        "sheet_name": "US Rep 1",
        "party_row": 3,
        "candidate_row": 4,
        "data_start_row": 5,
        "contests": [
            {
                "office": "United States House",
                "district": "1",
                "start_col": 1,
                "end_col": 3,
            },
        ],
    },
    {
        "sheet_name": "US Rep 2",
        "party_row": 3,
        "candidate_row": 4,
        "data_start_row": 5,
        "contests": [
            {
                "office": "United States House",
                "district": "2",
                "start_col": 1,
                "end_col": 2,
            },
        ],
    },
    {
        "sheet_name": "Gov",
        "party_row": 3,
        "candidate_row": 4,
        "data_start_row": 5,
        "contests": [
            {
                "office": "Governor",
                "district": "NA",
                "start_col": 1,
                "end_col": 6,
            },
        ],
    },
    {
        "sheet_name": "Lt Gov & SoS",
        "party_row": 3,
        "candidate_row": 4,
        "data_start_row": 5,
        "contests": [
            {
                "office": "Lieutenant Governor",
                "district": "NA",
                "start_col": 1,
                "end_col": 3,
            },
            {
                "office": "Secretary of State",
                "district": "NA",
                "start_col": 4,
                "end_col": 6,
            },
        ],
    },
    {
        "sheet_name": "SC & ST",
        "party_row": 3,
        "candidate_row": 4,
        "data_start_row": 5,
        "contests": [
            {
                "office": "State Controller",
                "district": "NA",
                "start_col": 1,
                "end_col": 3,
            },
            {
                "office": "State Treasurer",
                "district": "NA",
                "start_col": 4,
                "end_col": 5,
            },
        ],
    },
    {
        "sheet_name": "AG & SOPI",
        "party_row": 3,
        "candidate_row": 4,
        "data_start_row": 5,
        "contests": [
            {
                "office": "Attorney General",
                "district": "NA",
                "start_col": 1,
                "end_col": 2,
            },
            {
                "office": "Superintendent of Public Instruction",
                "district": "NA",
                "start_col": 3,
                "end_col": 4,
            },
        ],
    },
    {
        "sheet_name": "State Questions",
        "party_row": None,
        "candidate_row": 4,
        "data_start_row": 5,
        "contests": [
            {
                "office": "SJR 2 Constitutional Amendment",
                "district": "NA",
                "start_col": 1,
                "end_col": 2,
            },
            {
                "office": "Idaho Advisory Question (2022 Special Session HB 1)",
                "district": "NA",
                "start_col": 3,
                "end_col": 4,
            },
        ],
    },
]


def clean_cell(value: object) -> str:
    if pd.isna(value):
        return ""
    return str(value).replace("\r", " ").replace("\n", " ").strip()


def normalize_county(value: object) -> str:
    return clean_cell(value).replace(" County", "").upper()


def normalize_precinct(value: object) -> str:
    if pd.isna(value):
        return ""
    if isinstance(value, (int, float)):
        numeric = float(value)
        if numeric.is_integer():
            return str(int(numeric))
    text = clean_cell(value)
    return text.upper()


def normalize_party(value: object) -> str:
    text = clean_cell(value).upper().replace(".", "")
    if not text:
        return ""
    if text.startswith("DEM"):
        return "DEM"
    if text.startswith("REP"):
        return "REP"
    if text.startswith("LIB"):
        return "LIB"
    if text.startswith("CON"):
        return "CON"
    if "WRITE" in text or "W/I" in text:
        return "W/I"
    if text.startswith("IND"):
        return "IND"
    return text


def parse_votes(value: object) -> int | None:
    if pd.isna(value):
        return None
    text = clean_cell(value).replace(",", "")
    if not text:
        return None
    try:
        numeric = float(text)
    except ValueError:
        return None
    if not numeric.is_integer():
        return None
    return int(numeric)


def parse_sheet(spec: dict[str, object]) -> list[dict[str, str | int]]:
    raw = pd.read_excel(SOURCE_PATH, sheet_name=str(spec["sheet_name"]), header=None)
    if raw.empty:
        return []

    candidate_row = raw.iloc[int(spec["candidate_row"])].tolist()
    party_row = raw.iloc[int(spec["party_row"])].tolist() if spec["party_row"] is not None else []
    data_rows = raw.iloc[int(spec["data_start_row"]):].copy()
    current_county = ""
    output_rows: list[dict[str, str | int]] = []

    for _, row in data_rows.iterrows():
        first_cell = normalize_precinct(row.iloc[0])
        if not first_cell:
            continue

        remaining = [clean_cell(value) for value in row.iloc[1:].tolist()]
        if all(not value for value in remaining):
            current_county = normalize_county(first_cell)
            continue

        if not current_county:
            continue

        for contest in list(spec["contests"]):
            start_col = int(contest["start_col"])
            end_col = int(contest["end_col"])
            office = str(contest["office"])
            district = str(contest["district"])

            for col_idx in range(start_col, end_col + 1):
                candidate = clean_cell(candidate_row[col_idx] if col_idx < len(candidate_row) else "")
                if not candidate:
                    continue
                votes = parse_votes(row.iloc[col_idx] if col_idx < len(row) else "")
                if votes is None:
                    continue
                party = normalize_party(party_row[col_idx] if col_idx < len(party_row) else "")
                output_rows.append(
                    {
                        "county": current_county,
                        "precinct": first_cell,
                        "office": office,
                        "district": district,
                        "party": party,
                        "candidate": candidate,
                        "votes": votes,
                    }
                )

    return output_rows


def main() -> None:
    if not SOURCE_PATH.exists():
        raise FileNotFoundError(f"Missing source workbook: {SOURCE_PATH}")

    all_rows: list[dict[str, str | int]] = []
    for spec in CONTEST_SPECS:
        all_rows.extend(parse_sheet(spec))

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with OUTPUT_PATH.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=["county", "precinct", "office", "district", "party", "candidate", "votes"],
        )
        writer.writeheader()
        writer.writerows(all_rows)

    print(f"Wrote {len(all_rows)} rows to {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
