from __future__ import annotations

from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
CROSSWALKS_DIR = ROOT / "data" / "crosswalks"


SPECS = [
    {
        "key": "cd119",
        "block_file": CROSSWALKS_DIR / "tabblock00_2008_to_cd119_nhgis.csv",
        "detail_output": CROSSWALKS_DIR / "vtd20_2020_to_cd119_nhgis.csv",
        "compat_output": CROSSWALKS_DIR / "precinct_to_cd119_from_2020_vtd20_nhgis_popweighted.csv",
    },
    {
        "key": "sldl2024",
        "block_file": CROSSWALKS_DIR / "tabblock00_2008_to_sldl2024_nhgis.csv",
        "detail_output": CROSSWALKS_DIR / "vtd20_2020_to_sldl2024_nhgis.csv",
        "compat_output": CROSSWALKS_DIR / "precinct_to_2024_state_house_from_2020_vtd20_nhgis_popweighted.csv",
    },
    {
        "key": "sldu2024",
        "block_file": CROSSWALKS_DIR / "tabblock00_2008_to_sldu2024_nhgis.csv",
        "detail_output": CROSSWALKS_DIR / "vtd20_2020_to_sldu2024_nhgis.csv",
        "compat_output": CROSSWALKS_DIR / "precinct_to_2024_state_senate_from_2020_vtd20_nhgis_popweighted.csv",
    },
]


def load_vtd20_block_rows() -> pd.DataFrame:
    path = CROSSWALKS_DIR / "tabblock00_2008_to_vtd20_nhgis.csv"
    df = pd.read_csv(
        path,
        dtype={
            "blk2000ge": str,
            "blk2020ge": str,
            "source_block_geoid": str,
            "GEOID20": str,
            "target_id": str,
            "COUNTYFP20": str,
            "prec_id": str,
            "precinct_norm": str,
        },
        low_memory=False,
    )
    df["COUNTYFP20"] = df["COUNTYFP20"].fillna("").astype(str).str.replace(r"[^0-9]", "", regex=True).str.zfill(3)
    df["prec_id"] = df["prec_id"].fillna("").astype(str).str.replace(r"[^0-9A-Za-z]", "", regex=True).str.upper()
    df.loc[df["prec_id"].str.fullmatch(r"\d+"), "prec_id"] = df.loc[df["prec_id"].str.fullmatch(r"\d+"), "prec_id"].str.zfill(6)
    return df[
        [
            "blk2000ge",
            "blk2020ge",
            "source_block_geoid",
            "GEOID20",
            "precinct_norm",
            "COUNTYFP20",
            "prec_id",
        ]
    ].copy()


def build_vtd20_to_target(vtd20_blocks: pd.DataFrame, target_block_file: Path) -> tuple[pd.DataFrame, pd.DataFrame]:
    target_blocks = pd.read_csv(
        target_block_file,
        dtype={"blk2000ge": str, "blk2020ge": str, "source_block_geoid": str, "target_id": str},
    )
    merged = vtd20_blocks.merge(
        target_blocks,
        on=["blk2000ge", "blk2020ge", "source_block_geoid"],
        how="inner",
        validate="1:1",
    )

    detail = (
        merged.groupby(
            [
                "GEOID20",
                "precinct_norm",
                "COUNTYFP20",
                "prec_id",
                "target_id",
                "target_name",
                "district_num",
            ],
            dropna=False,
            as_index=False,
        )
        .agg(
            nhgis_weight=("nhgis_weight", "sum"),
            source_blocks=("source_block_geoid", "nunique"),
            target_blocks=("blk2020ge", "nunique"),
            allocated_pop2000=("allocated_pop2000", "sum"),
            allocated_housing2000=("allocated_housing2000", "sum"),
        )
        .sort_values(["GEOID20", "district_num", "target_id"])
        .reset_index(drop=True)
    )
    detail["crosswalk_method"] = "nhgis_block_weight_chain_2000_2010_2020"
    detail["source_vtd20_pop2000"] = detail.groupby("GEOID20")["allocated_pop2000"].transform("sum")
    detail["source_vtd20_housing2000"] = detail.groupby("GEOID20")["allocated_housing2000"].transform("sum")
    detail["source_vtd20_block_weight"] = detail.groupby("GEOID20")["nhgis_weight"].transform("sum")
    detail["population_weight"] = (
        detail["allocated_pop2000"] / detail["source_vtd20_pop2000"].where(detail["source_vtd20_pop2000"] > 0)
    ).fillna(0.0)
    detail["housing_weight"] = (
        detail["allocated_housing2000"] / detail["source_vtd20_housing2000"].where(detail["source_vtd20_housing2000"] > 0)
    ).fillna(0.0)
    detail["block_weight"] = (
        detail["nhgis_weight"] / detail["source_vtd20_block_weight"].where(detail["source_vtd20_block_weight"] > 0)
    ).fillna(0.0)
    detail["effective_weight"] = detail["population_weight"]
    detail["crosswalk_basis"] = "population"

    housing_mask = (
        (detail["effective_weight"] <= 0)
        & (detail["source_vtd20_pop2000"] <= 0)
        & (detail["source_vtd20_housing2000"] > 0)
    )
    block_mask = (
        (detail["effective_weight"] <= 0)
        & (detail["source_vtd20_pop2000"] <= 0)
        & (detail["source_vtd20_housing2000"] <= 0)
    )
    detail.loc[housing_mask, "effective_weight"] = detail.loc[housing_mask, "housing_weight"]
    detail.loc[housing_mask, "crosswalk_basis"] = "housing"
    detail.loc[block_mask, "effective_weight"] = detail.loc[block_mask, "block_weight"]
    detail.loc[block_mask, "crosswalk_basis"] = "block"
    detail["district_num"] = pd.to_numeric(detail["district_num"], errors="coerce").astype("Int64")

    compat = detail[
        [
            "GEOID20",
            "precinct_norm",
            "COUNTYFP20",
            "prec_id",
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
    compat = compat.rename(columns={"GEOID20": "precinct_key", "effective_weight": "area_weight"})
    compat = compat.sort_values(["district_num", "precinct_key", "target_id"]).reset_index(drop=True)
    return detail, compat


def write_csv(df: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(path, index=False)
    print(f"Wrote {path}")


def main() -> None:
    vtd20_blocks = load_vtd20_block_rows()
    summary_rows: list[dict[str, object]] = []
    for spec in SPECS:
        detail, compat = build_vtd20_to_target(vtd20_blocks, spec["block_file"])
        write_csv(detail, spec["detail_output"])
        write_csv(compat, spec["compat_output"])
        summary_rows.append(
            {
                "target": spec["key"],
                "rows": int(len(detail)),
                "source_vtd20_units": int(detail["GEOID20"].nunique()),
                "target_units": int(detail["target_id"].nunique()),
                "population_total": round(float(detail["allocated_pop2000"].sum()), 4),
                "housing_total": round(float(detail["allocated_housing2000"].sum()), 4),
            }
        )
    write_csv(pd.DataFrame(summary_rows), CROSSWALKS_DIR / "crosswalk_summary_2020_vtd20_to_2024_districts_nhgis.csv")


if __name__ == "__main__":
    main()
