from pathlib import Path

import requests


ROOT = Path(__file__).resolve().parents[1]
OUTPUT_DIR = ROOT / "data" / "boundaries"

API_BASE = "https://www.geoboundaries.org/api/current/gbOpen/IDN"

BOUNDARIES = {
    "ADM1": "geoBoundaries-IDN-ADM1-provinces.geojson",
    "ADM2": "geoBoundaries-IDN-ADM2-districts.geojson",
}


def download_boundary(
    admin_level: str,
    filename: str,
) -> Path:
    metadata_url = f"{API_BASE}/{admin_level}/"

    response = requests.get(metadata_url, timeout=30)
    response.raise_for_status()

    metadata = response.json()
    download_url = metadata["gjDownloadURL"]

    print(f"Downloading {admin_level}...")

    response = requests.get(download_url, timeout=120)
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