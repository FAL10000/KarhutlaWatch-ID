import math
from datetime import date, datetime, timezone
from pathlib import Path

import altair as alt
import polars as pl
import pydeck as pdk
import streamlit as st


ROOT = Path(__file__).resolve().parents[2]
ANALYTICS = ROOT / "data" / "analytics"

FIRMS_PATH = ANALYTICS / "firms_30d.parquet"
PROVINCE_PATH = ANALYTICS / "daily_province.parquet"
KABKOTA_PATH = ANALYTICS / "daily_kabupaten_kota.parquet"
CLUSTERS_PATH = ANALYTICS / "hotspot_clusters.parquet"
MONITORING_PATH = ANALYTICS / "monitoring_areas.parquet"

ALL_INDONESIA = "All Indonesia"
ALL_CONFIDENCE = "All confidence levels"
CONFIDENCE_CODES = {
    ALL_CONFIDENCE: None,
    "High": "h",
    "Nominal": "n",
    "Low": "l",
}
PRESET_DAYS = {"7D": 7, "14D": 14, "30D": 30}
CUSTOM_PERIOD = "Custom"
SINGLE_DATE = "Single date"
DATE_RANGE = "Date range"
HOTSPOTS_MODE = "Hotspots"
DENSITY_MODE = "Density"
COMBINED_MODE = "Combined"
PERSISTENT_CLUSTERS_MODE = "Persistent clusters"
MAP_MODES = [
    HOTSPOTS_MODE,
    DENSITY_MODE,
    COMBINED_MODE,
    PERSISTENT_CLUSTERS_MODE,
]
PERSISTENCE_MINIMUMS = {
    "2+ days": 2,
    "3+ days": 3,
    "7+ days": 7,
}
HOTSPOT_COLOR = [255, 139, 64, 170]
CLUSTER_OUTLINE_COLOR = [158, 229, 239, 225]
HEATMAP_COLORS = [
    [69, 27, 22],
    [112, 35, 24],
    [165, 48, 24],
    [213, 72, 30],
    [240, 125, 45],
    [255, 205, 105],
]


st.set_page_config(
    page_title="KarhutlaWatch Indonesia",
    page_icon=":material/satellite_alt:",
    layout="wide",
    initial_sidebar_state="expanded",
    menu_items={
        "About": (
            "KarhutlaWatch Indonesia monitors satellite-detected thermal "
            "anomalies from NASA FIRMS VIIRS NOAA-20 NRT. Hotspots are not "
            "confirmed fire incidents."
        )
    },
)


@st.cache_data(show_spinner=False)
def load_data() -> tuple[
    pl.DataFrame,
    pl.DataFrame,
    pl.DataFrame,
    pl.DataFrame,
    pl.DataFrame,
]:
    """Load the committed analytics datasets used by the dashboard."""
    firms = pl.read_parquet(FIRMS_PATH)
    province = pl.read_parquet(PROVINCE_PATH)
    kabkota = pl.read_parquet(KABKOTA_PATH)
    clusters = pl.read_parquet(CLUSTERS_PATH)
    monitoring = pl.read_parquet(MONITORING_PATH)
    return firms, province, kabkota, clusters, monitoring


def format_date(value: str) -> str:
    """Format an ISO date for public-facing labels."""
    return date.fromisoformat(value).strftime("%d %b %Y").lstrip("0")


def format_timestamp(value: datetime) -> str:
    """Format a UTC acquisition timestamp for compact metadata."""
    return value.strftime("%d %b %Y, %H:%M UTC").lstrip("0")


def format_change_label(
    recent_count: int,
    previous_count: int,
    change_pct: float | None,
) -> str:
    """Format a neutral comparison without inventing an infinite change."""
    if previous_count == 0:
        return "New activity"
    if change_pct is None or not math.isfinite(change_pct):
        return "Change unavailable"

    count_change = recent_count - previous_count
    if count_change < 0 and change_pct >= 0:
        return "Decreasing vs previous 7D"
    if count_change > 0 and change_pct < 0:
        return "Increasing vs previous 7D"
    return f"{change_pct:+.0f}% vs previous 7D"


def format_snapshot_recency(hours: int) -> str:
    """Describe recency relative to the analytics snapshot, not wall time."""
    if hours <= 0:
        return "<1h before snapshot"
    if hours < 24:
        return f"{hours}h before snapshot"
    return f"{hours // 24}d before snapshot"


def is_partial_latest_date(latest_date: str, current_utc_date: date) -> bool:
    """Return whether the latest acquisition date is still in progress."""
    return date.fromisoformat(latest_date) == current_utc_date


def format_period(start_date: str, end_date: str) -> str:
    """Format an inclusive date period without repeating shared parts."""
    start = date.fromisoformat(start_date)
    end = date.fromisoformat(end_date)
    if start == end:
        return format_date(start_date)
    if start.year == end.year and start.month == end.month:
        return f"{start.day}–{end.day} {end:%b %Y}"
    if start.year == end.year:
        return f"{start.day} {start:%b}–{end.day} {end:%b %Y}"
    return f"{format_date(start_date)}–{format_date(end_date)}"


def confidence_detection_label(selected_confidence: str) -> str:
    """Describe the active confidence scope in chart and table captions."""
    if selected_confidence == ALL_CONFIDENCE:
        return "satellite detections"
    return f"{selected_confidence.lower()}-confidence detections"


def filter_hotspots(
    firms: pl.DataFrame,
    start_date: str,
    end_date: str,
    selected_province: str,
    confidence_code: str | None,
) -> pl.DataFrame:
    """Return hotspot-level rows for the selected period and geography."""
    filtered = firms.filter(
        pl.col("acq_date").is_between(
            pl.lit(start_date), pl.lit(end_date), closed="both"
        )
    )
    if selected_province != ALL_INDONESIA:
        filtered = filtered.filter(pl.col("province") == selected_province)
    if confidence_code is not None:
        filtered = filtered.filter(pl.col("confidence") == confidence_code)
    return filtered


def calculate_kpis(filtered: pl.DataFrame) -> tuple[int, int, float, int]:
    """Calculate the four headline indicators for the active scope."""
    summary = filtered.select(
        pl.len().alias("hotspot_count"),
        (pl.col("confidence") == "h").sum().alias("high_confidence_count"),
        pl.col("frp").sum().fill_null(0.0).alias("total_frp"),
        pl.col("kabupaten_kota")
        .drop_nulls()
        .n_unique()
        .alias("affected_kabkota"),
    ).row(0, named=True)

    return (
        int(summary["hotspot_count"]),
        int(summary["high_confidence_count"]),
        float(summary["total_frp"]),
        int(summary["affected_kabkota"]),
    )


def build_trend(
    province_daily: pl.DataFrame,
    firms: pl.DataFrame,
    selected_dates: list[str],
    selected_province: str,
    confidence_code: str | None,
) -> pl.DataFrame:
    """Build a complete daily trend for Indonesia or one province."""
    if confidence_code is None and selected_province == ALL_INDONESIA:
        scoped = province_daily.group_by("acq_date").agg(
            pl.col("hotspot_count").sum().alias("hotspot_count")
        )
    elif confidence_code is None:
        scoped = province_daily.filter(
            pl.col("province") == selected_province
        ).select("acq_date", "hotspot_count")
    else:
        scoped_hotspots = firms.filter(pl.col("confidence") == confidence_code)
        if selected_province != ALL_INDONESIA:
            scoped_hotspots = scoped_hotspots.filter(
                pl.col("province") == selected_province
            )
        scoped = scoped_hotspots.group_by("acq_date").agg(
            pl.len().alias("hotspot_count")
        )

    return (
        pl.DataFrame({"acq_date": selected_dates})
        .join(scoped, on="acq_date", how="left")
        .with_columns(
            pl.col("acq_date").str.to_date("%Y-%m-%d").alias("date"),
            pl.col("hotspot_count").fill_null(0).cast(pl.Int64),
        )
        .select("date", "hotspot_count")
        .sort("date")
    )


def build_ranking(
    kabkota_daily: pl.DataFrame,
    firms: pl.DataFrame,
    start_date: str,
    end_date: str,
    selected_province: str,
    confidence_code: str | None,
) -> pl.DataFrame:
    """Return the top ten named kabupaten/kota for the active scope."""
    if confidence_code is None:
        ranking = (
            kabkota_daily.filter(
                pl.col("acq_date").is_between(
                    pl.lit(start_date), pl.lit(end_date), closed="both"
                )
                & pl.col("kabupaten_kota").is_not_null()
            )
            .group_by("province", "kabupaten_kota")
            .agg(
                pl.col("hotspot_count").sum(),
                pl.col("high_confidence_count").sum(),
                pl.col("total_frp").sum(),
                pl.col("max_frp").max(),
            )
        )
        if selected_province != ALL_INDONESIA:
            ranking = ranking.filter(pl.col("province") == selected_province)
    else:
        scoped_hotspots = firms.filter(
            pl.col("acq_date").is_between(
                pl.lit(start_date), pl.lit(end_date), closed="both"
            )
            & (pl.col("confidence") == confidence_code)
            & pl.col("kabupaten_kota").is_not_null()
        )
        if selected_province != ALL_INDONESIA:
            scoped_hotspots = scoped_hotspots.filter(
                pl.col("province") == selected_province
            )
        ranking = scoped_hotspots.group_by(
            "province", "kabupaten_kota"
        ).agg(
            pl.len().alias("hotspot_count"),
            (pl.col("confidence") == "h")
            .sum()
            .alias("high_confidence_count"),
            pl.col("frp").sum().alias("total_frp"),
            pl.col("frp").max().alias("max_frp"),
        )

    return (
        ranking.sort(
            ["hotspot_count", "high_confidence_count", "total_frp"],
            descending=True,
        )
        .head(10)
        .with_row_index("rank", offset=1)
        .select(
            "rank",
            "kabupaten_kota",
            "province",
            "hotspot_count",
            "high_confidence_count",
            "total_frp",
            "max_frp",
        )
    )


def build_monitoring_ranking(
    monitoring: pl.DataFrame,
    selected_province: str,
) -> pl.DataFrame:
    """Return the latest precomputed monitoring ranking for one scope."""
    scoped = monitoring.filter(pl.col("kabupaten_kota").is_not_null())
    if selected_province != ALL_INDONESIA:
        scoped = scoped.filter(pl.col("province") == selected_province)

    ranking = (
        scoped.sort(
            ["monitoring_priority", "recent_detection_count"],
            descending=True,
        )
        .head(10)
        .with_row_index("rank", offset=1)
    )
    rows = list(ranking.iter_rows(named=True))
    if not rows:
        return ranking

    return ranking.with_columns(
        pl.Series(
            "change_vs_previous",
            [
                format_change_label(
                    int(row["recent_detection_count"]),
                    int(row["previous_detection_count"]),
                    row["detection_change_pct"],
                )
                for row in rows
            ],
        ),
        pl.Series(
            "snapshot_recency",
            [
                format_snapshot_recency(
                    int(row["hours_since_last_detection"])
                )
                for row in rows
            ],
        ),
    ).select(
        "rank",
        "kabupaten_kota",
        "province",
        "monitoring_priority",
        "recent_detection_count",
        "change_vs_previous",
        "persistent_cluster_count",
        "recent_active_days",
        "recent_total_frp",
        "snapshot_recency",
    )


def filter_persistent_clusters(
    clusters: pl.DataFrame,
    start_date: str,
    end_date: str,
    selected_province: str,
) -> pl.DataFrame:
    """Build one point-in-time row per persistent track in the period."""
    period_rows = clusters.filter(
        pl.col("acq_date").is_between(
            date.fromisoformat(start_date),
            date.fromisoformat(end_date),
            closed="both",
        )
    )
    if selected_province != ALL_INDONESIA:
        period_rows = period_rows.filter(
            pl.col("province") == selected_province
        )

    representatives = (
        period_rows.sort(["acq_date", "last_detection_at"])
        .unique(subset="cluster_id", keep="last", maintain_order=True)
        .select(
            "cluster_id",
            "acq_date",
            "province",
            "kabupaten_kota",
            "detection_count",
            "centroid_latitude",
            "centroid_longitude",
            "last_detection_at",
            "is_persistent",
        )
    )

    cutoffs = representatives.select(
        "cluster_id",
        pl.col("acq_date").alias("representative_date"),
    )
    # Full-track summary fields are repeated on every daily row. Rebuild their
    # point-in-time equivalents from daily values to avoid historical leakage.
    history_to_representative = clusters.join(
        cutoffs,
        on="cluster_id",
        how="inner",
    ).filter(pl.col("acq_date") <= pl.col("representative_date"))
    point_in_time_stats = history_to_representative.group_by(
        "cluster_id"
    ).agg(
        pl.col("acq_date").min().alias("first_seen"),
        pl.col("acq_date").max().alias("last_seen"),
        pl.col("acq_date").n_unique().alias("active_days"),
        pl.col("detection_count").sum().alias("track_detection_count"),
        pl.col("total_frp").sum().alias("track_total_frp"),
    )

    return (
        representatives.join(
            point_in_time_stats,
            on="cluster_id",
            how="left",
        )
        .filter(pl.col("is_persistent") & (pl.col("active_days") >= 2))
        .sort(
            ["active_days", "track_detection_count"],
            descending=True,
        )
    )


def build_hotspot_records(
    filtered: pl.DataFrame,
) -> list[dict[str, object]]:
    """Prepare compact point and tooltip records for PyDeck."""
    confidence_label = (
        pl.when(pl.col("confidence") == "h")
        .then(pl.lit("High"))
        .when(pl.col("confidence") == "n")
        .then(pl.lit("Nominal"))
        .otherwise(pl.lit("Low"))
    )

    return (
        filtered.select(
            pl.col("longitude").alias("x"),
            pl.col("latitude").alias("y"),
            pl.col("kabupaten_kota")
            .fill_null("Unassigned area")
            .alias("k"),
            pl.col("province").alias("p"),
            pl.col("acquired_at_utc")
            .dt.strftime("%d %b %Y, %H:%M UTC")
            .str.replace(r"^0", "")
            .alias("a"),
            confidence_label.alias("c"),
            pl.col("frp").round(1).alias("f"),
        )
        .to_dicts()
    )


def build_density_records(filtered: pl.DataFrame) -> list[dict[str, float]]:
    """Prepare coordinate-only records for GPU density aggregation."""
    return (
        filtered.select(
            pl.col("longitude").alias("x"),
            pl.col("latitude").alias("y"),
        )
        .to_dicts()
    )


def build_cluster_records(
    persistent_clusters: pl.DataFrame,
    end_date: str,
) -> list[dict[str, object]]:
    """Prepare one compact tooltip record per persistent cluster track."""
    days_from_period_end = (
        pl.lit(date.fromisoformat(end_date)) - pl.col("last_seen")
    ).dt.total_days()

    return (
        persistent_clusters.select(
            pl.col("centroid_longitude").alias("x"),
            pl.col("centroid_latitude").alias("y"),
            pl.col("kabupaten_kota")
            .fill_null("Unassigned area")
            .alias("k"),
            pl.col("province").alias("p"),
            pl.col("active_days").alias("d"),
            pl.col("detection_count").alias("n"),
            pl.col("track_detection_count").alias("t"),
            pl.col("track_total_frp").round(1).alias("f"),
            pl.col("first_seen")
            .dt.strftime("%d %b %Y")
            .str.replace(r"^0", "")
            .alias("fs"),
            pl.col("last_seen")
            .dt.strftime("%d %b %Y")
            .str.replace(r"^0", "")
            .alias("ls"),
            pl.when(pl.col("active_days") >= 7)
            .then(pl.lit(11))
            .when(pl.col("active_days") >= 4)
            .then(pl.lit(8))
            .otherwise(pl.lit(5))
            .alias("r"),
            pl.when(days_from_period_end <= 1)
            .then(pl.lit(205))
            .when(days_from_period_end <= 3)
            .then(pl.lit(145))
            .otherwise(pl.lit(85))
            .alias("o"),
        )
        .to_dicts()
    )


def map_view(
    filtered: pl.DataFrame,
    selected_province: str,
    latitude_column: str = "latitude",
    longitude_column: str = "longitude",
) -> pdk.ViewState:
    """Choose a useful national or province-level starting viewport."""
    if selected_province == ALL_INDONESIA or filtered.is_empty():
        return pdk.ViewState(
            latitude=-2.5,
            longitude=118.0,
            zoom=3.4,
            min_zoom=2.5,
            max_zoom=12,
            pitch=0,
            bearing=0,
        )

    bounds = filtered.select(
        pl.col(latitude_column).min().alias("min_latitude"),
        pl.col(latitude_column).max().alias("max_latitude"),
        pl.col(longitude_column).min().alias("min_longitude"),
        pl.col(longitude_column).max().alias("max_longitude"),
    ).row(0, named=True)

    latitude = (
        float(bounds["min_latitude"]) + float(bounds["max_latitude"])
    ) / 2
    longitude = (
        float(bounds["min_longitude"]) + float(bounds["max_longitude"])
    ) / 2
    latitude_span = float(bounds["max_latitude"]) - float(
        bounds["min_latitude"]
    )
    longitude_span = float(bounds["max_longitude"]) - float(
        bounds["min_longitude"]
    )
    effective_span = max(longitude_span, latitude_span * 1.7, 0.15)
    zoom = max(
        4.0,
        min(8.5, math.log2(360.0 / effective_span) - 0.35),
    )

    return pdk.ViewState(
        latitude=latitude,
        longitude=longitude,
        zoom=zoom,
        min_zoom=2.5,
        max_zoom=12,
        pitch=0,
        bearing=0,
    )


def build_hotspot_layer(records: list[dict[str, object]]) -> pdk.Layer:
    """Build a small, individually inspectable FIRMS point layer."""
    return pdk.Layer(
        "ScatterplotLayer",
        id="hotspot-points",
        data=records,
        get_position="[x, y]",
        get_fill_color=HOTSPOT_COLOR,
        get_radius=2,
        radius_units="'pixels'",
        radius_min_pixels=1,
        radius_max_pixels=4,
        stroked=False,
        pickable=True,
        auto_highlight=True,
        highlight_color=[255, 235, 185, 230],
    )


def build_heatmap_layer(records: list[dict[str, float]]) -> pdk.Layer:
    """Build a transparent count-density layer below individual points."""
    return pdk.Layer(
        "HeatmapLayer",
        id="hotspot-density",
        data=records,
        get_position="[x, y]",
        get_weight=1,
        aggregation="'SUM'",
        radius_pixels=32,
        intensity=1,
        threshold=0.04,
        color_range=HEATMAP_COLORS,
        opacity=0.55,
        weights_texture_size=512,
        pickable=False,
    )


def build_cluster_layer(records: list[dict[str, object]]) -> pdk.Layer:
    """Build centroid markers for persistent tracked thermal activity."""
    return pdk.Layer(
        "ScatterplotLayer",
        id="persistent-clusters",
        data=records,
        get_position="[x, y]",
        get_fill_color="[45, 190, 210, o]",
        get_line_color=CLUSTER_OUTLINE_COLOR,
        get_radius="r",
        radius_units="'pixels'",
        radius_min_pixels=5,
        radius_max_pixels=11,
        line_width_units="'pixels'",
        line_width_min_pixels=1,
        stroked=True,
        pickable=True,
        auto_highlight=True,
        highlight_color=[221, 249, 252, 220],
    )


def render_header(
    start_date: str,
    end_date: str,
    selected_province: str,
    selected_confidence: str,
    latest_date: str,
    latest_date_may_be_partial: bool,
) -> None:
    """Render the dashboard identity and active scope."""
    title_column, date_column = st.columns(
        [3, 1], gap="large", vertical_alignment="center"
    )

    with title_column:
        st.title("KarhutlaWatch Indonesia")
        st.markdown(
            "Monitor recent satellite-detected thermal activity across "
            "Indonesia using NASA FIRMS VIIRS NOAA-20 near-real-time data."
        )
        st.caption(
            "A hotspot is a satellite thermal detection, not a confirmed "
            "forest or land-fire incident."
        )

    with date_column:
        with st.container(border=True):
            st.caption("Active period")
            st.subheader(format_period(start_date, end_date))
            st.markdown(f"**{selected_province}**")
            st.caption(f"Confidence: {selected_confidence}")
            if start_date <= latest_date <= end_date:
                st.badge(
                    "Latest available data",
                    icon=":material/update:",
                    color="blue",
                )
                if latest_date_may_be_partial:
                    st.caption("Current UTC day · may be incomplete")


def render_metrics(filtered: pl.DataFrame) -> None:
    """Render the headline indicators as responsive native cards."""
    hotspot_count, high_confidence_count, total_frp, affected_kabkota = (
        calculate_kpis(filtered)
    )

    with st.container(horizontal=True):
        st.metric(
            "Satellite detections",
            hotspot_count,
            format="%,d",
            icon=":material/sensors:",
            border=True,
            help="Number of NASA FIRMS hotspot rows in the selected scope.",
        )
        st.metric(
            "High-confidence detections",
            high_confidence_count,
            format="%,d",
            icon=":material/verified:",
            border=True,
            help='Detections where the FIRMS confidence code is "h".',
        )
        st.metric(
            "Total FRP",
            f"{total_frp:,.0f} MW",
            icon=":material/bolt:",
            border=True,
            help=(
                "Sum of Fire Radiative Power reported for detections in "
                "the selected scope."
            ),
        )
        st.metric(
            "Affected kabupaten/kota",
            affected_kabkota,
            format="%,d",
            icon=":material/map:",
            border=True,
            help="Distinct named kabupaten/kota with at least one detection.",
        )


def render_map(
    filtered: pl.DataFrame,
    clusters: pl.DataFrame,
    start_date: str,
    end_date: str,
    selected_province: str,
    selected_confidence: str,
) -> None:
    """Render hotspot, density, or persistent-cluster views on a dark map."""
    with st.container(border=True):
        heading_column, mode_column = st.columns(
            [2, 1], gap="large", vertical_alignment="bottom"
        )
        with heading_column:
            st.subheader("Hotspot activity map")
        with mode_column:
            map_mode = st.segmented_control(
                "Map display",
                MAP_MODES,
                default=COMBINED_MODE,
                required=True,
                width="stretch",
                key="map_display",
            )

        if map_mode == PERSISTENT_CLUSTERS_MODE:
            persistence_label = st.segmented_control(
                "Minimum persistence",
                list(PERSISTENCE_MINIMUMS),
                default="3+ days",
                required=True,
                width="content",
                key="minimum_persistence",
                help=(
                    "Minimum distinct active days observed for a precomputed "
                    "tracked cluster, as known by the selected period end."
                ),
            )
            minimum_persistence = PERSISTENCE_MINIMUMS[persistence_label]
            persistent_clusters = filter_persistent_clusters(
                clusters,
                start_date,
                end_date,
                selected_province,
            ).filter(pl.col("active_days") >= minimum_persistence)
            st.caption(
                f"{persistent_clusters.height:,} persistent thermal-activity "
                f"clusters observed during {format_period(start_date, end_date)} "
                f"· {selected_province}. Each marker is one tracked cluster "
                f"observed on at least {minimum_persistence} days. Precomputed "
                "from all confidence levels."
            )
            map_data = persistent_clusters
            empty_message = (
                "No tracked clusters meet this persistence threshold in the "
                "selected period and province."
            )
        else:
            st.caption(
                f"{filtered.height:,} individual detections during "
                f"{format_period(start_date, end_date)} · "
                f"{selected_province}. Confidence: {selected_confidence}."
            )
            map_data = filtered
            empty_message = (
                "No hotspot detections match the selected period, province, "
                "and confidence level."
            )

        if map_data.is_empty():
            st.info(
                empty_message,
                icon=":material/info:",
            )
            return

        layers: list[pdk.Layer] = []
        if map_mode == PERSISTENT_CLUSTERS_MODE:
            layers.append(
                build_cluster_layer(
                    build_cluster_records(persistent_clusters, end_date)
                )
            )
        elif map_mode in (DENSITY_MODE, COMBINED_MODE):
            layers.append(build_heatmap_layer(build_density_records(filtered)))
        if map_mode in (HOTSPOTS_MODE, COMBINED_MODE):
            layers.append(build_hotspot_layer(build_hotspot_records(filtered)))

        tooltip = None
        if map_mode == PERSISTENT_CLUSTERS_MODE:
            tooltip = {
                "html": (
                    "<b>{k}</b><br/>"
                    "{p}<br/>"
                    "Active days: {d}<br/>"
                    "First observed: {fs}<br/>"
                    "Last observed: {ls}<br/>"
                    "Tracked detections: {t}<br/>"
                    "Total FRP: {f} MW<br/>"
                    "Latest active day: {n} detections"
                ),
                "style": {
                    "backgroundColor": "rgba(18, 22, 27, 0.94)",
                    "color": "#F4F6F8",
                    "fontSize": "13px",
                },
            }
        elif map_mode in (HOTSPOTS_MODE, COMBINED_MODE):
            tooltip = {
                "html": (
                    "<b>{k}</b><br/>"
                    "{p}<br/>"
                    "Acquired: {a}<br/>"
                    "Confidence: {c}<br/>"
                    "FRP: {f} MW"
                ),
                "style": {
                    "backgroundColor": "rgba(18, 22, 27, 0.94)",
                    "color": "#F4F6F8",
                    "fontSize": "13px",
                },
            }

        if map_mode == PERSISTENT_CLUSTERS_MODE:
            initial_view_state = map_view(
                persistent_clusters,
                selected_province,
                latitude_column="centroid_latitude",
                longitude_column="centroid_longitude",
            )
        else:
            initial_view_state = map_view(filtered, selected_province)

        deck = pdk.Deck(
            map_style=pdk.map_styles.CARTO_DARK,
            map_provider="carto",
            initial_view_state=initial_view_state,
            layers=layers,
            tooltip=tooltip,
        )
        st.pydeck_chart(deck, height=620, width="stretch")
        if map_mode == PERSISTENT_CLUSTERS_MODE:
            st.caption(
                "Markers show the latest centroid of each tracked cluster "
                "within the selected period. Size reflects active days; brighter "
                "markers were observed closer to the period end. Marker size "
                "does not represent burned area, and clusters are not confirmed "
                "fire incidents."
            )
        else:
            st.caption(
                "Points are individual NASA FIRMS thermal detections. Density "
                "shows the concentration of detections, not confirmed burned "
                "area."
            )


def render_monitoring_priority(
    ranking: pl.DataFrame,
    monitoring_start_date: str,
    monitoring_end_date: str,
    selected_province: str,
) -> None:
    """Render the latest fixed-window monitoring ranking as a compact table."""
    with st.container(border=True):
        st.subheader("Areas requiring attention")
        st.markdown(
            f"**Monitoring priority · "
            f"{format_period(monitoring_start_date, monitoring_end_date)}**"
        )
        st.caption(
            "Latest precomputed 7-day snapshot compared with the previous 7 "
        )
        st.caption(
            "Monitoring priority is a relative indicator based on recent activity, FRP, persistence, and growth."
        )

        if ranking.is_empty():
            st.info(
                f"No monitoring areas are available for {selected_province} "
                "in this snapshot.",
                icon=":material/info:",
            )
            return

        st.dataframe(
            ranking,
            width="stretch",
            hide_index=True,
            column_config={
                "rank": st.column_config.NumberColumn(
                    "Rank", format="%d", width="small"
                ),
                "kabupaten_kota": st.column_config.TextColumn(
                    "Kabupaten/kota", width="large", pinned=True
                ),
                "province": st.column_config.TextColumn(
                    "Province", width="medium"
                ),
                "monitoring_priority": st.column_config.NumberColumn(
                    "Priority", format="%.1f", help="Relative score from 0–100."
                ),
                "recent_detection_count": st.column_config.NumberColumn(
                    "Recent detections", format="%,d"
                ),
                "change_vs_previous": st.column_config.TextColumn(
                    "Change vs previous 7D", width="large"
                ),
                "persistent_cluster_count": st.column_config.NumberColumn(
                    "Persistent clusters", format="%,d"
                ),
                "recent_active_days": st.column_config.NumberColumn(
                    "Active days (of 7)", format="%d"
                ),
                "recent_total_frp": st.column_config.NumberColumn(
                    "Recent total FRP", format="%,.1f MW"
                ),
                "snapshot_recency": st.column_config.TextColumn(
                    "Last activity", width="medium"
                ),
            },
        )


def render_trend(
    trend: pl.DataFrame,
    start_date: str,
    end_date: str,
    selected_province: str,
    selected_confidence: str,
    latest_date: str,
    latest_date_may_be_partial: bool,
) -> None:
    """Render the daily trend and distinguish a partial current UTC day."""
    latest_day = date.fromisoformat(latest_date)
    latest_point = trend.filter(pl.col("date") == latest_day)

    base = alt.Chart(trend).encode(
        x=alt.X(
            "date:T",
            title=None,
            axis=alt.Axis(format="%d %b", labelAngle=0, tickCount=8),
        ),
        y=alt.Y(
            "hotspot_count:Q",
            title="Satellite detections",
            scale=alt.Scale(zero=True),
        ),
        tooltip=[
            alt.Tooltip("date:T", title="Date", format="%d %b %Y"),
            alt.Tooltip(
                "hotspot_count:Q", title="Satellite detections", format=","
            ),
        ],
    )
    line = base.mark_line(point=True, strokeWidth=2)
    latest_rule = (
        alt.Chart(latest_point)
        .mark_rule(color="#E65C2A", strokeDash=[4, 4], opacity=0.65)
        .encode(x="date:T")
    )
    latest_marker = (
        alt.Chart(latest_point)
        .mark_point(color="#E65C2A", filled=True, size=120)
        .encode(
            x="date:T",
            y="hotspot_count:Q",
            tooltip=[
                alt.Tooltip(
                    "date:T", title="Partial UTC day", format="%d %b %Y"
                ),
                alt.Tooltip(
                    "hotspot_count:Q", title="Satellite detections", format=","
                ),
            ],
        )
    )

    with st.container(border=True):
        st.subheader("Daily hotspot trend")
        trend_caption = (
            f"Daily {confidence_detection_label(selected_confidence)} for "
            f"{selected_province} during {format_period(start_date, end_date)}."
        )
        chart = line
        if latest_date_may_be_partial and not latest_point.is_empty():
            trend_caption += (
                f" The current UTC day ({format_date(latest_date)}) is "
                "highlighted and may still receive detections."
            )
            chart = line + latest_rule + latest_marker
        st.caption(trend_caption)
        st.altair_chart(
            chart.properties(height=300),
            width="stretch",
        )


def render_ranking(
    ranking: pl.DataFrame,
    selected_province: str,
    selected_confidence: str,
) -> None:
    """Render the top-area ranking with friendly labels and formats."""
    with st.container(border=True):
        st.subheader("Top kabupaten/kota")
        scope_note = (
            "Province is shown to preserve geographic context."
            if selected_province == ALL_INDONESIA
            else f"Ranking within {selected_province}."
        )
        st.caption(
            f"Top 10 areas by {confidence_detection_label(selected_confidence)} "
            "during the selected period. "
            + scope_note
        )

        if ranking.is_empty():
            st.info(
                "No named kabupaten/kota are available for this selection.",
                icon=":material/info:",
            )
            return

        st.dataframe(
            ranking,
            width="stretch",
            hide_index=True,
            column_config={
                "rank": st.column_config.NumberColumn(
                    "Rank", format="%d", width="small"
                ),
                "kabupaten_kota": st.column_config.TextColumn(
                    "Kabupaten/kota", width="large", pinned=True
                ),
                "province": st.column_config.TextColumn(
                    "Province", width="medium"
                ),
                "hotspot_count": st.column_config.NumberColumn(
                    "Detections", format="%,d"
                ),
                "high_confidence_count": st.column_config.NumberColumn(
                    "High confidence", format="%,d"
                ),
                "total_frp": st.column_config.NumberColumn(
                    "Total FRP", format="%,.1f MW"
                ),
                "max_frp": st.column_config.NumberColumn(
                    "Maximum FRP", format="%,.1f MW"
                ),
            },
        )


def render_methodology(latest_acquisition: datetime) -> None:
    """Keep data-source and interpretation guidance available but secondary."""
    with st.expander(
        "Data source and methodology",
        icon=":material/info:",
    ):
        st.markdown(
            """
- **Source:** NASA FIRMS, using VIIRS NOAA-20 near-real-time (NRT) active-fire and thermal-anomaly detections.
- **FRP:** Fire Radiative Power, reported in megawatts (MW), estimates the instantaneous radiant energy of a detected thermal source.
- **Confidence:** FIRMS classifies detections as low (`l`), nominal (`n`), or high (`h`) confidence. Confidence describes the satellite retrieval, not incident severity.
- **Cluster:** A spatially and temporally associated group of FIRMS detections used to monitor persistence. It is a heuristic analytical track, not a NASA fire-event definition or confirmed individual fire.
- **Persistent:** A tracked cluster observed on at least two distinct days. Cluster centroids and marker sizes do not represent burned area.
- **Monitoring priority:** A relative ranking based on recent detections (35%), FRP (25%), persistence (25%), and positive growth versus the previous period (15%). It is not fire risk, severity, burned area, or emergency status.
- **Interpretation:** A hotspot is a satellite-detected thermal anomaly. It may have causes other than a forest or land fire and is not a confirmed incident. Density and cluster visualizations do not represent confirmed burned area.
            """
        )
        st.caption(
            "Near-real-time observations can arrive after the dataset is generated. "
            f"Latest acquisition included here: {format_timestamp(latest_acquisition)}."
        )


try:
    (
        firms,
        province_daily,
        kabkota_daily,
        clusters,
        monitoring,
    ) = load_data()
except FileNotFoundError as error:
    st.error(
        "Dashboard analytics files are missing. Rebuild or restore the committed "
        "Parquet files under data/analytics.",
        icon=":material/error:",
    )
    st.exception(error)
    st.stop()

available_dates = firms.get_column("acq_date").unique().sort().to_list()
available_provinces = firms.get_column("province").unique().sort().to_list()
earliest_date = available_dates[0]
latest_date = available_dates[-1]
latest_acquisition = firms.get_column("acquired_at_utc").max()
latest_date_may_be_partial = is_partial_latest_date(
    latest_date,
    datetime.now(timezone.utc).date(),
)
default_custom_start = date.fromisoformat(
    available_dates[max(0, len(available_dates) - PRESET_DAYS["7D"])]
)
latest_date_value = date.fromisoformat(latest_date)
monitoring_start_date = (
    monitoring.get_column("monitoring_start_date").min().isoformat()
)
monitoring_end_date = (
    monitoring.get_column("monitoring_end_date").max().isoformat()
)

with st.sidebar:
    st.header("Filters")
    st.caption("Choose a monitoring period and geographic scope.")
    selected_period = st.segmented_control(
        "Period",
        [*PRESET_DAYS, CUSTOM_PERIOD],
        default="7D",
        required=True,
        width="stretch",
        key="period",
    )
    if selected_period == CUSTOM_PERIOD:
        custom_selection = st.segmented_control(
            "Custom selection",
            [SINGLE_DATE, DATE_RANGE],
            default=DATE_RANGE,
            required=True,
            width="stretch",
            key="custom_selection",
        )
        if custom_selection == SINGLE_DATE:
            custom_date = st.date_input(
                "Date",
                value=latest_date_value,
                min_value=date.fromisoformat(earliest_date),
                max_value=latest_date_value,
                format="DD/MM/YYYY",
                key="custom_date",
                persist_state="session",
            )
            start_date = end_date = custom_date.isoformat()
        else:
            custom_range = st.date_input(
                "Date range",
                value=(default_custom_start, latest_date_value),
                min_value=date.fromisoformat(earliest_date),
                max_value=latest_date_value,
                format="DD/MM/YYYY",
                key="custom_range",
                persist_state="session",
            )
            if not custom_range:
                st.warning(
                    "Select a start and end date.",
                    icon=":material/date_range:",
                )
                st.stop()
            custom_start = custom_range[0]
            custom_end = custom_range[-1]
            start_date = custom_start.isoformat()
            end_date = custom_end.isoformat()
    else:
        period_days = PRESET_DAYS[selected_period]
        start_index = max(0, len(available_dates) - period_days)
        start_date = available_dates[start_index]
        end_date = latest_date

    selected_province = st.selectbox(
        "Province",
        [ALL_INDONESIA, *available_provinces],
        key="province",
    )
    selected_confidence = st.selectbox(
        "Confidence level",
        list(CONFIDENCE_CODES),
        index=list(CONFIDENCE_CODES).index("High"),
        key="confidence",
        help=(
            "FIRMS retrieval confidence: high (h), nominal (n), or low (l). "
            "This is not a measure of fire severity."
        ),
    )
    st.caption(
        f"Data coverage: {format_date(earliest_date)}–"
        f"{format_date(latest_date)}."
    )
    if start_date <= latest_date <= end_date:
        st.caption(
            ":material/update: Latest available data: "
            f"{format_date(latest_date)}."
        )
        if latest_date_may_be_partial:
            st.caption(
                ":material/schedule: The current UTC day may still receive "
                "detections."
            )

selected_dates = [
    value for value in available_dates if start_date <= value <= end_date
]
if not selected_dates:
    st.warning(
        "No analytics dates are available in the selected period.",
        icon=":material/date_range:",
    )
    st.stop()

confidence_code = CONFIDENCE_CODES[selected_confidence]
filtered = filter_hotspots(
    firms, start_date, end_date, selected_province, confidence_code
)
trend = build_trend(
    province_daily,
    firms,
    selected_dates,
    selected_province,
    confidence_code,
)
ranking = build_ranking(
    kabkota_daily,
    firms,
    start_date,
    end_date,
    selected_province,
    confidence_code,
)
monitoring_ranking = build_monitoring_ranking(
    monitoring,
    selected_province,
)

render_header(
    start_date,
    end_date,
    selected_province,
    selected_confidence,
    latest_date,
    latest_date_may_be_partial,
)
render_metrics(filtered)
render_map(
    filtered,
    clusters,
    start_date,
    end_date,
    selected_province,
    selected_confidence,
)
render_monitoring_priority(
    monitoring_ranking,
    monitoring_start_date,
    monitoring_end_date,
    selected_province,
)
render_trend(
    trend,
    start_date,
    end_date,
    selected_province,
    selected_confidence,
    latest_date,
    latest_date_may_be_partial,
)
render_ranking(ranking, selected_province, selected_confidence)
render_methodology(latest_acquisition)
