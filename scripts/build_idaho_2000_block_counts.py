from __future__ import annotations

from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
SHAPE_DIR = ROOT / "data" / "census" / "shapefiles"
GEOHEADER_PATH = SHAPE_DIR / "idgeo_uf1" / "idgeo.uf1"
POP_SEGMENT_PATH = SHAPE_DIR / "id00001_uf1" / "id00001.uf1"
HOUSING_SEGMENT_PATH = SHAPE_DIR / "id00037_uf1" / "id00037.uf1"
OUTPUT_PATH = ROOT / "data" / "census" / "idaho_block2000_counts.csv"


def ensure_parent(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def load_geoheader_blocks() -> pd.DataFrame:
    rows: list[dict[str, str]] = []
    with GEOHEADER_PATH.open() as fh:
        for line in fh:
            if line[8:11] != "101":
                continue
            rows.append(
                {
                    "logrecno": line[18:25],
                    "source_block_geoid": line[29:31] + line[31:34] + line[55:61] + line[62:66],
                    "source_countyfp00": line[31:34],
                    "source_tractce00": line[55:61],
                    "source_blkgrp00": line[61:62],
                    "source_blockce00": line[62:66],
                    "block_name": line[199:289].strip(),
                }
            )
    df = pd.DataFrame(rows)
    if df.empty:
        raise RuntimeError("No summary level 101 block records found in Idaho geoheader.")
    return df


def load_segment_counts(path: Path, value_name: str) -> pd.DataFrame:
    df = pd.read_csv(
        path,
        header=None,
        names=["FILEID", "STUSAB", "CHARITER", "CIFSN", "logrecno", value_name],
        usecols=[0, 1, 2, 3, 4, 5],
        dtype={"logrecno": str},
    )
    df[value_name] = pd.to_numeric(df[value_name], errors="coerce").fillna(0).astype(int)
    return df[["logrecno", value_name]].copy()


def main() -> None:
    blocks = load_geoheader_blocks()
    pop = load_segment_counts(POP_SEGMENT_PATH, "pop2000")
    housing = load_segment_counts(HOUSING_SEGMENT_PATH, "housing2000")

    merged = blocks.merge(pop, on="logrecno", how="left", validate="1:1")
    merged = merged.merge(housing, on="logrecno", how="left", validate="1:1")
    merged["pop2000"] = merged["pop2000"].fillna(0).astype(int)
    merged["housing2000"] = merged["housing2000"].fillna(0).astype(int)

    ensure_parent(OUTPUT_PATH)
    merged.to_csv(OUTPUT_PATH, index=False)
    print(f"Wrote {OUTPUT_PATH}")
    print(
        f"Rows={len(merged)} Blocks={merged['source_block_geoid'].nunique()} "
        f"Pop={int(merged['pop2000'].sum())} Housing={int(merged['housing2000'].sum())}"
    )


if __name__ == "__main__":
    main()
