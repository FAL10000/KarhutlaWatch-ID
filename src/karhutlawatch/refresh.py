import argparse
from datetime import datetime, timezone
from pathlib import Path

import polars as pl

from karhutlawatch.aggregate import (
    aggregate_kabkota,
    aggregate_province,
)
from karhutlawatch.firms import (
    fetch_firms,
    save_raw,
)
from karhutlawatch.monitoring import (
    build_daily_clusters,
    build_monitoring_areas,
    track_clusters,
)
from karhutlawatch.transform import (
    ADM1,
    ADM2,
    load_boundaries,
    save_processed,
    transform_firms,
)


ROOT = Path(__file__).resolve().parents[2]

ANALYTICS_DIR = ROOT / "data" / "analytics"

FIRMS_OUTPUT = ANALYTICS_DIR / "firms_30d.parquet"
PROVINCE_OUTPUT = ANALYTICS_DIR / "daily_province.parquet"
KABKOTA_OUTPUT = ANALYTICS_DIR / "daily_kabupaten_kota.parquet"
CLUSTERS_OUTPUT = ANALYTICS_DIR / "hotspot_clusters.parquet"
MONITORING_OUTPUT = ANALYTICS_DIR / "monitoring_areas.parquet"

SOURCE = "VIIRS_NOAA20_NRT"
AREA = "95,-11,141,6"
ROLLING_DAYS = 30


def check_boundaries() -> None:
    missing = [
        path
        for path in (ADM1, ADM2)
        if not path.exists()
    ]

    if missing:
        raise FileNotFoundError(
            "Administrative boundaries are missing. "
            "Run:\n\n"
            "uv run python scripts/download_boundaries.py"
        )


def update_rolling_dataset(
    existing: pl.DataFrame,
    new_data: pl.DataFrame,
    target_date: str,
) -> pl.DataFrame:
    existing = existing.with_columns(
        pl.col("acq_date").cast(pl.String)
    )

    new_data = new_data.with_columns(
        pl.col("acq_date").cast(pl.String)
    )

    existing = existing.filter(
        pl.col("acq_date") != target_date
    )

    new_data = new_data.filter(
        pl.col("acq_date") == target_date
    )

    rolling = pl.concat(
        [existing, new_data],
        how="vertical",
    )

    # Retain only the latest 30 acquisition dates.
    keep_dates = (
        rolling
        .select("acq_date")
        .unique()
        .sort("acq_date")
        .get_column("acq_date")
        .tail(ROLLING_DAYS)
        .to_list()
    )

    return (
        rolling
        .filter(
            pl.col("acq_date").is_in(keep_dates)
        )
        .sort("acquired_at_utc")
    )


def rebuild_analytics(
    firms: pl.DataFrame,
) -> None:
    ANALYTICS_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    firms.write_parquet(FIRMS_OUTPUT)

    province = aggregate_province(firms)
    kabkota = aggregate_kabkota(firms)

    province.write_parquet(PROVINCE_OUTPUT)
    kabkota.write_parquet(KABKOTA_OUTPUT)

    monitoring_firms = firms.with_columns(
        pl.col("acq_date")
        .str.to_date()
    )

    daily_clusters = build_daily_clusters(
        monitoring_firms
    )

    clusters = track_clusters(
        daily_clusters
    )

    clusters.write_parquet(
        CLUSTERS_OUTPUT
    )

    monitoring = build_monitoring_areas(
        monitoring_firms,
        clusters,
    )

    monitoring.write_parquet(
        MONITORING_OUTPUT
    )


def refresh(
    target_date: str,
) -> None:
    print(f"Refreshing {target_date}")

    check_boundaries()

    # Download

    raw = fetch_firms(
        source=SOURCE,
        area=AREA,
        date=target_date,
    )

    if raw.is_empty():
        print(
            "No FIRMS detections returned. "
            "Existing analytics were left unchanged."
        )
        return

    raw_path = save_raw(
        raw,
        SOURCE,
        target_date,
    )

    # Transform

    prov, kabkota = load_boundaries()

    processed = transform_firms(
        raw,
        prov,
        kabkota,
    )

    if processed.is_empty():
        print(
            "No Indonesian detections returned. "
            "Existing analytics were left unchanged."
        )
        return

    processed_path = save_processed(
        processed,
        SOURCE,
        target_date,
    )

    # Update rolling 30 days

    if not FIRMS_OUTPUT.exists():
        raise FileNotFoundError(
            f"{FIRMS_OUTPUT} does not exist. "
            "A baseline analytics dataset is required "
            "before incremental refresh."
        )

    existing = pl.read_parquet(
        FIRMS_OUTPUT
    )

    rolling = update_rolling_dataset(
        existing,
        processed,
        target_date,
    )

    # Rebuild analytics

    rebuild_analytics(rolling)

    dates = (
        rolling
        .select("acq_date")
        .unique()
        .sort("acq_date")
        .get_column("acq_date")
    )

    print()
    print("Refresh complete")
    print(f"Raw detections:       {raw.height:,}")
    print(f"Indonesia detections: {processed.height:,}")
    print(f"Rolling detections:   {rolling.height:,}")
    print(f"Coverage:             {dates.min()} → {dates.max()}")
    print(f"Unique dates:         {dates.len()}")
    print()
    print(f"Raw:        {raw_path}")
    print(f"Processed:  {processed_path}")
    print(f"Analytics:  {ANALYTICS_DIR}")


def main():
    parser = argparse.ArgumentParser(
        description="Refresh KarhutlaWatch analytics."
    )

    parser.add_argument(
        "--date",
        help=(
            "FIRMS acquisition date in YYYY-MM-DD format. "
            "Defaults to the current UTC date."
        ),
    )

    args = parser.parse_args()

    target_date = (
        args.date
        or datetime.now(timezone.utc)
        .date()
        .isoformat()
    )

    refresh(target_date)


if __name__ == "__main__":
    main()