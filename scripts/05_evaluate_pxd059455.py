#!/usr/bin/env python
"""Summarise InstaNovo prediction CSVs for PXD059455."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

from instanovo.utils.metrics import Metrics
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


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--official", required=True)
    parser.add_argument("--finetuned", required=True)
    parser.add_argument("--summary-out", required=True)
    parser.add_argument("--comparison-out", required=True)
    parser.add_argument("--json-out", required=True)
    return parser.parse_args()


def clean_sequence(value: object) -> str:
    if value is None or pd.isna(value):
        return ""
    return str(value)


def summarise(name: str, path: Path, metrics: Metrics) -> dict[str, float | int | str]:
    df = pd.read_csv(path)
    targets = [clean_sequence(x) for x in df["targets"]]
    predictions = [clean_sequence(x) for x in df["predictions"]]
    aa_precision, aa_recall, peptide_recall, peptide_precision = metrics.compute_precision_recall(targets, predictions)
    aa_error_rate = metrics.compute_aa_er(targets, predictions)

    pass_20 = []
    delta_ppm = []
    for row in df.itertuples(index=False):
        ok, deltas = metrics.matches_precursor(
            clean_sequence(getattr(row, "predictions")),
            float(getattr(row, "precursor_mz")),
            int(getattr(row, "precursor_charge")),
            prec_tol=20,
        )
        pass_20.append(ok)
        delta_ppm.append(min(deltas, key=lambda x: abs(x)) if deltas else float("nan"))

    df["delta_mass_ppm_recomputed"] = delta_ppm
    df["pass_20ppm_recomputed"] = pass_20
    df.to_csv(path, index=False)

    return {
        "model": name,
        "n_spectra": int(len(df)),
        "aa_precision": float(aa_precision),
        "aa_recall": float(aa_recall),
        "aa_error_rate": float(aa_error_rate),
        "peptide_precision": float(peptide_precision),
        "peptide_recall": float(peptide_recall),
        "pass_20ppm_count": int(sum(pass_20)),
        "pass_20ppm_rate": float(sum(pass_20) / len(pass_20)) if pass_20 else 0.0,
        "phospho_prediction_count": int(pd.Series(predictions).str.contains("UNIMOD:21", regex=False).sum()),
    }


def main() -> None:
    args = parse_args()
    residue_set = ResidueSet(RESIDUES)
    metrics = Metrics(residue_set, isotope_error_range=[0, 1])

    official = summarise("official_instanovo_v1.2.0", Path(args.official), metrics)
    finetuned = summarise("pxd059455_finetuned", Path(args.finetuned), metrics)
    summary = pd.DataFrame([official, finetuned])
    summary.to_csv(args.summary_out, index=False)

    official_df = pd.read_csv(args.official)
    finetuned_df = pd.read_csv(args.finetuned)
    join_cols = [col for col in ["spectrum_id", "scan_number", "precursor_mz", "precursor_charge", "targets"] if col in official_df.columns]
    comparison = official_df[join_cols + ["predictions", "pass_20ppm_recomputed"]].merge(
        finetuned_df[join_cols + ["predictions", "pass_20ppm_recomputed"]],
        on=join_cols,
        suffixes=("_official", "_finetuned"),
        how="outer",
    )
    comparison.to_csv(args.comparison_out, index=False)

    report = {
        "official": official,
        "finetuned": finetuned,
        "accepted": bool(
            finetuned["peptide_precision"] >= official["peptide_precision"] * 0.8
            and (
                finetuned["peptide_recall"] > official["peptide_recall"]
                or finetuned["aa_recall"] > official["aa_recall"]
                or finetuned["pass_20ppm_rate"] > official["pass_20ppm_rate"]
            )
        ),
    }
    Path(args.json_out).write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()

