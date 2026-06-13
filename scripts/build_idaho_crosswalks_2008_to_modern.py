from __future__ import annotations

from pathlib import Path

import geopandas as gpd
import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
CENSUS_DIR = DATA_DIR / "census"
CROSSWALKS_DIR = DATA_DIR / "crosswalks"
BLOCKS_2008_PATH = CENSUS_DIR / "shapefiles" / "tl_2008_16_tabblock00" / "tl_2008_16_tabblock00.shp"
VTD00_PATH = CENSUS_DIR / "tl_2008_16_vtd00.geojson"
EQUAL_AREA_CRS = "EPSG:5070"


TARGETS = [
    {
        "key": "county2020",
        "path": CENSUS_DIR / "tl_2020_16_county.geojson",
        "id_col": "GEOID",
        "label_col": "NAME20",
        "extra_cols": ["COUNTYFP"],
    },
    {
        "key": "vtd20",
        "path": CENSUS_DIR / "tl_2020_16_vtd20.geojson",
        "id_col": "GEOID20",
        "label_col": "precinct_norm",
        "extra_cols": ["COUNTYFP20", "prec_id"],
    },
    {
        "key": "cd119",
        "path": CENSUS_DIR / "tl_2024_16_cd119.geojson",
        "id_col": "GEOID",
        "label_col": "NAMELSAD",
        "district_col": "district",
        "extra_cols": ["CD119FP"],
        "compat_output": "precinct_to_cd119_from_2008_vtd00.csv",
    },
    {
        "key": "sldl2024",
        "path": CENSUS_DIR / "tl_2024_16_sldl.geojson",
        "id_col": "GEOID",
        "label_col": "NAMELSAD",
        "district_col": "district",
        "extra_cols": ["SLDLST"],
        "compat_output": "precinct_to_2024_state_house_from_2008_vtd00.csv",
    },
    {
        "key": "sldu2024",
        "path": CENSUS_DIR / "tl_2024_16_sldu.geojson",
        "id_col": "GEOID",
        "label_col": "NAMELSAD",
        "district_col": "district",
        "extra_cols": ["SLDUST"],
        "compat_output": "precinct_to_2024_state_senate_from_2008_vtd00.csv",
    },
]


def ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def load_blocks() -> gpd.GeoDataFrame:
    blocks = gpd.read_file(BLOCKS_2008_PATH)
    blocks = blocks.to_crs(EQUAL_AREA_CRS)
    blocks["source_block_geoid"] = blocks["BLKIDFP00"].astype(str)
    blocks["source_countyfp00"] = blocks["COUNTYFP00"].astype(str).str.zfill(3)
    blocks["source_tractce00"] = blocks["TRACTCE00"].astype(str).str.zfill(6)
    blocks["source_blockce00"] = blocks["BLOCKCE00"].astype(str).str.zfill(4)
    blocks["source_area_m2"] = blocks.geometry.area
    return blocks[
        [
            "source_block_geoid",
            "source_countyfp00",
            "source_tractce00",
            "source_blockce00",
            "source_area_m2",
            "geometry",
        ]
    ].copy()


def load_vtd00() -> gpd.GeoDataFrame:
    vtd = gpd.read_file(VTD00_PATH)
    vtd = vtd.to_crs(EQUAL_AREA_CRS)
    vtd["source_vtd_geoid"] = vtd["VTDIDFP00"].astype(str)
    vtd["source_vtd_code"] = vtd["VTDST00"].astype(str).str.zfill(6)
    vtd["source_countyfp00"] = vtd["COUNTYFP00"].astype(str).str.zfill(3)
    vtd["source_vtd_name"] = vtd["NAMELSAD00"].fillna(vtd["NAME00"]).astype(str)
    vtd["source_vtd_area_m2"] = vtd.geometry.area
    vtd["precinct_key"] = vtd["source_vtd_geoid"].astype(str)
    return vtd[
        [
            "source_vtd_geoid",
            "source_vtd_code",
            "source_countyfp00",
            "source_vtd_name",
            "source_vtd_area_m2",
            "precinct_key",
            "geometry",
        ]
    ].copy()


def attach_vtd_to_blocks(blocks: gpd.GeoDataFrame, vtd: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    block_points = blocks.copy()
    block_points["geometry"] = block_points.representative_point()
    joined = gpd.sjoin(
        block_points,
        vtd[
            [
                "source_vtd_geoid",
                "source_vtd_code",
                "source_vtd_name",
                "source_vtd_area_m2",
                "precinct_key",
                "geometry",
            ]
        ],
        how="left",
        predicate="within",
    ).drop(columns=["index_right"])

    missing = joined["source_vtd_geoid"].isna().sum()
    if missing:
        raise RuntimeError(f"Failed to assign {missing} tabblock00 features to a 2008 vtd00 polygon.")

    merged = blocks.merge(
        joined[
            [
                "source_block_geoid",
                "source_vtd_geoid",
                "source_vtd_code",
                "source_vtd_name",
                "source_vtd_area_m2",
                "precinct_key",
            ]
        ],
        on="source_block_geoid",
        how="left",
        validate="1:1",
    )
    return merged


def load_target(spec: dict[str, object]) -> gpd.GeoDataFrame:
    target = gpd.read_file(spec["path"])
    target = target.to_crs(EQUAL_AREA_CRS)
    id_col = str(spec["id_col"])
    label_col = str(spec["label_col"])
    cols = [id_col, label_col, "geometry", *spec.get("extra_cols", [])]
    if spec.get("district_col"):
        cols.append(str(spec["district_col"]))
    target = target[cols].copy()
    target["target_id"] = target[id_col].astype(str)
    target["target_name"] = target[label_col].fillna("").astype(str)
    if spec.get("district_col"):
        target["district_num"] = pd.to_numeric(target[str(spec["district_col"])], errors="coerce").astype("Int64")
    return target


def build_block_crosswalk(blocks: gpd.GeoDataFrame, target: gpd.GeoDataFrame) -> pd.DataFrame:
    keep_cols = [
        "source_block_geoid",
        "source_countyfp00",
        "source_tractce00",
        "source_blockce00",
        "source_area_m2",
        "source_vtd_geoid",
        "source_vtd_code",
        "source_vtd_name",
        "source_vtd_area_m2",
        "precinct_key",
        "geometry",
    ]
    overlaps = gpd.overlay(blocks[keep_cols], target, how="intersection", keep_geom_type=True)
    overlaps["intersection_area_m2"] = overlaps.geometry.area
    overlaps = overlaps[overlaps["intersection_area_m2"] > 0].copy()
    overlaps["area_weight"] = overlaps["intersection_area_m2"] / overlaps["source_area_m2"]
    overlaps["source_area_share_pct"] = overlaps["area_weight"] * 100.0
    data = pd.DataFrame(overlaps.drop(columns="geometry"))
    if "district_num" in data.columns:
        data["district_num"] = data["district_num"].astype("Int64")
    return data.sort_values(["source_block_geoid", "target_id"]).reset_index(drop=True)


def aggregate_to_vtd(block_rows: pd.DataFrame) -> pd.DataFrame:
    group_cols = [
        "source_vtd_geoid",
        "source_vtd_code",
        "source_vtd_name",
        "source_vtd_area_m2",
        "precinct_key",
        "target_id",
        "target_name",
    ]
    extra_cols: list[str] = []
    if "district_num" in block_rows.columns:
        extra_cols.append("district_num")
    for col in ["COUNTYFP", "COUNTYFP20", "prec_id", "CD119FP", "SLDLST", "SLDUST"]:
        if col in block_rows.columns:
            extra_cols.append(col)
    group_cols.extend(extra_cols)

    aggregated = (
        block_rows.groupby(group_cols, dropna=False, as_index=False)
        .agg(
            intersection_area_m2=("intersection_area_m2", "sum"),
            source_blocks=("source_block_geoid", "nunique"),
        )
        .copy()
    )
    aggregated["area_weight"] = aggregated["intersection_area_m2"] / aggregated["source_vtd_area_m2"]
    aggregated["source_area_share_pct"] = aggregated["area_weight"] * 100.0
    if "district_num" in aggregated.columns:
        aggregated["district_num"] = aggregated["district_num"].astype("Int64")
    return aggregated.sort_values(["source_vtd_geoid", "target_id"]).reset_index(drop=True)


def write_csv(df: pd.DataFrame, path: Path) -> None:
    ensure_dir(path.parent)
    df.to_csv(path, index=False)
    print(f"Wrote {path}")


def build_compat_crosswalk(vtd_rows: pd.DataFrame) -> pd.DataFrame:
    compat = vtd_rows[["precinct_key", "district_num", "target_id", "target_name", "area_weight"]].copy()
    compat["district_num"] = compat["district_num"].astype("Int64")
    compat = compat.sort_values(["district_num", "precinct_key", "target_id"]).reset_index(drop=True)
    return compat


def main() -> None:
    ensure_dir(CROSSWALKS_DIR)
    blocks = load_blocks()
    vtd00 = load_vtd00()
    blocks = attach_vtd_to_blocks(blocks, vtd00)

    summary_rows: list[dict[str, object]] = []
    for spec in TARGETS:
        target = load_target(spec)
        block_rows = build_block_crosswalk(blocks, target)
        vtd_rows = aggregate_to_vtd(block_rows)

        write_csv(block_rows, CROSSWALKS_DIR / f"tabblock00_2008_to_{spec['key']}.csv")
        write_csv(vtd_rows, CROSSWALKS_DIR / f"vtd00_2008_to_{spec['key']}.csv")

        if spec.get("compat_output"):
            compat = build_compat_crosswalk(vtd_rows)
            write_csv(compat, CROSSWALKS_DIR / str(spec["compat_output"]))

        summary_rows.append(
            {
                "target": spec["key"],
                "block_rows": int(len(block_rows)),
                "vtd_rows": int(len(vtd_rows)),
                "target_units": int(target["target_id"].nunique()),
                "source_vtd_units": int(vtd_rows["source_vtd_geoid"].nunique()),
            }
        )

    summary = pd.DataFrame(summary_rows)
    write_csv(summary, CROSSWALKS_DIR / "crosswalk_summary_2008_to_modern.csv")


if __name__ == "__main__":
    main()
