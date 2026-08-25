from datetime import timedelta
from math import asin, cos, radians, sin, sqrt
from pathlib import Path

import numpy as np
import polars as pl
from sklearn.cluster import DBSCAN


ROOT = Path(__file__).resolve().parents[2]

INPUT = ROOT / "data" / "analytics" / "firms_30d.parquet"
HOTSPOT_OUTPUT = ROOT / "data" / "analytics" / "hotspot_clusters.parquet"
MONITORING_OUTPUT = ROOT / "data" / "analytics" / "monitoring_areas.parquet"

EARTH_RADIUS_KM = 6371.0088

# Mmonitoring parameters.
CLUSTER_DISTANCE_KM = 5.0
MATCH_DISTANCE_KM = 7.5
MIN_SAMPLES = 2
MAX_MISSING_DAYS = 1
MONITORING_WINDOW_DAYS = 7


def haversine_km(
    lat1: float,
    lon1: float,
    lat2: float,
    lon2: float,
) -> float:
    lat1 = radians(lat1)
    lon1 = radians(lon1)
    lat2 = radians(lat2)
    lon2 = radians(lon2)

    dlat = lat2 - lat1
    dlon = lon2 - lon1

    a = (
        sin(dlat / 2) ** 2
        + cos(lat1)
        * cos(lat2)
        * sin(dlon / 2) ** 2
    )

    return 2 * EARTH_RADIUS_KM * asin(sqrt(a))


def cluster_day(df: pl.DataFrame) -> pl.DataFrame:
    coordinates = df.select(
        "latitude",
        "longitude",
    ).to_numpy()

    coordinates_rad = np.radians(coordinates)

    labels = DBSCAN(
        eps=CLUSTER_DISTANCE_KM / EARTH_RADIUS_KM,
        min_samples=MIN_SAMPLES,
        metric="haversine",
        algorithm="ball_tree",
    ).fit_predict(coordinates_rad)

    return df.with_columns(
        pl.Series(
            "daily_cluster",
            labels.tolist(),
            dtype=pl.Int64,
        )
    )

def build_daily_clusters(
    firms: pl.DataFrame,
) -> pl.DataFrame:
    dates = (
        firms
        .get_column("acq_date")
        .unique()
        .sort()
        .to_list()
    )

    daily_summaries = []

    for current_date in dates:
        daily = firms.filter(
            pl.col("acq_date") == current_date
        )

        clustered = cluster_day(daily)
        clustered = clustered.filter(
            pl.col("daily_cluster") >= 0
        )

        summary = (
            clustered
            .group_by("daily_cluster")
            .agg(
                pl.len()
                .alias("detection_count"),

                (pl.col("confidence") == "h")
                .sum()
                .alias("high_confidence_count"),

                pl.col("frp")
                .sum()
                .alias("total_frp"),

                pl.col("frp")
                .max()
                .alias("max_frp"),

                pl.col("latitude")
                .mean()
                .alias("centroid_latitude"),

                pl.col("longitude")
                .mean()
                .alias("centroid_longitude"),

                pl.col("acquired_at_utc")
                .min()
                .alias("first_detection_at"),

                pl.col("acquired_at_utc")
                .max()
                .alias("last_detection_at"),

                pl.col("province")
                .mode()
                .first()
                .alias("province"),

                pl.col("kabupaten_kota")
                .mode()
                .first()
                .alias("kabupaten_kota"),
            )
            .with_columns(
                pl.lit(current_date)
                .alias("acq_date")
            )
        )

        daily_summaries.append(summary)

    return pl.concat(daily_summaries)


def track_clusters(
    clusters: pl.DataFrame,
) -> pl.DataFrame:
    clusters = clusters.sort(
        [
            "acq_date",
            "detection_count",
            "centroid_latitude",
            "centroid_longitude",
        ],
        descending=[
            False,
            True,
            False,
            False,
        ],
    )

    tracks = {}
    rows = []

    next_track_id = 1

    dates = (
        clusters
        .get_column("acq_date")
        .unique()
        .sort()
        .to_list()
    )

    for current_date in dates:
        daily = clusters.filter(
            pl.col("acq_date") == current_date
        )

        used_tracks = set()

        for row in daily.iter_rows(named=True):
            best_track = None
            best_distance = float("inf")

            for track_id, track in tracks.items():
                if track_id in used_tracks:
                    continue

                days_since_seen = (
                    current_date - track["last_date"]
                ).days

                if days_since_seen < 1:
                    continue

                if days_since_seen > MAX_MISSING_DAYS + 1:
                    continue

                distance = haversine_km(
                    row["centroid_latitude"],
                    row["centroid_longitude"],
                    track["latitude"],
                    track["longitude"],
                )

                if (
                    distance <= MATCH_DISTANCE_KM
                    and distance < best_distance
                ):
                    best_track = track_id
                    best_distance = distance

            if best_track is None:
                best_track = f"C{next_track_id:05d}"
                next_track_id += 1

            used_tracks.add(best_track)

            tracks[best_track] = {
                "latitude": row["centroid_latitude"],
                "longitude": row["centroid_longitude"],
                "last_date": current_date,
            }

            row["cluster_id"] = best_track
            rows.append(row)

    tracked = pl.DataFrame(rows)

    cluster_stats = (
        tracked
        .group_by("cluster_id")
        .agg(
            pl.col("acq_date")
            .min()
            .alias("first_seen"),

            pl.col("acq_date")
            .max()
            .alias("last_seen"),

            pl.col("acq_date")
            .n_unique()
            .alias("active_days"),

            pl.col("detection_count")
            .sum()
            .alias("track_detection_count"),

            pl.col("total_frp")
            .sum()
            .alias("track_total_frp"),
        )
    )

    return (
        tracked
        .join(
            cluster_stats,
            on="cluster_id",
            how="left",
        )
        .with_columns(
            (pl.col("active_days") >= 2)
            .alias("is_persistent")
        )
        .sort(
            [
                "acq_date",
                "detection_count",
            ],
            descending=[
                False,
                True,
            ],
        )
    )

def build_monitoring_areas(
    firms: pl.DataFrame,
    clusters: pl.DataFrame,
) -> pl.DataFrame:
    reference_date = (
        firms
        .select(pl.col("acq_date").max())
        .item()
    )

    reference_time = (
        firms
        .select(pl.col("acquired_at_utc").max())
        .item()
    )

    recent_start = (
        reference_date
        - timedelta(days=MONITORING_WINDOW_DAYS - 1)
    )

    previous_end = recent_start - timedelta(days=1)

    previous_start = (
        previous_end
        - timedelta(days=MONITORING_WINDOW_DAYS - 1)
    )

    # Recent 7-day activity

    recent = (
        firms
        .filter(
            pl.col("acq_date")
            .is_between(
                recent_start,
                reference_date,
            )
        )
        .group_by(
            "province",
            "kabupaten_kota",
        )
        .agg(
            pl.len()
            .alias("recent_detection_count"),

            (pl.col("confidence") == "h")
            .sum()
            .alias("recent_high_confidence_count"),

            pl.col("frp")
            .sum()
            .alias("recent_total_frp"),

            pl.col("frp")
            .max()
            .alias("recent_max_frp"),

            pl.col("acq_date")
            .n_unique()
            .alias("recent_active_days"),

            pl.col("acquired_at_utc")
            .max()
            .alias("last_detection_at"),
        )
    )

    # Previous 7-day activity

    previous = (
        firms
        .filter(
            pl.col("acq_date")
            .is_between(
                previous_start,
                previous_end,
            )
        )
        .group_by(
            "province",
            "kabupaten_kota",
        )
        .agg(
            pl.len()
            .alias("previous_detection_count"),

            pl.col("frp")
            .sum()
            .alias("previous_total_frp"),
        )
    )

    # Cluster persistence

    persistence = (
        clusters
        .filter(
            pl.col("acq_date")
            .is_between(
                recent_start,
                reference_date,
            )
        )
        .group_by(
            "province",
            "kabupaten_kota",
        )
        .agg(
            pl.col("cluster_id")
            .n_unique()
            .alias("recent_cluster_count"),

            pl.col("cluster_id")
            .filter(pl.col("is_persistent"))
            .n_unique()
            .alias("persistent_cluster_count"),

            pl.col("active_days")
            .max()
            .alias("max_cluster_active_days"),
        )
    )

    # Combine

    monitoring = (
        recent
        .join(
            previous,
            on=[
                "province",
                "kabupaten_kota",
            ],
            how="left",
        )
        .join(
            persistence,
            on=[
                "province",
                "kabupaten_kota",
            ],
            how="left",
        )
        .with_columns(
            pl.col("previous_detection_count")
            .fill_null(0),

            pl.col("previous_total_frp")
            .fill_null(0.0),

            pl.col("recent_cluster_count")
            .fill_null(0),

            pl.col("persistent_cluster_count")
            .fill_null(0),

            pl.col("max_cluster_active_days")
            .fill_null(0),
        )
        .with_columns(
            (
                pl.col("recent_detection_count")
                - pl.col("previous_detection_count")
            )
            .alias("detection_change"),

            (
                pl.col("recent_total_frp")
                - pl.col("previous_total_frp")
            )
            .alias("frp_change"),

            (
                pl.col("previous_detection_count")
                == 0
            )
            .alias("is_new_activity"),

            (
                pl.lit(reference_time)
                - pl.col("last_detection_at")
            )
            .dt.total_hours()
            .alias("hours_since_last_detection"),
        )
        .with_columns(
            pl.when(
                pl.col("previous_detection_count") > 0
            )
            .then(
                (
                    pl.col("detection_change")
                    / pl.col("previous_detection_count")
                )
                * 100
            )
            .otherwise(None)
            .alias("detection_change_pct"),

            pl.when(
                pl.col("previous_total_frp") > 0
            )
            .then(
                (
                    pl.col("frp_change")
                    / pl.col("previous_total_frp")
                )
                * 100
            )
            .otherwise(None)
            .alias("frp_change_pct"),
        )
    )

    # Monitoring priority

    monitoring = (
        monitoring
        .with_columns(
            (
                pl.col("recent_detection_count")
                .rank("average")
                / pl.len()
            )
            .alias("_activity_score"),

            (
                pl.col("recent_total_frp")
                .rank("average")
                / pl.len()
            )
            .alias("_frp_score"),

            (
                pl.col("max_cluster_active_days")
                .rank("average")
                / pl.len()
            )
            .alias("_persistence_score"),

            (
                pl.col("detection_change")
                .clip(lower_bound=0)
                .rank("average")
                / pl.len()
            )
            .alias("_growth_score"),
        )
        .with_columns(
            (
                0.35 * pl.col("_activity_score")
                + 0.25 * pl.col("_frp_score")
                + 0.25 * pl.col("_persistence_score")
                + 0.15 * pl.col("_growth_score")
            )
            .mul(100)
            .round(1)
            .alias("monitoring_priority")
        )
        .drop(
            "_activity_score",
            "_frp_score",
            "_persistence_score",
            "_growth_score",
        )
        .with_columns(
            pl.lit(recent_start)
            .alias("monitoring_start_date"),

            pl.lit(reference_date)
            .alias("monitoring_end_date"),
        )
        .sort(
            "monitoring_priority",
            descending=True,
        )
    )

    return monitoring


def main():
    firms = (
        pl.read_parquet(INPUT)
        .with_columns(
            pl.col("acq_date")
            .str.to_date()
        )
    )

    daily_clusters = build_daily_clusters(firms)

    hotspot_clusters = track_clusters(
        daily_clusters
    )

    hotspot_clusters.write_parquet(
        HOTSPOT_OUTPUT
    )

    monitoring_areas = build_monitoring_areas(
        firms,
        hotspot_clusters,
    )

    monitoring_areas.write_parquet(
        MONITORING_OUTPUT
    )

    persistent = (
        hotspot_clusters
        .filter(pl.col("is_persistent"))
        .get_column("cluster_id")
        .n_unique()
    )

    print(
        f"Daily cluster rows: "
        f"{hotspot_clusters.height:,}"
    )

    print(
        f"Tracked clusters: "
        f"{hotspot_clusters.get_column('cluster_id').n_unique():,}"
    )

    print(
        f"Persistent clusters: "
        f"{persistent:,}"
    )

    print(
        f"Monitoring areas: "
        f"{monitoring_areas.height:,}"
    )

    print(f"Saved clusters to: {HOTSPOT_OUTPUT}")
    print(f"Saved monitoring areas to: {MONITORING_OUTPUT}")


if __name__ == "__main__":
    main()