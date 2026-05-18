# PXD059455 Aichor InstaNovo Fine-Tune

This branch replaces the failed ultra-light fine-tune with an Aichor GPU job.
The failed run used plain peptide labels, froze almost the whole model, used
`learning_rate=1e-7`, and trained for only 10 steps. This workflow builds
PTM-aware labels, downloads PRIDE mzXML spectra inside the container, trains
from the InstaNovo v1.2.0 checkpoint, and evaluates on held-out raw files.

## Submit

```bash
aichor submit local experiment --repo-dir . --message "proper PXD059455 InstaNovo finetune reduced epochs" --project-name "DTU Denovo Sequencing"
```

The default Aichor manifest requests one
`NVIDIA-H100-80GB-HBM3-MIG-3g.40gb` GPU slice with 16 CPU cores and 160 GiB
memory.

Current submitted experiment: `f126949b-7d2e-4ce5-876c-2594c910a122`. The
earlier experiments `03fea81f-ef4d-42c6-8a97-07fc4bcbb4c5` and
`3dccf233-4075-461c-820d-abfe651cd3cc` were cancelled before the final run:
the first because its step floor would have caused too many passes over this
small label set, the second because it still requested an unavailable A100.

## What Runs In The Container

1. `scripts/09_prepare_instanovo_checkpoint.py` downloads `instanovo-v1.2.0`
   and writes a trainer-compatible resume checkpoint.
2. `scripts/10_download_pxd059455.py` downloads PXD059455 metadata and the
   mzXML files whose raw-file names appear in `docs/msms.xlsx`. Vendor `.raw`
   files are skipped by default.
3. `scripts/11_build_pxd059455_sdf.py` maps local `docs/msms.xlsx` labels to
   PRIDE mzXML scans, encodes PTMs as UNIMOD tokens, filters bad precursor
   mass matches, and saves train/valid/test SpectrumDataFrame shards.
4. `instanovo transformer train` fine-tunes with `configs/pxd059455`.
5. `instanovo transformer predict --evaluation` evaluates the official and
   fine-tuned checkpoints on the held-out test split.
6. `scripts/13_evaluate_pxd059455.py` writes summary metrics and a comparison
   table.

## Defaults

- Effective batch size: 64 (`train_batch_size=16`, `grad_accumulation=4`).
- Epoch target: 6, converted to steps from the built training split.
- Minimum training steps: 0; no artificial floor is used on this small dataset.
- Warmup: 5% of total steps, minimum 5 steps.
- Learning rate: `5e-6`, cosine schedule.
- Validation/checkpoint interval: once per training epoch.
- Fine-tuning schedule: head from epoch 0, decoder from epoch 1, full model
  from epoch 2.
- Evaluation uses greedy decoding because InstaNovo 1.2.2 applies
  `suppressed_residues` only on the greedy path; this prevents the previous
  phospho-token collapse on a non-phospho dataset.

## Overfitting Guard

The local label table currently parses to 967 usable labels across 19 raw
files. The training script computes optimizer steps from the final train split
instead of using a fixed step count. For the expected split size, this is about
66 optimizer steps total, with validation and checkpointing once per epoch.
The best checkpoint is selected by validation loss and the final report still
compares against the official InstaNovo checkpoint on held-out raw files.

## Smoke Test Knobs

These environment variables can be set in the container or manifest for a
short diagnostic run:

```bash
PXD059455_DOWNLOAD_LIMIT=2
PXD059455_BUILD_MAX_FILES=2
PXD059455_SAMPLE_REGEX='MP_CT17052024'
```

Do not use these variables for the final run.

## Outputs

The job writes local artifacts under `${INSTANOVO_WORKDIR:-/tmp/instanovo_pxd059455}`:

- `processed/dataset_metadata.json`
- `processed/sdf/`
- `models/pxd059455_instanovo/model_best.ckpt`
- `predictions/official_instanovo_v1.2.0_test.csv`
- `predictions/pxd059455_finetuned_test.csv`
- `reports/summary_official_vs_finetuned.csv`
- `reports/comparison_official_vs_finetuned.csv`
- `reports/run_report.json`

When `AICHOR_OUTPUT_PATH` is present, the entrypoint uploads those artifacts to
the Aichor output bucket at the end of the run.
