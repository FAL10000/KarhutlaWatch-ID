import polars as pl

df = pl.read_parquet("../../data/raw/firms_noaa20.parquet")

df = df.with_columns(
    pl.concat_str(
        [
            pl.col("acq_date").cast(pl.String),
            pl.col("acq_time").cast(pl.String).str.zfill(4),
        ],
        separator=" ",
    )
    .str.strptime(pl.Datetime, "%Y-%m-%d %H%M")
    .dt.replace_time_zone("UTC")
    .alias("acquired_at_utc")
)

df.write_parquet("../../data/processed/firms_noaa20.parquet")