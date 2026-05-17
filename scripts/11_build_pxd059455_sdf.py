#!/usr/bin/env python
"""Build PTM-aware InstaNovo SpectrumDataFrame shards from PXD059455 mzXML."""

from __future__ import annotations

import argparse
import json
import math
import random
import re
from collections import Counter
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import polars as pl
from pyteomics import mzxml

from instanovo.constants import PROTON_MASS_AMU
from instanovo.utils.data_handler import SpectrumDataFrame
from instanovo.utils.residues import ResidueSet


RESIDUES = {
    "G": 57.021464,
    "A": 71.037114,
    "S": 87.032028,
    "P": 97.052764,
    "V": 99.068414,
    "T": 101.047670,
    "C": 103.009185,
    "L": 113.084064,
    "I": 113.084064,
    "N": 114.042927,
    "D": 115.026943,
    "Q": 128.058578,
    "K": 128.094963,
    "E": 129.042593,
    "M": 131.040485,
    "H": 137.058912,
    "F": 147.068414,
    "R": 156.101111,
    "Y": 163.063329,
    "W": 186.079313,
    "M[UNIMOD:35]": 147.035400,
    "C[UNIMOD:4]": 160.030649,
    "N[UNIMOD:7]": 115.026943,
    "Q[UNIMOD:7]": 129.042594,
    "S[UNIMOD:21]": 166.998028,
    "T[UNIMOD:21]": 181.013670,
    "Y[UNIMOD:21]": 243.029329,
    "[UNIMOD:1]": 42.010565,
    "[UNIMOD:5]": 43.005814,
    "[UNIMOD:385]": -17.026549,
}
RESIDUE_SET = ResidueSet(RESIDUES)
WATER_MASS = 18.0106


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--labels", default="docs/msms.xlsx")
    parser.add_argument("--mzxml-dir", required=True)
    parser.add_argument("--out-dir", required=True)
    parser.add_argument("--metadata-out", required=True)
    parser.add_argument("--max-ppm", type=float, default=20.0)
    parser.add_argument("--seed", type=int, default=101)
    parser.add_argument("--max-files", type=int, default=None)
    return parser.parse_args()


def clean_raw_file(value: Any) -> str:
    raw = str(value).strip()
    if raw.lower().endswith(".raw"):
        raw = raw[:-4]
    return raw


def normalize_modified_sequence(sequence: str) -> str:
    sequence = str(sequence).strip()
    sequence = sequence.strip("_")
    sequence = sequence.replace(".", "")
    return sequence


def read_parenthesized(text: str, start: int) -> tuple[str, int] | tuple[None, None]:
    depth = 0
    for pos in range(start, len(text)):
        char = text[pos]
        if char == "(":
            depth += 1
        elif char == ")":
            depth -= 1
            if depth == 0:
                return text[start + 1 : pos], pos + 1
    return None, None


def convert_modified_sequence(sequence: str, modified_sequence: str, modifications: str) -> tuple[str | None, str | None]:
    sequence = str(sequence).strip().upper()
    modified_sequence = normalize_modified_sequence(modified_sequence)
    modifications = str(modifications or "")

    if not sequence or sequence == "NAN":
        return None, "missing_sequence"

    if not modified_sequence or modified_sequence.upper() == "NAN":
        modified_sequence = sequence

    tokens: list[str] = []
    i = 0
    while i < len(modified_sequence):
        aa = modified_sequence[i]
        if not aa.isalpha() or not aa.isupper():
            return None, f"unexpected_character:{aa}"
        i += 1
        mod = None
        if i < len(modified_sequence) and modified_sequence[i] == "(":
            mod, next_i = read_parenthesized(modified_sequence, i)
            if mod is None or next_i is None:
                return None, "unterminated_modification"
            i = next_i

        if aa == "C":
            tokens.append("C[UNIMOD:4]")
        elif mod is None:
            tokens.append(aa)
        elif "Oxidation" in mod and aa == "M":
            tokens.append("M[UNIMOD:35]")
        elif "Deamidation" in mod and aa in {"N", "Q"}:
            tokens.append(f"{aa}[UNIMOD:7]")
        elif "Phospho" in mod and aa in {"S", "T", "Y"}:
            tokens.append(f"{aa}[UNIMOD:21]")
        elif "Acetyl" in mod and not tokens:
            tokens.append("[UNIMOD:1]")
            tokens.append(aa)
        elif "Carbamidomethyl" in mod and aa == "C":
            tokens.append("C[UNIMOD:4]")
        else:
            return None, f"unsupported_modification:{aa}:{mod}"

    plain = "".join(re.sub(r"\[UNIMOD:\d+\]", "", token) for token in tokens if token.startswith("[") is False)
    if plain != sequence:
        return None, f"sequence_mismatch:{plain}!={sequence}"

    unsupported = [token for token in RESIDUE_SET.tokenize("".join(tokens)) if token not in RESIDUE_SET]
    if unsupported:
        return None, f"unsupported_residue:{','.join(unsupported)}"

    return "".join(tokens), None


def load_labels(path: Path) -> tuple[pd.DataFrame, Counter]:
    labels = pd.read_excel(path)
    required = {"Raw file", "Scan number", "Sequence", "Modified sequence", "Modifications", "Charge", "m/z"}
    missing = sorted(required - set(labels.columns))
    if missing:
        raise ValueError(f"Missing required label columns: {missing}")

    rows = []
    drop_reasons: Counter = Counter()
    for _, row in labels.iterrows():
        try:
            scan_number = int(row["Scan number"])
            charge = int(row["Charge"])
            precursor_mz = float(row["m/z"])
        except Exception:
            drop_reasons["invalid_scan_charge_or_mz"] += 1
            continue

        seq, reason = convert_modified_sequence(row["Sequence"], row["Modified sequence"], row["Modifications"])
        if reason:
            drop_reasons[reason] += 1
            continue

        rows.append(
            {
                "raw_file": clean_raw_file(row["Raw file"]),
                "scan_number": scan_number,
                "sequence": seq,
                "precursor_charge": charge,
                "label_precursor_mz": precursor_mz,
                "retention_time": float(row["Retention time"]) if "Retention time" in labels.columns and not pd.isna(row["Retention time"]) else math.nan,
            }
        )

    out = pd.DataFrame(rows)
    out = out.drop_duplicates(["raw_file", "scan_number", "sequence"]).reset_index(drop=True)
    return out, drop_reasons


def scan_number(spec: dict[str, Any]) -> int | None:
    for key in ("num", "scan", "scanNumber"):
        value = spec.get(key)
        if value is not None:
            try:
                return int(value)
            except Exception:
                pass
    spec_id = str(spec.get("id", ""))
    match = re.search(r"(?:scan=|scanId=|controllerType=\d+\s+controllerNumber=\d+\s+scan=)?(\d+)$", spec_id)
    if match:
        return int(match.group(1))
    return None


def precursor_mz(spec: dict[str, Any]) -> float | None:
    value = spec.get("precursorMz")
    if isinstance(value, list) and value:
        first = value[0]
        if isinstance(first, dict):
            for key in ("precursorMz", "value"):
                if key in first:
                    return float(first[key])
        return float(first)
    if value is not None:
        return float(value)
    return None


def ppm_error(observed: float, expected: float) -> float:
    return (observed - expected) / expected * 1_000_000


def sequence_mz(sequence: str, charge: int) -> float:
    neutral = sum(RESIDUES[token] for token in RESIDUE_SET.tokenize(sequence)) + WATER_MASS
    return neutral / charge + PROTON_MASS_AMU


def iter_matching_spectra(
    mzxml_dir: Path,
    label_map: dict[tuple[str, int], dict[str, Any]],
    max_files: int | None,
    max_ppm: float,
) -> tuple[list[dict[str, Any]], Counter]:
    rows: list[dict[str, Any]] = []
    stats: Counter = Counter()
    mzxml_paths = sorted(mzxml_dir.glob("*.mzXML")) + sorted(mzxml_dir.glob("*.mzxml"))
    if max_files is not None:
        mzxml_paths = mzxml_paths[:max_files]
    if not mzxml_paths:
        raise FileNotFoundError(f"No mzXML files found in {mzxml_dir}")

    needed_raws = {raw for raw, _ in label_map}
    for path in mzxml_paths:
        raw = path.stem
        if raw not in needed_raws:
            continue
        print(f"Reading {path.name}")
        with mzxml.MzXML(str(path)) as reader:
            for spec in reader:
                if int(spec.get("msLevel", spec.get("ms level", 0)) or 0) != 2:
                    continue
                scan = scan_number(spec)
                if scan is None:
                    stats["missing_scan_number"] += 1
                    continue
                label = label_map.get((raw, scan))
                if label is None:
                    stats["unlabelled_ms2"] += 1
                    continue

                mz = precursor_mz(spec) or float(label["label_precursor_mz"])
                charge = int(label["precursor_charge"])
                theoretical_mz = sequence_mz(label["sequence"], charge)
                label_mass_error_ppm = ppm_error(theoretical_mz, float(label["label_precursor_mz"]))
                spectrum_mass_error_ppm = ppm_error(theoretical_mz, mz)
                if abs(label_mass_error_ppm) > max_ppm and abs(spectrum_mass_error_ppm) > max_ppm:
                    stats[f"mass_error_over_{max_ppm:g}ppm"] += 1
                    continue

                mz_array = np.asarray(spec["m/z array"], dtype=float)
                intensity_array = np.asarray(spec["intensity array"], dtype=float)
                if mz_array.size == 0 or intensity_array.size == 0 or mz_array.size != intensity_array.size:
                    stats["empty_or_invalid_peak_array"] += 1
                    continue

                rows.append(
                    {
                        "sequence": label["sequence"],
                        "precursor_mz": float(mz),
                        "precursor_charge": charge,
                        "retention_time": float(label["retention_time"]) if not math.isnan(label["retention_time"]) else 0.0,
                        "mz_array": mz_array.tolist(),
                        "intensity_array": intensity_array.tolist(),
                        "raw_file": raw,
                        "scan_number": scan,
                        "spectrum_id": f"{raw}:{scan}",
                        "label_precursor_mz": float(label["label_precursor_mz"]),
                        "label_mass_error_ppm": float(label_mass_error_ppm),
                        "spectrum_mass_error_ppm": float(spectrum_mass_error_ppm),
                    }
                )
                stats["matched"] += 1
    return rows, stats


def split_by_raw_file(df: pd.DataFrame, seed: int) -> pd.Series:
    raw_files = sorted(df["raw_file"].unique())
    random.Random(seed).shuffle(raw_files)
    n = len(raw_files)
    if n < 3:
        raise ValueError(f"Need at least 3 raw files for train/valid/test split, found {n}")
    n_train = max(1, int(round(n * 0.70)))
    n_valid = max(1, int(round(n * 0.15)))
    if n_train + n_valid >= n:
        n_train = n - 2
        n_valid = 1
    train = set(raw_files[:n_train])
    valid = set(raw_files[n_train : n_train + n_valid])

    def assign(raw: str) -> str:
        if raw in train:
            return "train"
        if raw in valid:
            return "valid"
        return "test"

    return df["raw_file"].map(assign)


def save_partition(df: pd.DataFrame, out_dir: Path, split: str) -> None:
    required = [
        "sequence",
        "precursor_mz",
        "precursor_charge",
        "retention_time",
        "mz_array",
        "intensity_array",
        "raw_file",
        "scan_number",
        "spectrum_id",
    ]
    sdf = SpectrumDataFrame(pl.from_pandas(df[required]), is_annotated=True)
    sdf.save(out_dir, partition=split, name="pxd059455", max_shard_size=10000)


def main() -> None:
    args = parse_args()
    labels, label_drops = load_labels(Path(args.labels))
    if labels.empty:
        raise SystemExit("No valid labels after PTM parsing.")

    label_map = {(row.raw_file, int(row.scan_number)): row._asdict() for row in labels.itertuples(index=False)}
    rows, match_stats = iter_matching_spectra(Path(args.mzxml_dir), label_map, args.max_files, args.max_ppm)
    if not rows:
        raise SystemExit("No labelled spectra matched the PRIDE mzXML files.")

    df = pd.DataFrame(rows)
    df["split"] = split_by_raw_file(df, args.seed)

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    for split in ("train", "valid", "test"):
        part = df[df["split"] == split].reset_index(drop=True)
        if part.empty:
            raise RuntimeError(f"Empty {split} split.")
        save_partition(part, out_dir, split)
        part.drop(columns=["mz_array", "intensity_array"]).to_csv(out_dir / f"{split}_metadata.csv", index=False)

    metadata = {
        "labels_total_after_ptm_parse": int(len(labels)),
        "spectra_total": int(len(df)),
        "split_counts": {k: int(v) for k, v in df["split"].value_counts().sort_index().to_dict().items()},
        "raw_files_by_split": {
            split: sorted(df.loc[df["split"] == split, "raw_file"].unique().tolist())
            for split in ("train", "valid", "test")
        },
        "label_drop_reasons": dict(label_drops),
        "match_stats": dict(match_stats),
        "phospho_label_count": int(df["sequence"].str.contains(r"UNIMOD:21", regex=True).sum()),
    }
    metadata_path = Path(args.metadata_out)
    metadata_path.parent.mkdir(parents=True, exist_ok=True)
    metadata_path.write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    print(json.dumps(metadata, indent=2))


if __name__ == "__main__":
    main()
