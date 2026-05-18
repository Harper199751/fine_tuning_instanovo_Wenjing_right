#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ARTIFACT_DIR="${ROOT_DIR}/reference_artifacts/pxd059455_instanovo_9623d64d"
WORKDIR="${PXD059455_REPRO_WORKDIR:-/tmp/pxd059455_release_repro}"
CHECKPOINT_URL="${PXD059455_CHECKPOINT_URL:-https://github.com/BioGeek/fine_tuning_instanovo_Wenjing_right/releases/download/pxd059455-finetune/model_best.ckpt}"
PYTHON_BIN="${PYTHON:-python}"
INSTANOVO_BIN="${INSTANOVO:-instanovo}"

CHECKPOINT_PATH="${WORKDIR}/model_best.ckpt"
OFFICIAL_COPY_PATH="${WORKDIR}/official_instanovo_v1.2.0_test.csv"
PREDICTION_PATH="${WORKDIR}/pxd059455_finetuned_release_test.csv"
SUMMARY_PATH="${WORKDIR}/summary_official_vs_release.csv"
COMPARISON_PATH="${WORKDIR}/comparison_official_vs_release.csv"
REPORT_PATH="${WORKDIR}/run_report_release.json"

mkdir -p "${WORKDIR}"

if [[ ! -s "${CHECKPOINT_PATH}" ]]; then
  curl -L --fail --retry 3 --retry-delay 5 -o "${CHECKPOINT_PATH}" "${CHECKPOINT_URL}"
fi

echo "Checkpoint: ${CHECKPOINT_PATH}"
sha256sum "${CHECKPOINT_PATH}"
cp "${ARTIFACT_DIR}/predictions/official_instanovo_v1.2.0_test.csv" "${OFFICIAL_COPY_PATH}"

ROOT_DIR="${ROOT_DIR}" "${PYTHON_BIN}" - <<'PY'
import os
import shutil
from pathlib import Path

import instanovo.utils

root = Path(os.environ["ROOT_DIR"])
src = root / "configs" / "pxd059455"
dst = Path(instanovo.utils.__file__).parent / "configs" / "pxd059455"
if dst.exists() or dst.is_symlink():
    if dst.is_symlink() or dst.is_file():
        dst.unlink()
    else:
        shutil.rmtree(dst)
dst.parent.mkdir(parents=True, exist_ok=True)
shutil.copytree(src, dst)
print(f"Installed {src} -> {dst}")
PY

"${INSTANOVO_BIN}" transformer predict \
  --evaluation \
  --data-path "${ARTIFACT_DIR}/sdf/*test*.parquet" \
  --output-path "${PREDICTION_PATH}" \
  --instanovo-model "${CHECKPOINT_PATH}" \
  --config-path configs/pxd059455 \
  --config-name inference_eval \
  data_path="${ARTIFACT_DIR}/sdf/*test*.parquet" \
  output_path="${PREDICTION_PATH}" \
  instanovo_model="${CHECKPOINT_PATH}" \
  batch_size=64 \
  num_workers="${PXD059455_REPRO_NUM_WORKERS:-8}"

"${PYTHON_BIN}" "${ROOT_DIR}/scripts/05_evaluate_pxd059455.py" \
  --official "${OFFICIAL_COPY_PATH}" \
  --finetuned "${PREDICTION_PATH}" \
  --summary-out "${SUMMARY_PATH}" \
  --comparison-out "${COMPARISON_PATH}" \
  --json-out "${REPORT_PATH}"

REFERENCE_REPORT="${ARTIFACT_DIR}/reports/run_report.json" \
REPRO_REPORT="${REPORT_PATH}" \
"${PYTHON_BIN}" - <<'PY'
import json
import math
import os
import sys
from pathlib import Path

reference = json.loads(Path(os.environ["REFERENCE_REPORT"]).read_text(encoding="utf-8"))
reproduced = json.loads(Path(os.environ["REPRO_REPORT"]).read_text(encoding="utf-8"))

keys = [
    "aa_precision",
    "aa_recall",
    "aa_error_rate",
    "peptide_precision",
    "peptide_recall",
    "pass_20ppm_count",
    "pass_20ppm_rate",
    "phospho_prediction_count",
]

failed = False
for key in keys:
    expected = reference["finetuned"][key]
    observed = reproduced["finetuned"][key]
    if isinstance(expected, float):
        ok = math.isclose(expected, observed, rel_tol=0.0, abs_tol=1e-6)
    else:
        ok = expected == observed
    status = "OK" if ok else "MISMATCH"
    print(f"{status}: {key}: expected={expected} observed={observed}")
    failed = failed or not ok

if failed:
    print("Release checkpoint did not reproduce the committed reference metrics.", file=sys.stderr)
    sys.exit(3)

print("Release checkpoint reproduced the committed reference metrics.")
PY
