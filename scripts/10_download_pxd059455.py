#!/usr/bin/env python
"""Download PRIDE PXD059455 files inside the training container."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import requests
from tqdm import tqdm


PROJECT = "PXD059455"
FILES_URL = f"https://www.ebi.ac.uk/pride/ws/archive/v2/projects/{PROJECT}/files"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out-dir", required=True)
    parser.add_argument("--include-raw", action="store_true", help="Also download vendor .raw files.")
    parser.add_argument("--labels", default=None, help="Optional msms.xlsx path; when set, download only labelled raw files.")
    parser.add_argument("--limit", type=int, default=None, help="Download only the first N mzXML files for smoke tests.")
    parser.add_argument("--sample-regex", default=None, help="Only download files whose names match this regex.")
    parser.add_argument("--force", action="store_true")
    return parser.parse_args()


def labelled_raw_files(labels_path: str | None) -> set[str] | None:
    if labels_path is None:
        return None
    import pandas as pd

    labels = pd.read_excel(labels_path, usecols=["Raw file"])
    raws = set()
    for value in labels["Raw file"].dropna():
        raw = str(value).strip()
        if raw.lower().endswith(".raw"):
            raw = raw[:-4]
        raws.add(raw)
    if not raws:
        raise ValueError(f"No raw files found in labels: {labels_path}")
    return raws


def get_http_url(file_record: dict[str, Any]) -> str:
    for loc in file_record.get("publicFileLocations", []):
        value = loc.get("value", "")
        if value.startswith("ftp://"):
            parsed = urlparse(value)
            return f"https://{parsed.netloc}{parsed.path}"
        if value.startswith("http://") or value.startswith("https://"):
            return value
    raise ValueError(f"No downloadable URL found for {file_record.get('fileName')}")


def wanted_files(
    files: list[dict[str, Any]],
    include_raw: bool,
    sample_regex: str | None,
    limit: int | None,
    labelled_raws: set[str] | None,
) -> list[dict[str, Any]]:
    pattern = re.compile(sample_regex) if sample_regex else None
    mzxml = []
    metadata = []
    raw = []
    for record in files:
        name = record["fileName"]
        if pattern and not pattern.search(name):
            continue
        lower = name.lower()
        if lower.endswith(".mzxml"):
            if labelled_raws is not None and Path(name).stem not in labelled_raws:
                continue
            mzxml.append(record)
        elif lower in {"checksum.txt"} or lower.endswith(".xlsx") or lower.endswith(".fasta"):
            metadata.append(record)
        elif include_raw and lower.endswith(".raw"):
            if labelled_raws is not None and Path(name).stem not in labelled_raws:
                continue
            raw.append(record)

    mzxml = sorted(mzxml, key=lambda x: x["fileName"])
    if limit is not None:
        mzxml = mzxml[:limit]
    metadata = sorted(metadata, key=lambda x: x["fileName"])
    raw = sorted(raw, key=lambda x: x["fileName"])
    return metadata + mzxml + raw


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def download(record: dict[str, Any], out_dir: Path, force: bool) -> dict[str, Any]:
    name = record["fileName"]
    target = out_dir / name
    expected_size = int(record.get("fileSizeBytes") or 0)
    accession = str(record.get("accession") or "")

    if target.exists() and not force:
        if expected_size == 0 or target.stat().st_size == expected_size:
            print(f"Skipping existing file: {target}")
            return {"file": name, "status": "skipped", "bytes": target.stat().st_size}

    url = get_http_url(record)
    tmp = target.with_suffix(target.suffix + ".part")
    headers = {}
    resume_at = tmp.stat().st_size if tmp.exists() and not force else 0
    mode = "ab" if resume_at else "wb"
    if resume_at:
        headers["Range"] = f"bytes={resume_at}-"

    print(f"Downloading {name} from {url}")
    with requests.get(url, stream=True, timeout=60, headers=headers) as response:
        response.raise_for_status()
        total = int(response.headers.get("content-length", "0")) + resume_at
        with tmp.open(mode) as handle, tqdm(
            total=total or expected_size,
            initial=resume_at,
            unit="B",
            unit_scale=True,
            unit_divisor=1024,
            desc=name,
        ) as progress:
            for chunk in response.iter_content(chunk_size=1024 * 1024):
                if chunk:
                    handle.write(chunk)
                    progress.update(len(chunk))

    tmp.replace(target)

    if expected_size and target.stat().st_size != expected_size:
        raise RuntimeError(f"Size mismatch for {target}: got {target.stat().st_size}, expected {expected_size}")

    if re.fullmatch(r"[0-9a-fA-F]{64}", accession):
        observed = sha256(target)
        if observed.lower() != accession.lower():
            raise RuntimeError(f"SHA256 mismatch for {target}: got {observed}, expected {accession}")

    return {"file": name, "status": "downloaded", "bytes": target.stat().st_size}


def main() -> None:
    args = parse_args()
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    response = requests.get(FILES_URL, timeout=60)
    response.raise_for_status()
    files = response.json()
    selected = wanted_files(files, args.include_raw, args.sample_regex, args.limit, labelled_raw_files(args.labels))
    if not selected:
        raise SystemExit("No PRIDE files selected for download.")

    manifest = []
    for record in selected:
        manifest.append(download(record, out_dir, args.force))

    manifest_path = out_dir / "download_manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(f"Wrote {manifest_path}")

    mzxml_count = sum(1 for item in manifest if item["file"].lower().endswith(".mzxml"))
    if mzxml_count == 0:
        print("No mzXML files were downloaded.", file=sys.stderr)
        sys.exit(2)


if __name__ == "__main__":
    main()
