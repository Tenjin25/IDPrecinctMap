from __future__ import annotations

import json
import shutil
import time
import zipfile
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import urlretrieve

import geopandas as gpd
import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
CENSUS_DIR = DATA_DIR / "census"
SHAPE_DIR = CENSUS_DIR / "shapefiles"

COUNTY_ZIP_URL = "https://www2.census.gov/geo/tiger/TIGER2020/COUNTY/tl_2020_us_county.zip"
VTD_ZIP_URL_TEMPLATE = "https://www2.census.gov/geo/tiger/TIGER2020PL/LAYER/VTD/2020/tl_2020_{geoid}_vtd20.zip"
CD_ZIP_URL = "https://www2.census.gov/geo/tiger/TIGER2024/CD/tl_2024_16_cd119.zip"
SLDL_ZIP_URL = "https://www2.census.gov/geo/tiger/TIGER2024/SLDL/tl_2024_16_sldl.zip"
SLDU_ZIP_URL = "https://www2.census.gov/geo/tiger/TIGER2024/SLDU/tl_2024_16_sldu.zip"
COUNTY_2008_ZIP_URL = "https://www2.census.gov/geo/tiger/TIGER2008/16_IDAHO/tl_2008_16_county.zip"
VTD_2008_ZIP_URL_TEMPLATE = "https://www2.census.gov/geo/tiger/TIGER2008/16_IDAHO/{geoid}_{county_slug}_County/tl_2008_{geoid}_vtd00.zip"
CD_2008_ZIP_URL = "https://www2.census.gov/geo/tiger/TIGER2008/16_IDAHO/tl_2008_16_cd110.zip"
SLDL_2008_ZIP_URL = "https://www2.census.gov/geo/tiger/TIGER2008/16_IDAHO/tl_2008_16_sldl.zip"
SLDU_2008_ZIP_URL = "https://www2.census.gov/geo/tiger/TIGER2008/16_IDAHO/tl_2008_16_sldu.zip"
TABBLOCK_2008_ZIP_URL = "https://www2.census.gov/geo/tiger/TIGER2008/16_IDAHO/tl_2008_16_tabblock.zip"
TABBLOCK00_2008_ZIP_URL = "https://www2.census.gov/geo/tiger/TIGER2008/16_IDAHO/tl_2008_16_tabblock00.zip"

PALETTE = [
    (-1.0, "#08306b"),
    (-0.2, "#2171b5"),
    (-0.05, "#6baed6"),
    (0.05, "#cbd5e1"),
    (0.2, "#fcae91"),
    (1.0, "#cb181d"),
]


def ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def download(url: str, dest: Path) -> None:
    ensure_dir(dest.parent)
    if dest.exists() and dest.stat().st_size > 0:
        print(f"Using cached download {dest}")
        return
    print(f"Downloading {url} -> {dest}")
    last_err: Exception | None = None
    for attempt in range(4):
        try:
            urlretrieve(url, dest)
            return
        except HTTPError as err:
            last_err = err
            if err.code == 429 and attempt < 3:
                wait_seconds = 4 * (attempt + 1)
                print(f"Rate limited on {url}; sleeping {wait_seconds}s before retry")
                time.sleep(wait_seconds)
                continue
            raise
    if last_err:
        raise last_err


def extract(zip_path: Path, dest_dir: Path) -> None:
    if dest_dir.exists() and any(dest_dir.glob("*.shp")):
        print(f"Using cached extract {dest_dir}")
        return
    if dest_dir.exists():
        shutil.rmtree(dest_dir)
    ensure_dir(dest_dir)
    print(f"Extracting {zip_path} -> {dest_dir}")
    with zipfile.ZipFile(zip_path) as zf:
        zf.extractall(dest_dir)


def first_shp(dir_path: Path) -> Path:
    matches = sorted(dir_path.glob("*.shp"))
    if not matches:
        raise FileNotFoundError(f"No shapefile found in {dir_path}")
    return matches[0]


def county_norm(name: str) -> str:
    return "".join(ch for ch in (name or "").upper() if ch.isalnum() or ch in {" ", "-", "."}).strip()


def county_slug(name: str) -> str:
    return (name or "").replace(".", "").replace(" ", "_").replace("-", "_")


def write_geojson(gdf: gpd.GeoDataFrame, path: Path) -> None:
    ensure_dir(path.parent)
    gdf.to_file(path, driver="GeoJSON")
    print(f"Wrote {path}")


def build_counties() -> dict[str, str]:
    county_zip = SHAPE_DIR / "tl_2020_us_county.zip"
    county_extract = SHAPE_DIR / "tl_2020_us_county"
    download(COUNTY_ZIP_URL, county_zip)
    extract(county_zip, county_extract)

    counties = gpd.read_file(first_shp(county_extract))
    counties = counties[counties["STATEFP"] == "16"].copy()
    counties = counties.to_crs(4326)
    counties["NAME20"] = counties["NAME"]
    counties["county_nam"] = counties["NAME"]
    counties["STATEFP20"] = "16"
    write_geojson(counties, CENSUS_DIR / "tl_2020_16_county.geojson")
    return {str(row["COUNTYFP"]): str(row["NAME"]) for _, row in counties.iterrows()}


def build_counties_2008() -> None:
    county_zip = SHAPE_DIR / "tl_2008_16_county.zip"
    county_extract = SHAPE_DIR / "tl_2008_16_county"
    download(COUNTY_2008_ZIP_URL, county_zip)
    extract(county_zip, county_extract)

    counties = gpd.read_file(first_shp(county_extract)).to_crs(4326)
    counties["NAME20"] = counties.get("NAME", "")
    counties["county_nam"] = counties.get("NAME", "")
    write_geojson(counties, CENSUS_DIR / "tl_2008_16_county.geojson")


def build_vtd(county_names_by_fp: dict[str, str]) -> None:
    vtd_frames: list[gpd.GeoDataFrame] = []
    for county_fp in sorted(county_names_by_fp):
        geoid = f"16{county_fp}"
        vtd_zip = SHAPE_DIR / f"tl_2020_{geoid}_vtd20.zip"
        vtd_extract = SHAPE_DIR / f"tl_2020_{geoid}_vtd20"
        download(VTD_ZIP_URL_TEMPLATE.format(geoid=geoid), vtd_zip)
        extract(vtd_zip, vtd_extract)
        vtd_frames.append(gpd.read_file(first_shp(vtd_extract)).to_crs(4326))

    vtd = pd.concat(vtd_frames, ignore_index=True)
    vtd = gpd.GeoDataFrame(vtd, geometry="geometry", crs="EPSG:4326")
    vtd["county_nam"] = vtd["COUNTYFP20"].map(county_names_by_fp).fillna("")
    vtd["prec_id"] = vtd["VTDST20"].astype(str).str.strip()
    vtd["precinct_norm"] = vtd.apply(
        lambda row: f"{county_norm(row['county_nam'])} - {str(row['prec_id']).upper()}".strip(),
        axis=1,
    )
    vtd["precinct_name"] = vtd.get("NAMELSAD20", pd.Series([""] * len(vtd))).astype(str)
    write_geojson(vtd, CENSUS_DIR / "tl_2020_16_vtd20.geojson")

    centroids = vtd.copy()
    centroids["geometry"] = centroids.representative_point()
    centroid_cols = [
        "STATEFP20",
        "COUNTYFP20",
        "county_nam",
        "VTDST20",
        "VTDI20",
        "NAME20",
        "NAMELSAD20",
        "prec_id",
        "precinct_norm",
        "precinct_name",
        "geometry",
    ]
    centroid_cols = [c for c in centroid_cols if c in centroids.columns]
    write_geojson(centroids[centroid_cols], DATA_DIR / "precinct_centroids.geojson")


def build_vtd_2008(county_names_by_fp: dict[str, str]) -> None:
    vtd_frames: list[gpd.GeoDataFrame] = []
    for county_fp, county_name in sorted(county_names_by_fp.items()):
        geoid = f"16{county_fp}"
        slug = county_slug(county_name)
        vtd_zip = SHAPE_DIR / f"tl_2008_{geoid}_vtd00.zip"
        vtd_extract = SHAPE_DIR / f"tl_2008_{geoid}_vtd00"
        download(VTD_2008_ZIP_URL_TEMPLATE.format(geoid=geoid, county_slug=slug), vtd_zip)
        extract(vtd_zip, vtd_extract)
        vtd_frames.append(gpd.read_file(first_shp(vtd_extract)).to_crs(4326))

    vtd = pd.concat(vtd_frames, ignore_index=True)
    vtd = gpd.GeoDataFrame(vtd, geometry="geometry", crs="EPSG:4326")
    county_name_col = "COUNTY" if "COUNTY" in vtd.columns else None
    if county_name_col:
        vtd["county_nam"] = vtd[county_name_col].astype(str).str.replace(" County", "", regex=False).str.strip()
    else:
        vtd["county_nam"] = ""
    vtd["prec_id"] = vtd.get("VTD00", pd.Series([""] * len(vtd))).astype(str).str.strip()
    vtd["precinct_norm"] = vtd.apply(
        lambda row: f"{county_norm(row['county_nam'])} - {str(row['prec_id']).upper()}".strip(),
        axis=1,
    )
    vtd["precinct_name"] = vtd["prec_id"]
    write_geojson(vtd, CENSUS_DIR / "tl_2008_16_vtd00.geojson")

    centroids = vtd.copy()
    centroids["geometry"] = centroids.representative_point()
    centroid_cols = [
        "STATEFP00",
        "COUNTYFP00",
        "county_nam",
        "VTD00",
        "NAME00",
        "prec_id",
        "precinct_norm",
        "precinct_name",
        "geometry",
    ]
    centroid_cols = [c for c in centroid_cols if c in centroids.columns]
    write_geojson(centroids[centroid_cols], DATA_DIR / "precinct_centroids_2008.geojson")


def _load_statewide_district_geojson(url: str, output_name: str, district_field: str) -> list[int]:
    zip_path = SHAPE_DIR / f"{output_name}.zip"
    extract_dir = SHAPE_DIR / output_name
    download(url, zip_path)
    extract(zip_path, extract_dir)

    gdf = gpd.read_file(first_shp(extract_dir)).to_crs(4326)
    if district_field not in gdf.columns:
        raise KeyError(f"{district_field} missing from {output_name}")
    gdf["district"] = pd.to_numeric(gdf[district_field], errors="coerce").fillna(0).astype(int)
    write_geojson(gdf, CENSUS_DIR / f"{output_name}.geojson")
    return sorted(n for n in gdf["district"].dropna().unique().tolist() if int(n) > 0)


def write_district_info_csv(path: Path, districts: list[int], label: str) -> None:
    ensure_dir(path.parent)
    rows = [
        {
            "district": district,
            "name": f"{label} {district}",
            "total_population": 0,
            "white_vap_pct": 0,
            "black_vap_pct": 0,
            "hispanic_vap_pct": 0,
        }
        for district in districts
    ]
    pd.DataFrame(rows).to_csv(path, index=False)
    print(f"Wrote {path}")


def build_district_assets() -> None:
    congressional = _load_statewide_district_geojson(CD_ZIP_URL, "tl_2024_16_cd119", "CD119FP")
    state_house = _load_statewide_district_geojson(SLDL_ZIP_URL, "tl_2024_16_sldl", "SLDLST")
    state_senate = _load_statewide_district_geojson(SLDU_ZIP_URL, "tl_2024_16_sldu", "SLDUST")

    write_district_info_csv(DATA_DIR / "id_congressional_districts.csv", congressional, "Congressional District")
    write_district_info_csv(DATA_DIR / "id_state_house_districts.csv", state_house, "State House District")
    write_district_info_csv(DATA_DIR / "id_state_senate_districts.csv", state_senate, "State Senate District")

    descriptions_path = DATA_DIR / "district_descriptions.json"
    descriptions_path.write_text(
        json.dumps({"congressional": {}, "state_house": {}, "state_senate": {}}, indent=2),
        encoding="utf-8",
    )
    print(f"Wrote {descriptions_path}")


def build_district_assets_2008() -> None:
    _load_statewide_district_geojson(CD_2008_ZIP_URL, "tl_2008_16_cd110", "CD110FP")
    _load_statewide_district_geojson(SLDL_2008_ZIP_URL, "tl_2008_16_sldl", "SLDLST")
    _load_statewide_district_geojson(SLDU_2008_ZIP_URL, "tl_2008_16_sldu", "SLDUST")


def build_tabblocks_2008() -> None:
    for output_name, url in [
        ("tl_2008_16_tabblock", TABBLOCK_2008_ZIP_URL),
        ("tl_2008_16_tabblock00", TABBLOCK00_2008_ZIP_URL),
    ]:
        zip_path = SHAPE_DIR / f"{output_name}.zip"
        extract_dir = SHAPE_DIR / output_name
        download(url, zip_path)
        extract(zip_path, extract_dir)
        print(f"Prepared crosswalk asset {extract_dir}")

    notes_path = CENSUS_DIR / "crosswalk_assets_2008.txt"
    notes_path.write_text(
        "\n".join(
            [
                "2008 Idaho crosswalk assets downloaded from the U.S. Census Bureau TIGER/Line archive.",
                "Files prepared for crosswalk work:",
                "- tl_2008_16_tabblock.zip and extracted shapefile directory",
                "- tl_2008_16_tabblock00.zip and extracted shapefile directory",
                "- county-by-county tl_2008_<geoid>_vtd00.zip extracts",
                "- tl_2008_16_cd110.zip extract",
                "- tl_2008_16_sldl.zip extract",
                "- tl_2008_16_sldu.zip extract",
            ]
        ),
        encoding="utf-8",
    )
    print(f"Wrote {notes_path}")


def main() -> None:
    ensure_dir(CENSUS_DIR)
    ensure_dir(SHAPE_DIR)
    names = build_counties()
    build_counties_2008()
    build_vtd(names)
    build_vtd_2008(names)
    build_district_assets()
    build_district_assets_2008()
    build_tabblocks_2008()


if __name__ == "__main__":
    main()
