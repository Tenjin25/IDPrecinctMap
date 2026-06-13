from __future__ import annotations

import csv
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
INPUT_CSV = ROOT / "data" / "raw_races_general.csv"
OUTPUT_CSV = ROOT / "data" / "openelections-data-id" / "2024" / "20241105__id__general__precinct.csv"

FIELDNAMES = ["county", "precinct", "office", "district", "party", "candidate", "votes"]

PARTY_MAP = {
    "": "",
    "constitution": "CON",
    "democratic": "DEM",
    "independent": "IND",
    "libertarian": "LIB",
    "nonpartisan": "",
    "republican": "REP",
}


def normalize_county(value: str) -> str:
    county = (value or "").strip()
    county = re.sub(r"\s+County$", "", county, flags=re.IGNORECASE)
    return county.upper()


def normalize_precinct(value: str) -> str:
    return (value or "").strip()


def normalize_party(value: str) -> str:
    party = (value or "").strip()
    return PARTY_MAP.get(party.lower(), party.upper())


def parse_office_district(race: str) -> tuple[str, str]:
    race = (race or "").strip()

    patterns: list[tuple[re.Pattern[str], str]] = [
        (re.compile(r"^United States President$", re.IGNORECASE), "President"),
        (re.compile(r"^United States Representative District (\d+)$", re.IGNORECASE), "U.S. House"),
        (re.compile(r"^State Senator District (\d+)$", re.IGNORECASE), "State Senate"),
        (re.compile(r"^State Representative District (\d+) Seat ([A-Z])$", re.IGNORECASE), "State House"),
        (re.compile(r"^County Commissioner District (\d+)$", re.IGNORECASE), "County Commissioner"),
    ]

    for pattern, office_name in patterns:
        match = pattern.match(race)
        if not match:
            continue
        if office_name == "President":
            return office_name, "NA"
        if office_name == "State House":
            return office_name, f"{match.group(1)}{match.group(2).upper()}"
        return office_name, match.group(1)

    return race, "NA"


def main() -> None:
    OUTPUT_CSV.parent.mkdir(parents=True, exist_ok=True)

    with INPUT_CSV.open("r", encoding="utf-8-sig", newline="") as src, OUTPUT_CSV.open(
        "w", encoding="utf-8", newline=""
    ) as dst:
        reader = csv.DictReader(src)
        writer = csv.DictWriter(dst, fieldnames=FIELDNAMES)
        writer.writeheader()

        for row in reader:
            office, district = parse_office_district(row.get("Race", ""))
            writer.writerow(
                {
                    "county": normalize_county(row.get("County", "")),
                    "precinct": normalize_precinct(row.get("Precinct", "")),
                    "office": office,
                    "district": district,
                    "party": normalize_party(row.get("Party", "")),
                    "candidate": (row.get("Candidate", "") or "").strip(),
                    "votes": (row.get("Votes", "") or "").strip(),
                }
            )


if __name__ == "__main__":
    main()
