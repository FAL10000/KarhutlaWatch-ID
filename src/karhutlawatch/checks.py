import polars as pl

df = pl.read_parquet("../../data/raw/firms_noaa20.parquet")

print(df)
print(df.schema)
print(df.shape)

print(
    df.select(
        pl.col("acq_date").min().alias("first_date"),
        pl.col("acq_date").max().alias("last_date"),
        pl.col("latitude").min().alias("min_lat"),
        pl.col("latitude").max().alias("max_lat"),
        pl.col("longitude").min().alias("min_lon"),
        pl.col("longitude").max().alias("max_lon"),
        pl.col("frp").min().alias("min_frp"),
        pl.col("frp").max().alias("max_frp"),
    )
)

print(df.group_by("confidence").len())