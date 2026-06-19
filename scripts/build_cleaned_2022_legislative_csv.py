from __future__ import annotations

import csv
import re
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
WORKBOOK_PATH = (
    ROOT
    / "data"
    / "2022_General_Canvass"
    / "2022_General_Canvass"
    / "22 General Legislative - Precinct.xlsx"
)
OUTPUT_PATH = (
    ROOT
    / "data"
    / "2022_General_Canvass"
    / "2022_legislative_precinct_cleaned.csv"
)


SUMMARY_PRECINCT_PREFIXES = (
    "TOTAL",
    "GRAND TOTAL",
    "COUNTY TOTAL",
    "CO. TOTAL",
)


def normalize_party(raw: str) -> str:
    value = (raw or "").strip().upper()
    mapping = {
        "DEM": "DEM",
        "DEMOCRAT": "DEM",
        "DEMOCRATIC": "DEM",
        "REP": "REP",
        "REPUBLICAN": "REP",
        "CON": "CON",
        "CONSTITUTION": "CON",
        "LIB": "LIB",
        "LIBERTARIAN": "LIB",
        "IND": "IND",
        "INDEPENDENT": "IND",
        "W/I": "W/I",
    }
    return mapping.get(value, value)


def norm_county(raw: str) -> str:
    text = (raw or "").strip()
    text = re.sub(r"\s+", " ", text)
    return text.upper()


def normalize_precinct_cell(value: object) -> str:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return ""
    text = str(value).strip()
    text = re.sub(r"\s+", " ", text)
    return text.upper()


def is_summary_precinct(text: str) -> bool:
    if not text:
        return True
    return any(text.startswith(prefix) for prefix in SUMMARY_PRECINCT_PREFIXES)


def canonical_office(office_label: str) -> tuple[str, str]:
    office = (office_label or "").strip().upper()
    if office == "ST SEN":
        return "state_senate", ""
    if office == "ST REP A":
        return "state_house", "A"
    if office == "ST REP B":
        return "state_house", "B"
    return office.lower().replace(" ", "_"), ""


def clean_office_row(path: Path, sheet_name: str, office_row: list[object]) -> list[str]:
    values = ["" if pd.isna(v) else str(v).strip() for v in office_row]
    uppercase = [v.upper() for v in values]
    if (
        path.name == "22 General Legislative - Precinct.xlsx"
        and sheet_name == "Leg Dist 22"
        and uppercase.count("ST REP A") == 2
        and "ST REP B" not in uppercase
    ):
        seen_house_a = 0
        for idx, label in enumerate(uppercase):
            if label != "ST REP A":
                continue
            seen_house_a += 1
            if seen_house_a == 2:
                values[idx] = "ST REP B"
                break

    normalized: list[str] = []
    last_label = ""
    for value in values:
        if value:
            last_label = value
        normalized.append(last_label)
    return normalized


def extract_sheet_records(path: Path, sheet_name: str, header_row_index: int = 2) -> list[dict[str, object]]:
    raw = pd.read_excel(path, sheet_name=sheet_name, header=None)
    if raw.empty:
        return []

    district_match = re.search(r"(\d+)$", sheet_name)
    if not district_match:
        return []
    district_num = int(district_match.group(1))

    office_row = clean_office_row(path, sheet_name, raw.iloc[header_row_index].tolist())
    party_row = ["" if pd.isna(v) else str(v).strip() for v in raw.iloc[header_row_index + 1].tolist()]
    candidate_row = ["" if pd.isna(v) else str(v).strip() for v in raw.iloc[header_row_index + 2].tolist()]
    data_rows = raw.iloc[header_row_index + 3 :].copy()

    records: list[dict[str, object]] = []
    current_county = ""
    pending_county_subtotal = False

    for excel_row_idx, row in data_rows.iterrows():
        precinct_text = normalize_precinct_cell(row.iloc[0])
        if not precinct_text:
            continue
        if is_summary_precinct(precinct_text):
            continue

        non_key_values = [
            v for v in row.iloc[1:].tolist() if not pd.isna(v) and str(v).strip() != ""
        ]
        if not non_key_values:
            current_county = norm_county(precinct_text)
            pending_county_subtotal = True
            continue

        if not current_county:
            continue
        if pending_county_subtotal and precinct_text == current_county:
            pending_county_subtotal = False
            continue
        pending_county_subtotal = False

        for col_idx in range(1, len(row)):
            candidate = candidate_row[col_idx] if col_idx < len(candidate_row) else ""
            if not candidate:
                continue
            votes = pd.to_numeric(row.iloc[col_idx], errors="coerce")
            if pd.isna(votes):
                continue
            office_label = office_row[col_idx] if col_idx < len(office_row) else ""
            party_label = party_row[col_idx] if col_idx < len(party_row) else ""
            office_type, seat = canonical_office(office_label)
            records.append(
                {
                    "sheet_name": sheet_name,
                    "district_num": district_num,
                    "county": current_county,
                    "precinct": precinct_text,
                    "office_label": office_label,
                    "office_type": office_type,
                    "seat": seat,
                    "party_label": party_label,
                    "party_norm": normalize_party(party_label),
                    "candidate": candidate,
                    "votes": int(votes),
                    "source_excel_row": int(excel_row_idx + 1),
                    "source_excel_col": int(col_idx + 1),
                }
            )
    return records


def main() -> None:
    if not WORKBOOK_PATH.exists():
        raise FileNotFoundError(f"Workbook not found: {WORKBOOK_PATH}")

    all_records: list[dict[str, object]] = []
    workbook = pd.ExcelFile(WORKBOOK_PATH)
    for sheet_name in workbook.sheet_names:
        all_records.extend(extract_sheet_records(WORKBOOK_PATH, sheet_name, header_row_index=2))

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "sheet_name",
        "district_num",
        "county",
        "precinct",
        "office_label",
        "office_type",
        "seat",
        "party_label",
        "party_norm",
        "candidate",
        "votes",
        "source_excel_row",
        "source_excel_col",
    ]
    with OUTPUT_PATH.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(all_records)

    print(f"Wrote {len(all_records)} rows to {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
