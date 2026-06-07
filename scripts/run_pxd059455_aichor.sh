#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="/app"
WORKDIR="${INSTANOVO_WORKDIR:-/tmp/instanovo_pxd059455}"
RAW_DIR="${WORKDIR}/raw/PXD059455"
PROCESSED_DIR="${WORKDIR}/processed"
SDF_DIR="${PROCESSED_DIR}/sdf"
CHECKPOINT_DIR="${WORKDIR}/checkpoints"
MODEL_DIR="${WORKDIR}/models/pxd059455_instanovo"
PRED_DIR="${WORKDIR}/predictions"
REPORT_DIR="${WORKDIR}/reports"
OVERRIDE_FILE="${WORKDIR}/training_overrides.txt"
TENSORBOARD_DIR="${WORKDIR}/tensorboard"

mkdir -p "${RAW_DIR}" "${SDF_DIR}" "${CHECKPOINT_DIR}" "${MODEL_DIR}" "${PRED_DIR}" "${REPORT_DIR}" "${TENSORBOARD_DIR}"
cd "${ROOT_DIR}"

echo "=== Runtime ==="
date -Iseconds
python - <<'PY'
import torch, instanovo
print("instanovo", getattr(instanovo, "__version__", "unknown"))
print("torch", torch.__version__)
print("cuda_available", torch.cuda.is_available())
print("cuda_device_count", torch.cuda.device_count())
if torch.cuda.is_available():
    print("cuda_device", torch.cuda.get_device_name(0))
PY
nvidia-smi || true

if ! python - <<'PY'
import torch
raise SystemExit(0 if torch.cuda.is_available() else 1)
PY
then
  echo "CUDA is required for the full fine-tune; refusing to run on CPU." >&2
  exit 2
fi

echo "=== Preparing pretrained checkpoint ==="
python scripts/01_prepare_instanovo_checkpoint.py \
  --model-id instanovo-v1.2.0 \
  --output "${CHECKPOINT_DIR}/instanovo-v1.2.0-train-resume.ckpt"

echo "=== Downloading PRIDE PXD059455 mzXML data ==="
DOWNLOAD_ARGS=(--out-dir "${RAW_DIR}" --labels docs/msms.xlsx)
if [[ -n "${PXD059455_DOWNLOAD_LIMIT:-}" ]]; then
  DOWNLOAD_ARGS+=(--limit "${PXD059455_DOWNLOAD_LIMIT}")
fi
if [[ -n "${PXD059455_SAMPLE_REGEX:-}" ]]; then
  DOWNLOAD_ARGS+=(--sample-regex "${PXD059455_SAMPLE_REGEX}")
fi
python scripts/02_download_pxd059455.py "${DOWNLOAD_ARGS[@]}"

echo "=== Building InstaNovo SpectrumDataFrame splits ==="
BUILD_ARGS=(
  --labels docs/msms.xlsx
  --mzxml-dir "${RAW_DIR}"
  --out-dir "${SDF_DIR}"
  --metadata-out "${PROCESSED_DIR}/dataset_metadata.json"
  --max-ppm 20
  --seed 101
)
if [[ -n "${PXD059455_BUILD_MAX_FILES:-}" ]]; then
  BUILD_ARGS+=(--max-files "${PXD059455_BUILD_MAX_FILES}")
fi
python scripts/03_build_pxd059455_sdf.py "${BUILD_ARGS[@]}"

echo "=== Computing training-step overrides ==="
python scripts/04_make_training_overrides.py \
  --metadata "${PROCESSED_DIR}/dataset_metadata.json" \
  --train-batch-size 16 \
  --grad-accumulation 4 \
  --epochs 6 \
  --min-steps 0 \
  --out "${OVERRIDE_FILE}" \
  --finetune-config "${ROOT_DIR}/configs/pxd059455/finetune/pxd059455.yaml"
mapfile -t TRAIN_OVERRIDES < "${OVERRIDE_FILE}"

echo "=== Installing InstaNovo CLI configs ==="
python - <<'PY'
import shutil
from pathlib import Path

import instanovo.utils

src = Path("/app/configs/pxd059455")
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

echo "=== Training PXD059455 fine-tuned InstaNovo ==="
export INSTANOVO_WORKDIR="${WORKDIR}"
if [[ -n "${AICHOR_LOGS_PATH:-}" ]]; then
  echo "Disabling InstaNovo's AIchor TensorBoard hook; local TensorBoard logs remain under ${TENSORBOARD_DIR}."
  unset AICHOR_LOGS_PATH
fi
instanovo transformer train \
  --config-path configs/pxd059455 \
  --config-name instanovo_finetune \
  "${TRAIN_OVERRIDES[@]}" \
  dataset.train_path="${SDF_DIR}/*train*.parquet" \
  dataset.valid_path="${SDF_DIR}/*valid*.parquet" \
  model_save_folder_path="${MODEL_DIR}" \
  resume_checkpoint_path="${CHECKPOINT_DIR}/instanovo-v1.2.0-train-resume.ckpt" \
  use_neptune=false

echo "=== Predicting held-out test split with official model ==="
instanovo transformer predict \
  --evaluation \
  --data-path "${SDF_DIR}/*test*.parquet" \
  --output-path "${PRED_DIR}/official_instanovo_v1.2.0_test.csv" \
  --instanovo-model instanovo-v1.2.0 \
  --config-path configs/pxd059455 \
  --config-name inference_eval \
  data_path="${SDF_DIR}/*test*.parquet" \
  output_path="${PRED_DIR}/official_instanovo_v1.2.0_test.csv" \
  instanovo_model=instanovo-v1.2.0

echo "=== Predicting held-out test split with fine-tuned model ==="
instanovo transformer predict \
  --evaluation \
  --data-path "${SDF_DIR}/*test*.parquet" \
  --output-path "${PRED_DIR}/pxd059455_finetuned_test.csv" \
  --instanovo-model "${MODEL_DIR}/model_best.ckpt" \
  --config-path configs/pxd059455 \
  --config-name inference_eval \
  data_path="${SDF_DIR}/*test*.parquet" \
  output_path="${PRED_DIR}/pxd059455_finetuned_test.csv" \
  instanovo_model="${MODEL_DIR}/model_best.ckpt"

echo "=== Evaluating ==="
python scripts/05_evaluate_pxd059455.py \
  --official "${PRED_DIR}/official_instanovo_v1.2.0_test.csv" \
  --finetuned "${PRED_DIR}/pxd059455_finetuned_test.csv" \
  --summary-out "${REPORT_DIR}/summary_official_vs_finetuned.csv" \
  --comparison-out "${REPORT_DIR}/comparison_official_vs_finetuned.csv" \
  --json-out "${REPORT_DIR}/run_report.json"

echo "=== Uploading artifacts if Aichor output storage is available ==="
python scripts/06_upload_aichor_artifacts.py \
  "${PROCESSED_DIR}/dataset_metadata.json" \
  "${SDF_DIR}" \
  "${MODEL_DIR}" \
  "${TENSORBOARD_DIR}" \
  "${PRED_DIR}" \
  "${REPORT_DIR}" || true

echo "=== Done ==="
date -Iseconds
