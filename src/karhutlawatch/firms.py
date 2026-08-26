import os
from io import BytesIO
from pathlib import Path
import time

import polars as pl
import requests
from dotenv import load_dotenv


ROOT = Path(__file__).resolve().parents[2]
OUTPUT_DIR = ROOT / "data" / "raw" / "firms"
BASE_URL = "https://firms.modaps.eosdis.nasa.gov/api/area/csv"

load_dotenv(ROOT / ".env")

RETRY_DELAYS = [5, 15, 30]


def get_with_retry(url: str, timeout: int) -> requests.Response:
    for attempt in range(4):
        try:
            response = requests.get(url, timeout=timeout)

            if response.status_code == 429 or response.status_code >= 500:
                response.raise_for_status()

            response.raise_for_status()
            return response

        except (requests.ConnectionError, requests.Timeout) as error:
            if attempt == 3:
                raise

            delay = RETRY_DELAYS[attempt]
            print(
                f"Request failed ({type(error).__name__}). "
                f"Retrying in {delay}s..."
            )
            time.sleep(delay)

        except requests.HTTPError as error:
            status = error.response.status_code

            if status != 429 and status < 500:
                raise

            if attempt == 3:
                raise

            delay = RETRY_DELAYS[attempt]
            print(
                f"HTTP {status}. Retrying in {delay}s..."
            )
            time.sleep(delay)

    raise RuntimeError("Request failed after retries.")

def fetch_firms(
    source: str,
    area: str,
    day_range: int = 1,
    date: str | None = None,
) -> pl.DataFrame:
    MAP_KEY = os.environ["FIRMS_MAP_KEY"]

    url = f"{BASE_URL}/{MAP_KEY}/{source}/{area}/{day_range}"

    if date is not None:
        url += f"/{date}"

    response = get_with_retry(url, timeout=30)
    response.raise_for_status()

    return pl.read_csv(BytesIO(response.content))


def save_raw(
    df: pl.DataFrame,
    source: str,
    date: str,
) -> Path:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    source_name = source.lower().replace("_nrt", "")
    output_path = OUTPUT_DIR / f"firms_{source_name}_{date}.parquet"

    df.write_parquet(output_path)

    return output_path


if __name__ == "__main__":
    source = "VIIRS_NOAA20_NRT"
    date = "2026-08-24"

    df = fetch_firms(
        source=source,
        area="95,-11,141,6",
        date=date,
    )

    output_path = save_raw(
        df=df,
        source=source,
        date=date,
    )

    print(f"Retrieved {df.height:,} detections")
    print(f"Saved to {output_path}")