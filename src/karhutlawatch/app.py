from pathlib import Path

import polars as pl
import streamlit as st


ROOT = Path(__file__).resolve().parents[2]
ANALYTICS = ROOT / "data" / "analytics"

FIRMS_PATH = ANALYTICS / "firms_30d.parquet"
PROVINCE_PATH = ANALYTICS / "daily_province.parquet"
KABKOTA_PATH = ANALYTICS / "daily_kabupaten_kota.parquet"


@st.cache_data
def load_data():
    firms = pl.read_parquet(FIRMS_PATH)
    province = pl.read_parquet(PROVINCE_PATH)
    kabkota = pl.read_parquet(KABKOTA_PATH)

    return firms, province, kabkota


firms, province, kabkota = load_data()


st.set_page_config(
    page_title="KarhutlaWatch Indonesia",
    layout="wide",
)

st.title("KarhutlaWatch Indonesia")
st.caption("NASA FIRMS hotspot monitoring for Indonesia")


# Filters

dates = (
    firms
    .select("acq_date")
    .unique()
    .sort("acq_date")
    .get_column("acq_date")
    .to_list()
)

provinces = (
    firms
    .select("province")
    .unique()
    .sort("province")
    .get_column("province")
    .to_list()
)

selected_date = st.selectbox(
    "Date",
    dates,
    index=len(dates) - 1,
)

selected_province = st.selectbox(
    "Province",
    ["All Indonesia"] + provinces,
)


# Filter hotspot data

filtered = firms.filter(
    pl.col("acq_date") == selected_date
)

if selected_province != "All Indonesia":
    filtered = filtered.filter(
        pl.col("province") == selected_province
    )


# KPIs

hotspot_count = filtered.height

high_confidence_count = filtered.filter(
    pl.col("confidence") == "h"
).height

total_frp = filtered.get_column("frp").sum()

affected_kabkota = filtered.get_column(
    "kabupaten_kota"
).n_unique()


col1, col2, col3, col4 = st.columns(4)

col1.metric(
    "Hotspots",
    f"{hotspot_count:,}",
)

col2.metric(
    "High confidence",
    f"{high_confidence_count:,}",
)

col3.metric(
    "Total FRP",
    f"{total_frp:,.0f}",
)

col4.metric(
    "Kabupaten/Kota",
    f"{affected_kabkota:,}",
)


# Map

st.subheader("Hotspot map")

map_data = filtered.select(
    "latitude",
    "longitude",
)

st.map(
    map_data,
    latitude="latitude",
    longitude="longitude",
)


# 30-day trend

st.subheader("Hotspot trend")

trend = province

if selected_province != "All Indonesia":
    trend = trend.filter(
        pl.col("province") == selected_province
    )
else:
    trend = (
        trend
        .group_by("acq_date")
        .agg(
            pl.col("hotspot_count")
            .sum()
            .alias("hotspot_count")
        )
    )

trend = trend.sort("acq_date")

st.line_chart(
    trend,
    x="acq_date",
    y="hotspot_count",
)


# Top Kabupaten/Kota

st.subheader("Top Kabupaten/Kota")

ranking = kabkota.filter(
    pl.col("acq_date") == selected_date
)

if selected_province != "All Indonesia":
    ranking = ranking.filter(
        pl.col("province") == selected_province
    )

ranking = (
    ranking
    .sort(
        "hotspot_count",
        descending=True,
    )
    .head(10)
)

st.dataframe(
    ranking.select(
        "province",
        "kabupaten_kota",
        "hotspot_count",
        "high_confidence_count",
        "total_frp",
        "max_frp",
    ),
    hide_index=True,
    use_container_width=True,
)