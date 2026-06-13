from __future__ import annotations

import zipfile
from pathlib import Path

import geopandas as gpd
import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
CENSUS_DIR = DATA_DIR / "census"
SHAPE_DIR = CENSUS_DIR / "shapefiles"
CROSSWALKS_DIR = DATA_DIR / "crosswalks"
BLOCKS_2008_PATH = SHAPE_DIR / "tl_2008_16_tabblock00" / "tl_2008_16_tabblock00.shp"
BLOCKS_2020_PATH = SHAPE_DIR / "tl_2020_16_tabblock20" / "tl_2020_16_tabblock20.shp"
VTD00_PATH = CENSUS_DIR / "tl_2008_16_vtd00.geojson"
BLOCK_COUNTS_2000_PATH = CENSUS_DIR / "idaho_block2000_counts.csv"
NHGIS_2000_2010_ZIP = SHAPE_DIR / "nhgis_blk2000_blk2010_16.zip"
NHGIS_2010_2020_ZIP = SHAPE_DIR / "nhgis_blk2010_blk2020_16.zip"
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
        "compat_output": "precinct_to_cd119_from_2008_vtd00_nhgis_popweighted.csv",
    },
    {
        "key": "sldl2024",
        "path": CENSUS_DIR / "tl_2024_16_sldl.geojson",
        "id_col": "GEOID",
        "label_col": "NAMELSAD",
        "district_col": "district",
        "extra_cols": ["SLDLST"],
        "compat_output": "precinct_to_2024_state_house_from_2008_vtd00_nhgis_popweighted.csv",
    },
    {
        "key": "sldu2024",
        "path": CENSUS_DIR / "tl_2024_16_sldu.geojson",
        "id_col": "GEOID",
        "label_col": "NAMELSAD",
        "district_col": "district",
        "extra_cols": ["SLDUST"],
        "compat_output": "precinct_to_2024_state_senate_from_2008_vtd00_nhgis_popweighted.csv",
    },
]


def ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def read_nhgis_zip(zip_path: Path) -> pd.DataFrame:
    with zipfile.ZipFile(zip_path) as zf:
        csv_name = next(name for name in zf.namelist() if name.endswith(".csv"))
        with zf.open(csv_name) as fh:
            return pd.read_csv(fh, dtype=str)


def load_vtd00() -> gpd.GeoDataFrame:
    vtd = gpd.read_file(VTD00_PATH)
    vtd = vtd.to_crs(EQUAL_AREA_CRS)
    vtd["source_vtd_geoid"] = vtd["VTDIDFP00"].astype(str)
    vtd["source_vtd_code"] = vtd["VTDST00"].astype(str).str.zfill(6)
    vtd["source_countyfp00"] = vtd["COUNTYFP00"].astype(str).str.zfill(3)
    vtd["source_vtd_name"] = vtd["NAMELSAD00"].fillna(vtd["NAME00"]).astype(str)
    vtd["precinct_key"] = vtd["source_vtd_geoid"].astype(str)
    return vtd[
        [
            "source_vtd_geoid",
            "source_vtd_code",
            "source_countyfp00",
            "source_vtd_name",
            "precinct_key",
            "geometry",
        ]
    ].copy()


def build_source_block_lookup() -> pd.DataFrame:
    blocks = gpd.read_file(BLOCKS_2008_PATH)
    blocks = blocks.to_crs(EQUAL_AREA_CRS)
    blocks["source_block_geoid"] = blocks["BLKIDFP00"].astype(str)
    block_points = blocks[["source_block_geoid", "geometry"]].copy()
    block_points["geometry"] = block_points.representative_point()
    joined = gpd.sjoin(
        block_points,
        load_vtd00(),
        how="left",
        predicate="within",
    ).drop(columns=["index_right"])
    if joined["source_vtd_geoid"].isna().any():
        missing = int(joined["source_vtd_geoid"].isna().sum())
        raise RuntimeError(f"Failed to assign {missing} 2000 blocks to 2008 vtd00 polygons.")
    return pd.DataFrame(joined.drop(columns="geometry"))


def load_source_block_counts() -> pd.DataFrame:
    df = pd.read_csv(
        BLOCK_COUNTS_2000_PATH,
        dtype={
            "logrecno": str,
            "source_block_geoid": str,
            "source_countyfp00": str,
            "source_tractce00": str,
            "source_blkgrp00": str,
            "source_blockce00": str,
        },
    )
    df["pop2000"] = pd.to_numeric(df["pop2000"], errors="coerce").fillna(0).astype(float)
    df["housing2000"] = pd.to_numeric(df["housing2000"], errors="coerce").fillna(0).astype(float)
    return df[
        [
            "source_block_geoid",
            "logrecno",
            "source_countyfp00",
            "source_tractce00",
            "source_blkgrp00",
            "source_blockce00",
            "pop2000",
            "housing2000",
        ]
    ].copy()


def load_target(spec: dict[str, object]) -> gpd.GeoDataFrame:
    target = gpd.read_file(spec["path"])
    target = target.to_crs(EQUAL_AREA_CRS)
    cols = [str(spec["id_col"]), str(spec["label_col"]), "geometry", *spec.get("extra_cols", [])]
    if spec.get("district_col"):
        cols.append(str(spec["district_col"]))
    target = target[cols].copy()
    target["target_id"] = target[str(spec["id_col"])].astype(str)
    target["target_name"] = target[str(spec["label_col"])].fillna("").astype(str)
    if spec.get("district_col"):
        target["district_num"] = pd.to_numeric(target[str(spec["district_col"])], errors="coerce").astype("Int64")
    return target


def build_2020_block_target_lookup(spec: dict[str, object]) -> pd.DataFrame:
    blocks = gpd.read_file(BLOCKS_2020_PATH)
    blocks = blocks.to_crs(EQUAL_AREA_CRS)
    blocks["blk2020ge"] = blocks["GEOID20"].astype(str)
    block_points = blocks[["blk2020ge", "geometry"]].copy()
    block_points["geometry"] = block_points.representative_point()
    target = load_target(spec)
    joined = gpd.sjoin(block_points, target, how="left", predicate="within").drop(columns=["index_right"])
    if joined["target_id"].isna().any():
        missing = int(joined["target_id"].isna().sum())
        raise RuntimeError(f"Failed to assign {missing} 2020 blocks to {spec['key']}.")
    data = pd.DataFrame(joined.drop(columns="geometry"))
    return data.sort_values(["blk2020ge", "target_id"]).reset_index(drop=True)


def build_2000_to_2020_chain() -> pd.DataFrame:
    cw_2000_2010 = read_nhgis_zip(NHGIS_2000_2010_ZIP).rename(
        columns={"weight": "weight_2000_2010"}
    )
    cw_2010_2020 = read_nhgis_zip(NHGIS_2010_2020_ZIP).rename(
        columns={"weight": "weight_2010_2020"}
    )
    cw_2000_2010["weight_2000_2010"] = pd.to_numeric(cw_2000_2010["weight_2000_2010"], errors="coerce").fillna(0.0)
    cw_2010_2020["weight_2010_2020"] = pd.to_numeric(cw_2010_2020["weight_2010_2020"], errors="coerce").fillna(0.0)

    merged = cw_2000_2010.merge(cw_2010_2020, on="blk2010ge", how="inner", validate="m:m")
    merged["nhgis_weight"] = merged["weight_2000_2010"] * merged["weight_2010_2020"]
    merged = merged[merged["nhgis_weight"] > 0].copy()
    grouped = (
        merged.groupby(["blk2000ge", "blk2020ge"], as_index=False)
        .agg(nhgis_weight=("nhgis_weight", "sum"))
        .sort_values(["blk2000ge", "blk2020ge"])
        .reset_index(drop=True)
    )
    return grouped


def write_csv(df: pd.DataFrame, path: Path) -> None:
    ensure_dir(path.parent)
    df.to_csv(path, index=False)
    print(f"Wrote {path}")


def build_precinct_compat_crosswalk(vtd_rows: pd.DataFrame) -> pd.DataFrame:
    compat = vtd_rows[
        [
            "precinct_key",
            "district_num",
            "target_id",
            "target_name",
            "effective_weight",
            "population_weight",
            "housing_weight",
            "block_weight",
            "crosswalk_basis",
        ]
    ].copy()
    compat = compat.rename(columns={"effective_weight": "area_weight"})
    compat["district_num"] = compat["district_num"].astype("Int64")
    return compat.sort_values(["district_num", "precinct_key", "target_id"]).reset_index(drop=True)


def main() -> None:
    ensure_dir(CROSSWALKS_DIR)
    source_lookup = build_source_block_lookup()
    source_counts = load_source_block_counts()
    chain = build_2000_to_2020_chain().merge(
        source_lookup,
        left_on="blk2000ge",
        right_on="source_block_geoid",
        how="inner",
        validate="m:1",
    )
    chain = chain.merge(
        source_counts,
        on=[
            "source_block_geoid",
            "source_countyfp00",
        ],
        how="left",
        validate="m:1",
    )
    if chain["pop2000"].isna().any() or chain["housing2000"].isna().any():
        missing = int(chain["pop2000"].isna().sum() + chain["housing2000"].isna().sum())
        raise RuntimeError(f"Missing 2000 block counts for {missing} chained rows.")

    summary_rows: list[dict[str, object]] = []
    for spec in TARGETS:
        target_lookup = build_2020_block_target_lookup(spec)
        block_rows = chain.merge(target_lookup, on="blk2020ge", how="left", validate="m:1")
        if block_rows["target_id"].isna().any():
            missing = int(block_rows["target_id"].isna().sum())
            raise RuntimeError(f"Failed to assign {missing} NHGIS chained rows to {spec['key']}.")

        block_rows["crosswalk_method"] = "nhgis_block_weight_chain_2000_2010_2020"
        block_rows["source_block_weight_share"] = block_rows["nhgis_weight"]
        block_rows["allocated_pop2000"] = block_rows["pop2000"] * block_rows["nhgis_weight"]
        block_rows["allocated_housing2000"] = block_rows["housing2000"] * block_rows["nhgis_weight"]
        block_rows = block_rows.sort_values(["source_block_geoid", "target_id"]).reset_index(drop=True)

        block_out = CROSSWALKS_DIR / f"tabblock00_2008_to_{spec['key']}_nhgis.csv"
        write_csv(block_rows, block_out)

        group_cols = [
            "source_vtd_geoid",
            "source_vtd_code",
            "source_countyfp00",
            "source_vtd_name",
            "precinct_key",
            "target_id",
            "target_name",
        ]
        for col in ["district_num", "COUNTYFP", "COUNTYFP20", "prec_id", "CD119FP", "SLDLST", "SLDUST"]:
            if col in block_rows.columns:
                group_cols.append(col)

        vtd_rows = (
            block_rows.groupby(group_cols, dropna=False, as_index=False)
            .agg(
                nhgis_weight=("nhgis_weight", "sum"),
                source_blocks=("source_block_geoid", "nunique"),
                target_blocks=("blk2020ge", "nunique"),
                allocated_pop2000=("allocated_pop2000", "sum"),
                allocated_housing2000=("allocated_housing2000", "sum"),
            )
            .sort_values(["source_vtd_geoid", "target_id"])
            .reset_index(drop=True)
        )
        vtd_rows["crosswalk_method"] = "nhgis_block_weight_chain_2000_2010_2020"
        vtd_rows["source_block_weight_sum"] = vtd_rows["nhgis_weight"]
        vtd_rows["source_block_weight_avg"] = vtd_rows["nhgis_weight"] / vtd_rows["source_blocks"]
        vtd_pop_totals = vtd_rows.groupby("source_vtd_geoid")["allocated_pop2000"].transform("sum")
        vtd_housing_totals = vtd_rows.groupby("source_vtd_geoid")["allocated_housing2000"].transform("sum")
        vtd_block_totals = vtd_rows.groupby("source_vtd_geoid")["nhgis_weight"].transform("sum")
        vtd_rows["source_vtd_pop2000"] = vtd_pop_totals
        vtd_rows["source_vtd_housing2000"] = vtd_housing_totals
        vtd_rows["population_weight"] = (vtd_rows["allocated_pop2000"] / vtd_pop_totals.where(vtd_pop_totals > 0)).fillna(0.0)
        vtd_rows["housing_weight"] = (vtd_rows["allocated_housing2000"] / vtd_housing_totals.where(vtd_housing_totals > 0)).fillna(0.0)
        vtd_rows["block_weight"] = (vtd_rows["nhgis_weight"] / vtd_block_totals.where(vtd_block_totals > 0)).fillna(0.0)
        vtd_rows["effective_weight"] = vtd_rows["population_weight"]
        vtd_rows["crosswalk_basis"] = "population"
        housing_mask = (vtd_rows["effective_weight"] <= 0) & (vtd_rows["source_vtd_pop2000"] <= 0) & (vtd_rows["source_vtd_housing2000"] > 0)
        block_mask = (vtd_rows["effective_weight"] <= 0) & (vtd_rows["source_vtd_pop2000"] <= 0) & (vtd_rows["source_vtd_housing2000"] <= 0)
        vtd_rows.loc[housing_mask, "effective_weight"] = vtd_rows.loc[housing_mask, "housing_weight"]
        vtd_rows.loc[housing_mask, "crosswalk_basis"] = "housing"
        vtd_rows.loc[block_mask, "effective_weight"] = vtd_rows.loc[block_mask, "block_weight"]
        vtd_rows.loc[block_mask, "crosswalk_basis"] = "block"
        if "district_num" in vtd_rows.columns:
            vtd_rows["district_num"] = vtd_rows["district_num"].astype("Int64")

        vtd_out = CROSSWALKS_DIR / f"vtd00_2008_to_{spec['key']}_nhgis.csv"
        write_csv(vtd_rows, vtd_out)

        if spec.get("compat_output"):
            compat = build_precinct_compat_crosswalk(vtd_rows)
            write_csv(compat, CROSSWALKS_DIR / str(spec["compat_output"]))

        summary_rows.append(
            {
                "target": spec["key"],
                "block_rows": int(len(block_rows)),
                "vtd_rows": int(len(vtd_rows)),
                "source_vtd_units": int(vtd_rows["source_vtd_geoid"].nunique()),
                "target_units": int(vtd_rows["target_id"].nunique()),
                "population_total": round(float(vtd_rows["allocated_pop2000"].sum()), 4),
                "housing_total": round(float(vtd_rows["allocated_housing2000"].sum()), 4),
            }
        )

    summary = pd.DataFrame(summary_rows)
    write_csv(summary, CROSSWALKS_DIR / "crosswalk_summary_2008_to_modern_nhgis.csv")


if __name__ == "__main__":
    main()
