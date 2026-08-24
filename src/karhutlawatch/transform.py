import polars as pl
import polars_st as st

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ADM1 = ROOT / "data" / "boundaries" / "geoBoundaries-IDN-ADM1-provinces.geojson"
ADM2 = ROOT / "data" / "boundaries" / "geoBoundaries-IDN-ADM2-districts.geojson"
OUTPUT_DIR = ROOT / "data" / "processed" / "firms"

def add_timestamp(df: pl.DataFrame) -> pl.DataFrame:
    return df.with_columns(
        pl.concat_str(
            [
                pl.col("acq_date"),
                pl.col("acq_time")
                .cast(pl.String)
                .str.zfill(4),
            ],
            separator=" ",
        )
        .str.strptime(pl.Datetime, "%Y-%m-%d %H%M")
        .dt.replace_time_zone("UTC")
        .alias("acquired_at_utc")
    )

def add_geometry(df: pl.DataFrame) -> pl.DataFrame:
    return df.with_columns(
        geometry=st.point(
            pl.concat_arr("longitude", "latitude"),
            srid=4326,
        )
    )

def assign_admin(
    df: pl.DataFrame,
    boundary: pl.DataFrame,
    column_name: str,
) -> pl.DataFrame:
    boundary = boundary.select(
        pl.col("shapeName").alias(column_name),
        "geometry",
    )

    return (
        df.st.sjoin(
            boundary,
            how="left",
            predicate="contains",
        )
        .drop("geometry_right")
    )

def transform_firms(
    df: pl.DataFrame,
    prov: pl.DataFrame,
    kabkota: pl.DataFrame,
) -> pl.DataFrame:
    return (
        df
        .pipe(add_timestamp)
        .pipe(add_geometry)
        .pipe(assign_admin, prov, "province")
        .pipe(assign_admin, kabkota, "kabupaten_kota")
        .filter(pl.col("province").is_not_null())
    )

def load_boundaries() -> tuple[pl.DataFrame, pl.DataFrame]:
    prov = st.read_file(ADM1)
    kabkota = st.read_file(ADM2)

    return prov, kabkota

def save_processed(
    df: pl.DataFrame,
    source: str,
    date: str,
) -> Path:
    OUTPUT_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    source_name = (
        source
        .lower()
        .replace("_nrt", "")
    )

    output_path = (
        OUTPUT_DIR
        / f"firms_{source_name}_{date}_indonesia.parquet"
    )

    df.write_parquet(output_path)

    return output_path