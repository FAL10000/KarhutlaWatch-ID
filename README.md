# KarhutlaWatch Indonesia

KarhutlaWatch is a Python-based dashboard for exploring satellite-detected fire hotspots across Indonesia.

The project retrieves active fire detections from **NASA FIRMS**, filters them to Indonesian territory, assigns each detection to its province and kabupaten/kota, and presents recent hotspot activity through an interactive Streamlit dashboard.

> **Status:** Early MVP. The current dashboard uses a 30-day snapshot of NOAA-20 VIIRS hotspot detections.

## Features

- Retrieve hotspot detections from the NASA FIRMS API
- Filter detections to Indonesia using administrative boundaries
- Assign province and kabupaten/kota using spatial joins
- Store intermediate datasets as Parquet
- Aggregate daily hotspot activity by administrative area
- Track:
  - hotspot count
  - high-confidence detections
  - total Fire Radiative Power (FRP)
  - maximum FRP
- Interactive Streamlit dashboard with:
  - date filtering
  - province filtering
  - hotspot map
  - 30-day trend
  - top kabupaten/kota ranking

## Data Pipeline

```text
NASA FIRMS
    ↓
Raw hotspot detections
    ↓
Polars transformation
    ↓
Point geometry
    ↓
geoBoundaries ADM1 / ADM2 spatial join
    ↓
Indonesia hotspot dataset
    ↓
Daily aggregations
    ↓
Streamlit dashboard
```

## Tech Stack

- Python
- Polars
- polars-st
- Streamlit
- NASA FIRMS API
- geoBoundaries
- Parquet
- uv

## Project Structure

```text
KarhutlaWatch-ID/
├── data/
│   ├── analytics/
│   ├── boundaries/
│   ├── processed/
│   └── raw/
├── scripts/
│   └── download_boundaries.py
├── src/
│   └── karhutlawatch/
│       ├── aggregate.py
│       ├── app.py
│       ├── firms.py
│       ├── pipeline.py
│       └── transform.py
├── notebooks/
├── tests/
├── pyproject.toml
└── uv.lock
```

Raw, processed, and boundary datasets are not stored in the repository. The analytics datasets required by the current dashboard are included.

## Setup

Clone the repository:

```bash
git clone https://github.com/FAL10000/KarhutlaWatch-ID.git
cd KarhutlaWatch-ID
```

Install dependencies:

```bash
uv sync
```

For FIRMS ingestion, create a `.env` file:

```env
FIRMS_MAP_KEY=your_nasa_firms_map_key
```

A NASA FIRMS MAP_KEY can be obtained from the NASA FIRMS API website.

## Download Administrative Boundaries

The transformation pipeline uses Indonesian ADM1 and ADM2 boundaries from geoBoundaries.

Download them with:

```bash
uv run python scripts/download_boundaries.py
```

This creates the required GeoJSON files under:

```text
data/boundaries/
```

## Run the Data Pipeline

Run a FIRMS ingestion and transformation:

```bash
uv run python -m karhutlawatch.pipeline
```

Build the analytical datasets:

```bash
uv run python -m karhutlawatch.aggregate
```

## Run the Dashboard

```bash
uv run streamlit run src/karhutlawatch/app.py
```

The dashboard will normally be available at:

```text
http://localhost:8501
```

## Data Sources

### NASA FIRMS

Active fire and thermal anomaly detections are retrieved from the NASA Fire Information for Resource Management System (FIRMS).

Current MVP data source:

- VIIRS
- NOAA-20
- Near Real-Time (NRT)

https://firms.modaps.eosdis.nasa.gov/

### geoBoundaries

Administrative boundaries are retrieved from the geoBoundaries `gbOpen` dataset.

https://www.geoboundaries.org/

geoBoundaries `gbOpen` data is distributed under the CC BY 4.0 license.

## Important Note

A FIRMS hotspot represents a satellite-detected thermal anomaly. It does **not necessarily mean that a forest or land fire has been independently confirmed**.

Hotspot counts should therefore be interpreted as indicators of detected thermal activity rather than confirmed fire incidents.

Near-real-time data for the current day may also be incomplete because additional satellite observations can arrive later.

## Roadmap

Planned improvements include:

- Automated daily FIRMS updates
- Rolling 30-day dataset generation
- Improved hotspot mapping and tooltips
- Hotspot persistence detection
- Historical and seasonal analysis
- Weather context from BMKG
- Fire-risk / escalation indicators
- Public Streamlit deployment

## License

Project license to be determined.

Data remains subject to the terms and licenses of its respective providers.