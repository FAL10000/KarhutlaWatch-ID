# KarhutlaWatch Indonesia

KarhutlaWatch is an interactive monitoring dashboard for satellite-detected thermal anomalies across Indonesia.

It retrieves near-real-time hotspot detections from **NASA FIRMS VIIRS NOAA-20**, filters them to Indonesian territory, assigns administrative regions, tracks repeated hotspot activity across days, and presents the results through a public Streamlit dashboard.

**Live app:** https://karhutlawatch-id.streamlit.app/

> KarhutlaWatch is a monitoring and exploratory analytics project. A satellite hotspot or tracked cluster is not the same as a confirmed forest-fire incident or measured burned area.

## Features

### Hotspot monitoring

- Rolling 30-day NASA FIRMS dataset
- Province and kabupaten/kota filtering
- Confidence-level filtering
- Single-date and date-range analysis
- Individual hotspot map
- Hotspot-density map
- Combined hotspot + density view
- Daily hotspot trends
- Kabupaten/kota activity rankings
- Fire Radiative Power (FRP) metrics

### Persistent activity

KarhutlaWatch groups spatially nearby FIRMS detections and tracks those groups across consecutive days.

This makes it possible to distinguish:

- isolated thermal detections
- repeatedly observed thermal activity
- long-running hotspot clusters

Persistent clusters are analytical monitoring features and are **not confirmed individual fires**.

### Monitoring priority

The dashboard also provides a rolling monitoring-priority ranking by kabupaten/kota.

The score combines:

- 35% recent detection activity
- 25% Fire Radiative Power
- 25% hotspot persistence
- 15% positive activity growth

The score is relative to other monitored areas and should not be interpreted as an official fire-risk, severity, or emergency classification.

## Architecture

```text
NASA FIRMS
    ↓
FIRMS Area API
    ↓
Raw detections
    ↓
Polars transformation
    ↓
Point geometry
    ↓
geoBoundaries ADM1 / ADM2 spatial join
    ↓
Indonesia-only hotspot data
    ↓
Rolling 30-day dataset
    ↓
Daily administrative aggregations
    ↓
DBSCAN hotspot clustering
    ↓
Cross-day cluster tracking
    ↓
Monitoring-priority analytics
    ↓
Streamlit dashboard
```

## Automated Data Refresh

KarhutlaWatch is refreshed automatically with GitHub Actions.

```text
Every 3 hours
    ↓
Download latest NASA FIRMS NRT data
    ↓
Replace the current UTC day's snapshot
    ↓
Keep latest 30 acquisition dates
    ↓
Rebuild administrative summaries
    ↓
Rebuild hotspot clusters
    ↓
Rebuild monitoring-priority dataset
    ↓
Publish latest analytics
    ↓
Streamlit displays updated data
```

The current UTC acquisition day is refreshed repeatedly because NASA FIRMS near-real-time data can still be incomplete while the day is in progress.

Once each morning, the workflow also retrieves the previous UTC acquisition day again to replace its earlier near-real-time snapshot with a later version.

Monitoring-priority comparisons use only completed acquisition days. This avoids comparing a partial current day against a complete historical period.

## Data Products

KarhutlaWatch generates five analytical datasets:

```text
firms_30d.parquet
    Individual FIRMS detections for the rolling 30-day window

daily_province.parquet
    Daily hotspot metrics by province

daily_kabupaten_kota.parquet
    Daily hotspot metrics by kabupaten/kota

hotspot_clusters.parquet
    Spatial hotspot clusters tracked across days

monitoring_areas.parquet
    Latest completed 7-day monitoring snapshot by kabupaten/kota
```

## Tech Stack

| Technology | Purpose |
|---|---|
| Python | Application and data pipeline |
| Polars | Data transformation and aggregation |
| polars-st | Spatial geometry and administrative joins |
| NumPy | Numerical data preparation |
| scikit-learn | DBSCAN hotspot clustering |
| Streamlit | Public interactive dashboard |
| PyDeck | Interactive geographic visualization |
| Altair | Dashboard charts |
| Parquet | Compact analytical storage |
| requests | NASA FIRMS and boundary downloads |
| uv | Dependency and Python environment management |
| GitHub Actions | Scheduled automated data refresh |
| Streamlit Community Cloud | Public application hosting |

## Data Sources

### NASA FIRMS

**Fire Information for Resource Management System**

Current satellite product:

- VIIRS
- NOAA-20
- Near Real-Time (NRT)

Used for:

- hotspot coordinates
- acquisition date/time
- detection confidence
- Fire Radiative Power (FRP)
- thermal anomaly monitoring

https://firms.modaps.eosdis.nasa.gov/

### geoBoundaries

KarhutlaWatch uses the `gbOpen` Indonesia administrative boundaries.

Used for:

- filtering detections to Indonesian territory
- assigning province (ADM1)
- assigning kabupaten/kota (ADM2)

https://www.geoboundaries.org/

geoBoundaries `gbOpen` data is distributed under CC BY 4.0.

## Project Structure

```text
KarhutlaWatch-ID/
├── .github/
│   └── workflows/
│       └── refresh.yml
│
├── data/
│   ├── analytics/
│   ├── boundaries/
│   ├── processed/
│   └── raw/
│
├── scripts/
│   └── download_boundaries.py
│
├── src/
│   └── karhutlawatch/
│       ├── aggregate.py
│       ├── app.py
│       ├── firms.py
│       ├── monitoring.py
│       ├── pipeline.py
│       ├── refresh.py
│       └── transform.py
│
├── notebooks/
├── tests/
├── pyproject.toml
└── uv.lock
```

Raw, processed, and large administrative-boundary files are intentionally excluded from Git.

## Local Setup

Clone the repository:

```bash
git clone https://github.com/FAL10000/KarhutlaWatch-ID.git
cd KarhutlaWatch-ID
```

Install dependencies:

```bash
uv sync
```

Create:

```text
.env
```

with:

```env
FIRMS_MAP_KEY=your_nasa_firms_map_key
```

## Administrative Boundaries

Download the required Indonesia ADM1 and ADM2 boundaries:

```bash
uv run python scripts/download_boundaries.py
```

## Refresh the Dataset

A complete rolling refresh can be run with:

```bash
uv run python -m karhutlawatch.refresh
```

A particular acquisition date can be replaced with:

```bash
uv run python -m karhutlawatch.refresh --date YYYY-MM-DD
```

The refresh pipeline is designed to replace an existing date rather than duplicate it.

## Run the Dashboard

```bash
uv run streamlit run src/karhutlawatch/app.py
```

The local app will normally be available at:

```text
http://localhost:8501
```

## Methodology Notes

### Hotspot

A hotspot is a satellite-detected thermal anomaly reported by NASA FIRMS.

It does not necessarily represent a confirmed forest or land fire.

### Fire Radiative Power

FRP represents the rate of radiant energy emitted by a detected thermal anomaly and is reported in megawatts.

It is useful for comparing thermal activity but is not the same as burned area.

### Persistent Cluster

Daily hotspots located within approximately 5 km are grouped using DBSCAN.

Nearby daily clusters are then associated across days using a distance-based tracking heuristic.

A tracked cluster observed on at least two distinct days is considered persistent.

These parameters are analytical heuristics and are not official NASA fire-event definitions.

### Incomplete Data

The latest UTC acquisition day may be incomplete because additional satellite observations can arrive later.

Live hotspot views may include this partial day.

Monitoring-priority comparisons intentionally use completed acquisition days only.

## Current Limitations

- Satellite hotspots are not confirmed fire incidents
- Cluster boundaries do not represent burned area
- Monitoring priority is not an official risk or severity score
- Only NOAA-20 VIIRS NRT is currently used
- Current analysis covers a rolling 30-day period
- Weather conditions are not yet incorporated
- Cluster tracking uses heuristic distance thresholds
- Satellite revisit timing is not yet explicitly modeled, NOAA-20/VIIRS does not observe all of Indonesia continuously
- A refresh does not necessarily mean a newer acquisition timestamp

## Possible Future Work

- BMKG weather context
- rainfall, humidity, and wind overlays
- seasonal and historical baselines
- peatland / land-cover context
- smoke and air-quality indicators
- alerts for rapidly increasing persistent activity

## License

The source code in this repository is licensed under the [MIT License](LICENSE).

Data and third-party materials are not covered by the MIT License:

- NASA FIRMS / VIIRS NOAA-20 data remain subject to the applicable NASA Earthdata and FIRMS data-use and citation guidance. NASA FIRMS should be acknowledged as the data source.
- geoBoundaries `gbOpen` administrative boundaries are licensed under [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/) and require attribution.
- Derived analytics files retain any applicable source-data terms and attribution requirements.

This project is independent and is not endorsed by NASA, NOAA, or geoBoundaries.