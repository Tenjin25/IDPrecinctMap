"""Build Idaho county Census profiles and block-disaggregated CVAP map profiles.

County shares use mutually exclusive 2020 Census P2 categories. Precinct and
2024 district shares use RDH's 2020-2024 CVAP disaggregated to 2020 blocks.
Block interior points assign estimates to current map polygons.
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import zipfile
from collections import defaultdict
from pathlib import Path

import shapefile
from shapely.geometry import Point, shape
from shapely.strtree import STRtree


ROOT = Path(__file__).resolve().parents[1]
FIELDS = (
    "CVAP_TOT24", "CVAP_WHT24", "CVAP_BLA24", "CVAP_HSP24",
    "CVAP_AMI24", "CVAP_ASI24", "CVAP_NHP24", "CVAP_2OM24",
    "CVAP_AIW24", "CVAP_ASW24", "CVAP_BLW24", "CVAP_AIB24",
)
RACES = ("white", "black", "hispanic", "native", "asian", "pacific", "multiracial")
TARGETS = (
    ("precinct", "data/census/tl_2020_16_vtd20.geojson", "precinct_norm"),
    ("congressional", "data/census/tl_2024_16_cd119.geojson", "CD119FP"),
    ("state_house", "data/census/tl_2024_16_sldl.geojson", "SLDLST"),
    ("state_senate", "data/census/tl_2024_16_sldu.geojson", "SLDUST"),
)


def pct(value: int, total: int) -> float:
    return round(value * 100 / total, 2) if total else 0.0


def write_counties(census_zip: Path) -> None:
    with zipfile.ZipFile(census_zip) as archive:
        counties = {}
        for line in archive.open("idgeo2020.pl"):
            row = line.decode("latin-1").rstrip("\r\n").split("|")
            if row[2] == "050":
                counties[row[7]] = (row[9], row[86])
        profiles = {}
        for line in archive.open("id000012020.pl"):
            row = line.decode("latin-1").rstrip("\r\n").split("|")
            if row[4] not in counties:
                continue
            geoid, name = counties[row[4]]
            # Segment 1: 5 control columns, P1 (71), then P2 (73).
            p2 = [int(value or 0) for value in row[76:149]]
            total = p2[0]
            if not total:
                continue
            counts = {
                "white": p2[4], "black": p2[5], "hispanic": p2[1],
                "native": p2[6], "asian": p2[7], "pacific": p2[8],
                "multiracial": p2[10],
            }
            key = str(name).strip().upper()
            profiles[key] = {
                "county": name, "geoid20": geoid, "total_pop": total,
                **{f"{race}_pop": counts[race] for race in RACES},
                **{f"{race}_pop_pct": pct(counts[race], total) for race in RACES},
            }
        vap = {}
        for line in archive.open("id000022020.pl"):
            row = line.decode("latin-1").rstrip("\r\n").split("|")
            if row[4] in counties:
                # Segment 2 begins with P3; P3_001 is total VAP.
                vap[row[4]] = int(row[5] or 0)
        for logical_record, (_, name) in counties.items():
            key = str(name).strip().upper()
            if key in profiles:
                profiles[key]["vap_18plus"] = vap.get(logical_record, 0)
    if len(profiles) != 44:
        raise RuntimeError(f"Expected 44 Idaho counties, got {len(profiles)}")
    if sum(row["total_pop"] for row in profiles.values()) != 1839106:
        raise RuntimeError("Idaho county population does not reconcile to the 2020 Census state total")
    payload = {
        "source": "2020 Census P.L. 94-171 P2/P3, Idaho State Summary File",
        "notes": [
            "Race shares use total 2020 population, not CVAP.",
            "Categories are non-Hispanic race alone, Hispanic of any race, and non-Hispanic two or more races.",
            "vap_18plus is total voting-age population from P3.",
        ],
        "counties": profiles,
    }
    (ROOT / "data/county_demographics_2020_pl.json").write_text(
        json.dumps(payload, separators=(",", ":")) + "\n", encoding="utf-8"
    )


def load_target(path: Path, field: str) -> tuple[list, list[str], STRtree]:
    features = json.loads(path.read_text(encoding="utf-8"))["features"]
    geometries, keys = [], []
    for feature in features:
        props = feature["properties"]
        raw = str(props.get(field) or "").strip()
        if not raw:
            continue
        key = raw.upper() if field == "precinct_norm" else str(int(raw))
        geometries.append(shape(feature["geometry"]))
        keys.append(key)
    return geometries, keys, STRtree(geometries)


def target_key(point: Point, target: tuple[list, list[str], STRtree]) -> str | None:
    geometries, keys, tree = target
    for raw_idx in tree.query(point):
        idx = int(raw_idx)
        if geometries[idx].covers(point):
            return keys[idx]
    nearest = tree.nearest(point)
    return keys[int(nearest)] if nearest is not None else None


def race_counts(values: list[int]) -> list[int]:
    (_, white, black, hispanic, native, asian, pacific, other,
     aiw, asw, blw, aib) = values
    return [white, black, hispanic, native, asian, pacific, other + aiw + asw + blw + aib]


def write_csv(path: Path, header: list[str], rows: list[list]) -> None:
    with path.open("w", newline="", encoding="utf-8") as target:
        writer = csv.writer(target)
        writer.writerow(header)
        writer.writerows(rows)


def build_cvap(cvap_zip: Path, block_zip: Path) -> None:
    targets = [load_target(ROOT / relpath, field) for _, relpath, field in TARGETS]
    grouped = [defaultdict(lambda: [0] * len(FIELDS)) for _ in targets]
    with zipfile.ZipFile(cvap_zip) as archive:
        filename = next(name for name in archive.namelist() if name.lower().endswith(".csv"))
        lines = (line.decode("utf-8-sig") for line in archive.open(filename))
        reader = csv.DictReader(lines)
        estimates = {
            str(row["GEOID20"]): [int(float(row.get(field) or 0)) for field in FIELDS]
            for row in reader
        }
    with zipfile.ZipFile(block_zip) as archive:
        dbf_name = next(name for name in archive.namelist() if name.lower().endswith('.dbf'))
        sf = shapefile.Reader(dbf=io.BytesIO(archive.read(dbf_name)))
    names = [field[0] for field in sf.fields[1:]]
    indices = [names.index(field) for field in ("GEOID20", "INTPTLON20", "INTPTLAT20")]
    matched = 0
    for record in sf.iterRecords():
        geoid, lon, lat = (record[idx] for idx in indices)
        values = estimates.get(str(geoid))
        if values is None:
            continue
        matched += 1
        point = Point(float(lon), float(lat))
        for target, sums in zip(targets, grouped):
            key = target_key(point, target)
            if key is None:
                continue
            accum = sums[key]
            for idx, value in enumerate(values):
                accum[idx] += value
    if matched < 80000:
        raise RuntimeError(f"Only {matched} block GEOIDs matched CVAP source")
    source_total = sum(values[0] for values in estimates.values())
    for label, sums in zip((item[0] for item in TARGETS), grouped):
        if sum(values[0] for values in sums.values()) != source_total:
            raise RuntimeError(f"{label} CVAP does not reconcile to the block source")

    precinct_rows = []
    for key, values in sorted(grouped[0].items()):
        total = values[0]
        races = race_counts(values)
        precinct_rows.append([
            key, total, *races, *[pct(value, total) for value in races],
        ])
    write_csv(
        ROOT / "data/precinct_demographics_2020_vap.csv",
        ["precinct_id", "vap_18plus", *[f"{race}_vap" for race in RACES],
         *[f"{race}_vap_pct" for race in RACES]],
        precinct_rows,
    )
    write_csv(
        ROOT / "data/cvap_aggregates/precinct_2020__cvap24.csv",
        ["precinct_id", "CVAP_TOT24"],
        [[row[0], row[1]] for row in precinct_rows],
    )
    names = ("Congressional District", "State House District", "State Senate District")
    files = ("id_congressional_districts.csv", "id_state_house_districts.csv", "id_state_senate_districts.csv")
    for label, filename, sums in zip(names, files, grouped[1:]):
        rows = []
        for key, values in sorted(sums.items(), key=lambda item: int(item[0])):
            total = values[0]
            races = race_counts(values)
            rows.append([key, f"{label} {key}", "", total, *[pct(value, total) for value in races]])
        write_csv(
            ROOT / "data" / filename,
            ["district", "name", "total_population", "cvap_total",
             *[f"{race}_vap_pct" for race in RACES]],
            rows,
        )
    print(f"Matched {matched:,} blocks; precincts={len(precinct_rows):,}; districts=" +
          ",".join(str(len(sums)) for sums in grouped[1:]))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cvap-zip", type=Path, required=True)
    parser.add_argument("--census-zip", type=Path, default=ROOT / "data/census/id2020.pl.zip")
    parser.add_argument("--block-zip", type=Path, default=ROOT / "data/census/shapefiles/tl_2020_16_tabblock20.zip")
    args = parser.parse_args()
    write_counties(args.census_zip)
    build_cvap(args.cvap_zip, args.block_zip)


if __name__ == "__main__":
    main()
