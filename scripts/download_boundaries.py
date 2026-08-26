from pathlib import Path
import time

import requests


ROOT = Path(__file__).resolve().parents[1]
OUTPUT_DIR = ROOT / "data" / "boundaries"

API_BASE = "https://www.geoboundaries.org/api/current/gbOpen/IDN"

BOUNDARIES = {
    "ADM1": "geoBoundaries-IDN-ADM1-provinces.geojson",
    "ADM2": "geoBoundaries-IDN-ADM2-districts.geojson",
}

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

def download_boundary(
    admin_level: str,
    filename: str,
) -> Path:
    metadata_url = f"{API_BASE}/{admin_level}/"

    response = get_with_retry(metadata_url, timeout=30)
    response.raise_for_status()

    metadata = response.json()
    download_url = metadata["gjDownloadURL"]

    print(f"Downloading {admin_level}...")

    response = get_with_retry(download_url, timeout=120)
    response.raise_for_status()

    output_path = OUTPUT_DIR / filename
    output_path.write_bytes(response.content)

    return output_path


def main():
    OUTPUT_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    for admin_level, filename in BOUNDARIES.items():
        output_path = download_boundary(
            admin_level,
            filename,
        )

        size_mb = output_path.stat().st_size / 1024 / 1024

        print(
            f"Saved {output_path.name} "
            f"({size_mb:.1f} MB)"
        )


if __name__ == "__main__":
    main()