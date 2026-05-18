# PXD059455 InstaNovo Fine-Tuning

This workflow fine-tunes InstaNovo on the PXD059455 wastewater metaproteomics
dataset using the fine-tuning approach described by InstaNovo-P, adapted to the
labels and peak lists available for this dataset. It builds PTM-aware labels,
uses the PRIDE peak lists for matched spectra, trains from the official
InstaNovo v1.2.0 checkpoint, and evaluates the fine-tuned checkpoint against the
official checkpoint on held-out raw files.

Compared with the upstream
[fine_tuning_instanovo_Wenjing_right](https://github.com/Harper199751/fine_tuning_instanovo_Wenjing_right)
repository, this branch adds a reproducible data download, SpectrumDataFrame
construction, small-dataset fine-tuning schedule, held-out evaluation, and
artifact upload path.

## Inputs

- `docs/msms.xlsx`: labelled PSM table used to select raw files and build
  peptide targets.
- PRIDE project `PXD059455`: metadata, checksums, and mzXML/mzML peak lists are
  downloaded inside the container.
- InstaNovo model `instanovo-v1.2.0`: downloaded at runtime and converted to a
  trainer-compatible resume checkpoint.

The workflow converts MaxQuant-style modified peptide annotations to InstaNovo
residue and UNIMOD tokens, verifies PRIDE downloads against `checksum.txt`, and
splits data by raw file into train, validation, and test partitions.

## Submit

[AIchor](https://aichor.ai/) is used here as the GPU execution platform.

```bash
aichor submit local experiment --repo-dir . --message "proper PXD059455 InstaNovo finetune trainer-step epochs" --project-name "DTU Denovo Sequencing"
```

The default AIchor manifest requests one
`NVIDIA-H100-80GB-HBM3-MIG-3g.40gb` GPU slice with 16 CPU cores and 160 GiB
memory.

Reference successful experiment:
`9623d64d-c085-42de-8c73-e43f47ccbf55`.

Reference outputs from this run are committed under
`reference_artifacts/pxd059455_instanovo_9623d64d/`.

## Pipeline

1. `scripts/01_prepare_instanovo_checkpoint.py` downloads `instanovo-v1.2.0`
   and writes a trainer-compatible resume checkpoint.
2. `scripts/02_download_pxd059455.py` downloads PXD059455 metadata and the
   mzXML/mzML files whose raw-file names appear in `docs/msms.xlsx`.
3. `scripts/03_build_pxd059455_sdf.py` maps labels to PRIDE scans, encodes
   PTMs as UNIMOD tokens, filters precursor mass mismatches, and writes
   train/valid/test SpectrumDataFrame parquet shards.
4. `scripts/04_make_training_overrides.py` computes training steps and the
   step-based unfreezing schedule from the prepared train split.
5. `instanovo transformer train` fine-tunes with `configs/pxd059455`.
6. `instanovo transformer predict --evaluation` evaluates both the official
   and fine-tuned checkpoints on the held-out test split.
7. `scripts/05_evaluate_pxd059455.py` writes summary metrics and a comparison
   table.
8. `scripts/06_upload_aichor_artifacts.py` uploads selected local outputs when
   AIchor output storage is available.

## Training Defaults

- Base checkpoint: `instanovo-v1.2.0`.
- Effective batch size: 64 (`train_batch_size=16`, `grad_accumulation=4`).
- Epoch target: 6, converted to trainer steps from the built training split.
- For the current split: 831 train, 57 validation, and 78 test spectra.
- Current schedule: 51 trainer steps per epoch, 306 trainer steps total.
- Warmup: 5% of total steps, minimum 5 steps.
- Learning rate: `5e-6`, cosine schedule.
- Weight decay: `1e-6`.
- Validation/checkpoint interval: once per computed training epoch.
- Fine-tuning schedule: head from step 0, decoder after one computed training
  epoch, full model after two computed training epochs.
- Checkpoint selection: best validation loss.
- Evaluation: greedy decoding with phospho residues suppressed because this
  label set contains no phosphorylation annotations.

## Result

The reference run trained for 306 trainer steps, validated every 51 steps, and
evaluated on 78 held-out spectra. Validation loss decreased from `0.45504`
before training to `0.32188` at the final checkpoint.

Compared with the official InstaNovo v1.2.0 checkpoint on the held-out test
split, the fine-tuned checkpoint improved:

- Amino-acid precision: `0.77529` to `0.79437`.
- Amino-acid recall: `0.77605` to `0.79747`.
- Amino-acid error rate: `0.14314` to `0.12658`.
- Peptide precision/recall: `0.58974` to `0.62821`.
- 20 ppm precursor-mass pass count: `66/78` to `67/78`.

No phospho predictions were emitted.

## Smoke Test Knobs

These environment variables can be set in the container or manifest for a
short diagnostic run:

```bash
PXD059455_DOWNLOAD_LIMIT=2
PXD059455_BUILD_MAX_FILES=2
PXD059455_SAMPLE_REGEX='MP_CT17052024'
```

Do not use these variables for a production fine-tuning run.

## Outputs

The job writes local artifacts under `${INSTANOVO_WORKDIR:-/tmp/instanovo_pxd059455}`:

- `processed/dataset_metadata.json`
- `processed/sdf/`
- `models/pxd059455_instanovo/model_best.ckpt`
- `tensorboard/`
- `predictions/official_instanovo_v1.2.0_test.csv`
- `predictions/pxd059455_finetuned_test.csv`
- `reports/summary_official_vs_finetuned.csv`
- `reports/comparison_official_vs_finetuned.csv`
- `reports/run_report.json`

When `AICHOR_OUTPUT_PATH` is present, the entrypoint uploads these artifacts to
the AIchor output bucket at the end of the run.
