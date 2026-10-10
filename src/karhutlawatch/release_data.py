import argparse
import io
import os
from pathlib import Path
from zipfile import ZIP_STORED, ZipFile

import polars as pl
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

ROOT = Path(__file__).resolve().parents[2]
ANALYTICS = ROOT / "data" / "analytics"
BUNDLE = ROOT / "dist" / "analytics.zip"
REPO = "FAL10000/KarhutlaWatch-ID"

FILES = (
    "firms_30d.parquet",
    "daily_province.parquet",
    "daily_kabupaten_kota.parquet",
    "hotspot_clusters.parquet",
    "monitoring_areas.parquet",
)


def read_bundle(content: bytes) -> dict[str, bytes]:
    """Validate a complete snapshot before using any of its files."""
    with ZipFile(io.BytesIO(content)) as archive:
        if (
            len(archive.namelist()) != len(FILES)
            or set(archive.namelist()) != set(FILES)
        ):
            raise ValueError("Snapshot must contain exactly five datasets.")

        datasets = {name: archive.read(name) for name in FILES}

    for content in datasets.values():
        pl.read_parquet(io.BytesIO(content))

    return datasets


def download_snapshot() -> dict[str, bytes]:
    """Download the complete latest published analytics snapshot."""
    retry = Retry(
        total=3,
        backoff_factor=1,
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods={"GET"},
    )

    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "KarhutlaWatch",
    }
    token = os.environ.get("GH_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"

    try:
        with requests.Session() as session:
            session.mount("https://", HTTPAdapter(max_retries=retry))

            response = session.get(
                f"https://api.github.com/repos/{REPO}/releases/latest",
                headers=headers,
                timeout=(10, 60),
            )
            response.raise_for_status()
            release = response.json()

            if not release["tag_name"].startswith("analytics-"):
                raise ValueError("Latest release is not an analytics snapshot.")

            assets = [
                asset
                for asset in release["assets"]
                if asset["name"] == "analytics.zip"
            ]
            if len(assets) != 1:
                raise ValueError("Release must contain one analytics.zip.")

            response = session.get(
                assets[0]["browser_download_url"],
                timeout=(10, 120),
            )
            response.raise_for_status()

        return read_bundle(response.content)

    except Exception as error:
        raise RuntimeError(
            "Could not download a complete analytics snapshot."
        ) from error


def pack_snapshot() -> None:
    """Package and validate all five local analytical datasets."""
    BUNDLE.parent.mkdir(parents=True, exist_ok=True)
    temporary = BUNDLE.with_name("analytics.tmp.zip")

    with ZipFile(temporary, "w", compression=ZIP_STORED) as archive:
        for name in FILES:
            archive.write(ANALYTICS / name, arcname=name)

    read_bundle(temporary.read_bytes())
    temporary.replace(BUNDLE)
    print(f"Created {BUNDLE}")


def restore_snapshot() -> None:
    """Restore the baseline required by the incremental refresh."""
    datasets = download_snapshot()
    ANALYTICS.mkdir(parents=True, exist_ok=True)

    for name, content in datasets.items():
        destination = ANALYTICS / name
        temporary = destination.with_suffix(".parquet.tmp")
        temporary.write_bytes(content)
        temporary.replace(destination)

    print(f"Restored snapshot into {ANALYTICS}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("pack", "download"))
    args = parser.parse_args()

    if args.command == "pack":
        pack_snapshot()
    else:
        restore_snapshot()


if __name__ == "__main__":
    main()
