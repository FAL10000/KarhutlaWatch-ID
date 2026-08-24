import os
from io import BytesIO

import polars as pl
import requests
from dotenv import load_dotenv
from pathlib import Path

load_dotenv()

MAP_KEY = os.environ["FIRMS_MAP_KEY"]

SOURCE = "VIIRS_NOAA20_NRT"
AREA = "95,-11,141,6"
DAY_RANGE = 1

url = f"https://firms.modaps.eosdis.nasa.gov/api/area/csv/{MAP_KEY}/{SOURCE}/{AREA}/{DAY_RANGE}"

response = requests.get(url, timeout=30)
response.raise_for_status()

df = pl.read_csv(BytesIO(response.content))

output_dir = Path("../../data/raw")
output_dir.mkdir(parents=True, exist_ok=True)

df.write_parquet(output_dir / "firms_noaa20.parquet")