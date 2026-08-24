from pathlib import Path

import polars as pl


ROOT = Path(__file__).resolve().parents[2]

PROCESSED_DIR = ROOT / "data" / "processed" / "firms"
ANALYTICS_DIR = ROOT / "data" / "analytics"

MONTHLY_OUTPUT = ANALYTICS_DIR / "firms_30d.parquet"
PROVINCE_OUTPUT = ANALYTICS_DIR / "daily_province.parquet"
KABKOTA_OUTPUT = ANALYTICS_DIR / "daily_kabupaten_kota.parquet"


def load_firms() -> pl.DataFrame:
    return (
        pl.scan_parquet(
            PROCESSED_DIR / "firms_viirs_noaa20_*_indonesia.parquet"
        )
        .sort("acquired_at_utc")
        .collect()
    )


def aggregate_province(df: pl.DataFrame) -> pl.DataFrame:
    return (
        df
        .group_by(
            "acq_date",
            "province",
        )
        .agg(
            pl.len().alias("hotspot_count"),

            (pl.col("confidence") == "h")
            .sum()
            .alias("high_confidence_count"),

            pl.col("frp")
            .sum()
            .alias("total_frp"),

            pl.col("frp")
            .max()
            .alias("max_frp"),
        )
        .sort(
            ["acq_date", "hotspot_count"],
            descending=[False, True],
        )
    )


def aggregate_kabkota(df: pl.DataFrame) -> pl.DataFrame:
    return (
        df
        .group_by(
            "acq_date",
            "province",
            "kabupaten_kota",
        )
        .agg(
            pl.len().alias("hotspot_count"),

            (pl.col("confidence") == "h")
            .sum()
            .alias("high_confidence_count"),

            pl.col("frp")
            .sum()
            .alias("total_frp"),

            pl.col("frp")
            .max()
            .alias("max_frp"),
        )
        .sort(
            ["acq_date", "hotspot_count"],
            descending=[False, True],
        )
    )


def main():
    ANALYTICS_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    firms = load_firms()
    firms.write_parquet(MONTHLY_OUTPUT)

    province = aggregate_province(firms)
    kabkota = aggregate_kabkota(firms)

    province.write_parquet(PROVINCE_OUTPUT)
    kabkota.write_parquet(KABKOTA_OUTPUT)

    print(f"Hotspot rows: {firms.height:,}")
    print(f"Province summary rows: {province.height:,}")
    print(f"Kab/Kota summary rows: {kabkota.height:,}")


if __name__ == "__main__":
    main()