#!/usr/bin/env python
"""Upload selected local run artifacts to Aichor output storage when available."""

from __future__ import annotations

import argparse
import os
from pathlib import Path

import s3fs


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("paths", nargs="+")
    return parser.parse_args()


def normalise_output_path(path: str) -> str:
    if path.startswith("s3://"):
        return path.rstrip("/")
    return f"s3://{path.strip('/')}/output"


def main() -> None:
    args = parse_args()
    output = os.environ.get("AICHOR_OUTPUT_PATH")
    endpoint = os.environ.get("AWS_ENDPOINT_URL") or os.environ.get("S3_ENDPOINT")
    if not output:
        print("AICHOR_OUTPUT_PATH is not set; artifacts remain local.")
        return

    fs = s3fs.S3FileSystem(client_kwargs={"endpoint_url": endpoint} if endpoint else None)
    dest_root = normalise_output_path(output)

    for raw_path in args.paths:
        path = Path(raw_path)
        if not path.exists():
            print(f"Skipping missing artifact path: {path}")
            continue
        if path.is_file():
            dest = f"{dest_root}/{path.name}"
            print(f"Uploading {path} -> {dest}")
            fs.put(str(path), dest)
            continue
        for file_path in path.rglob("*"):
            if file_path.is_file():
                rel = file_path.relative_to(path)
                dest = f"{dest_root}/{path.name}/{rel.as_posix()}"
                print(f"Uploading {file_path} -> {dest}")
                fs.put(str(file_path), dest)


if __name__ == "__main__":
    main()

