from karhutlawatch.firms import fetch_firms, save_raw
from karhutlawatch.transform import (
    load_boundaries,
    save_processed,
    transform_firms,
)


def run_pipeline(
    source: str,
    date: str,
) -> None:
    raw = fetch_firms(
        source=source,
        area="95,-11,141,6",
        date=date,
    )

    raw_path = save_raw(
        raw,
        source,
        date,
    )

    prov, kabkota = load_boundaries()

    processed = transform_firms(
        raw,
        prov,
        kabkota,
    )

    processed_path = save_processed(
        processed,
        source,
        date,
    )

    print(f"Raw detections:       {raw.height:,}")
    print(f"Indonesia detections: {processed.height:,}")
    print(f"Raw file:             {raw_path}")
    print(f"Processed file:       {processed_path}")


if __name__ == "__main__":
    run_pipeline(
        source="VIIRS_NOAA20_NRT",
        date="2026-08-24",
    )