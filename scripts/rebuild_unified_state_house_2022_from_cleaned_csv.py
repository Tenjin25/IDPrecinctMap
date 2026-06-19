from __future__ import annotations

import csv
import json
from collections import defaultdict
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CLEANED_CSV_PATH = ROOT / "data" / "2022_General_Canvass" / "2022_legislative_precinct_cleaned.csv"
OUTPUT_JSON_PATH = ROOT / "data" / "district_contests_2022_lines" / "state_house_state_house_2022.json"


def category_color_for_margin(margin_pct_abs: float, winner: str) -> str:
    if winner not in {"REP", "DEM"}:
        return "#f7f7f7"
    is_rep = winner == "REP"
    if margin_pct_abs >= 40:
        return "#67000d" if is_rep else "#08306b"
    if margin_pct_abs >= 30:
        return "#a50f15" if is_rep else "#08519c"
    if margin_pct_abs >= 20:
        return "#cb181d" if is_rep else "#3182bd"
    if margin_pct_abs >= 10:
        return "#ef3b2c" if is_rep else "#6baed6"
    if margin_pct_abs >= 5.5:
        return "#fb6a4a" if is_rep else "#9ecae1"
    if margin_pct_abs >= 1.0:
        return "#fcae91" if is_rep else "#c6dbef"
    if margin_pct_abs >= 0.5:
        return "#fee8c8" if is_rep else "#e1f5fe"
    return "#f7f7f7"


def load_cleaned_rows() -> list[dict[str, str]]:
    with CLEANED_CSV_PATH.open("r", encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh))


def to_int(value: str) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return 0


def pick_winner(dem_votes: int, rep_votes: int, other_votes: int) -> str:
    buckets = [("DEM", dem_votes), ("REP", rep_votes), ("OTHER", other_votes)]
    max_votes = max(v for _, v in buckets)
    if max_votes <= 0:
        return "TIE"
    winners = [party for party, votes in buckets if votes == max_votes]
    if len(winners) != 1:
        return "TIE"
    return winners[0]


def build_payload(rows: list[dict[str, str]]) -> dict:
    seat_totals: dict[tuple[int, str], dict[str, object]] = {}
    unique_candidates: set[str] = set()

    for row in rows:
        if row.get("office_type") != "state_house":
            continue
        seat = (row.get("seat") or "").strip().upper()
        district_num = to_int(row.get("district_num"))
        if district_num <= 0 or seat not in {"A", "B"}:
            continue

        key = (district_num, seat)
        bucket = seat_totals.setdefault(
            key,
            {
                "dem_votes": 0,
                "rep_votes": 0,
                "other_votes": 0,
                "total_votes": 0,
                "dem_candidates": defaultdict(int),
                "rep_candidates": defaultdict(int),
            },
        )

        votes = to_int(row.get("votes"))
        party = (row.get("party_norm") or "").strip().upper()
        candidate = (row.get("candidate") or "").strip()
        if candidate:
            unique_candidates.add(candidate)

        bucket["total_votes"] += votes
        if party == "DEM":
            bucket["dem_votes"] += votes
            if candidate:
                bucket["dem_candidates"][candidate] += votes
        elif party == "REP":
            bucket["rep_votes"] += votes
            if candidate:
                bucket["rep_candidates"][candidate] += votes
        else:
            bucket["other_votes"] += votes

    results: dict[str, dict[str, object]] = {}
    for district_num, seat in sorted(seat_totals.keys()):
        bucket = seat_totals[(district_num, seat)]
        dem_votes = int(bucket["dem_votes"])
        rep_votes = int(bucket["rep_votes"])
        other_votes = int(bucket["other_votes"])
        total_votes = int(bucket["total_votes"])

        dem_candidates = bucket["dem_candidates"]
        rep_candidates = bucket["rep_candidates"]
        dem_candidate = max(dem_candidates.items(), key=lambda item: (item[1], item[0]))[0] if dem_candidates else ""
        rep_candidate = max(rep_candidates.items(), key=lambda item: (item[1], item[0]))[0] if rep_candidates else ""

        signed_margin_pct = ((rep_votes - dem_votes) / total_votes * 100.0) if total_votes > 0 else 0.0
        winner = pick_winner(dem_votes, rep_votes, other_votes)
        color = category_color_for_margin(abs(signed_margin_pct), winner)
        district_key = f"{district_num}{seat}"

        results[district_key] = {
            "district": district_key,
            "district_num": district_num,
            "seat": seat,
            "dem_votes": dem_votes,
            "rep_votes": rep_votes,
            "other_votes": other_votes,
            "total_votes": total_votes,
            "dem_candidate": dem_candidate,
            "rep_candidate": rep_candidate,
            "margin": rep_votes - dem_votes,
            "margin_pct": round(signed_margin_pct, 6),
            "winner": winner,
            "color": color,
            "competitiveness": {"color": color},
            "no_data": total_votes <= 0,
        }

    return {
        "scope": "state_house",
        "contest_type": "state_house",
        "year": 2022,
        "state": "ID",
        "meta": {
            "match_coverage_pct": None,
            "weighted_vote_coverage_pct": None,
            "source": "idaho_unified_state_house_from_cleaned_csv",
            "office": "State House",
            "office_group": "State House",
            "district_format": "number+seat",
            "seat_labels": ["A", "B"],
            "lines_year": 2022,
            "candidate_count": len(unique_candidates) or None,
        },
        "general": {"results": results},
    }


def main() -> None:
    rows = load_cleaned_rows()
    payload = build_payload(rows)
    OUTPUT_JSON_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_JSON_PATH.write_text(f"{json.dumps(payload, indent=2)}\n", encoding="utf-8")
    print(f"Wrote {len(payload['general']['results'])} district-seat entries to {OUTPUT_JSON_PATH}")


if __name__ == "__main__":
    main()
