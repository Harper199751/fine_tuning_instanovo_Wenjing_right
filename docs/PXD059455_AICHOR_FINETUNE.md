# PXD059455 InstaNovo Fine-Tuning

This workflow fine-tunes InstaNovo on the PXD059455 wastewater metaproteomics
dataset using the fine-tuning approach described by InstaNovo-P, adapted to the
MaxQuant-derived PSM labels and public PRIDE peak-list files available for this
dataset. It converts the labels from `docs/msms.xlsx` into PTM-aware InstaNovo
residue tokens, downloads the corresponding PRIDE mzXML/mzML peak-list files,
matches labelled scans back to those spectra, trains from the official InstaNovo
v1.2.0 checkpoint, and evaluates the fine-tuned checkpoint against the official
checkpoint on held-out raw files.

Compared with the upstream
[fine_tuning_instanovo_Wenjing_right](https://github.com/Harper199751/fine_tuning_instanovo_Wenjing_right)
repository, this branch adds a reproducible data download, SpectrumDataFrame
construction, raw-file-level split with traceable held-out evaluation,
small-dataset fine-tuning schedule, and artifact upload path.

## Inputs

- `docs/msms.xlsx`: MaxQuant-derived high-confidence PSM table used as the
  label source and to select the raw files needed for this dataset.
- PRIDE project `PXD059455`: metadata, checksums, and mzXML/mzML peak-list files
  are downloaded inside the container as the reproducible source of spectra.
- InstaNovo model `instanovo-v1.2.0`: downloaded at runtime and converted to a
  trainer-compatible resume checkpoint.

The workflow treats `docs/msms.xlsx` as the label source and the PRIDE
mzXML/mzML files as the spectrum source. It converts MaxQuant-style modified
peptide annotations to InstaNovo residue and UNIMOD tokens, verifies PRIDE
downloads against `checksum.txt`, matches labelled scans back to the downloaded
peak-list files, and splits data by raw file into train, validation, and test
partitions.

## Execution Environment

The workflow is containerized and should be portable to GPU environments with
the same dependencies. The reference run used one H100-class GPU with 16 CPU
cores and 160 GiB memory.

Reference outputs from this run are committed under
`reference_artifacts/pxd059455_instanovo_9623d64d/`.

## Pipeline

1. `scripts/01_prepare_instanovo_checkpoint.py` downloads `instanovo-v1.2.0`
   and writes a trainer-compatible resume checkpoint.
2. `scripts/02_download_pxd059455.py` downloads PXD059455 metadata and the
   mzXML/mzML peak-list files whose raw-file names appear in `docs/msms.xlsx`.
3. `scripts/03_build_pxd059455_sdf.py` maps the MaxQuant-derived labels from
   `docs/msms.xlsx` to scans in the PRIDE peak-list files, encodes PTMs as
   UNIMOD tokens, filters precursor mass mismatches, and writes train/valid/test
   SpectrumDataFrame parquet shards.
4. `scripts/04_make_training_overrides.py` computes training steps and the
   step-based unfreezing schedule from the prepared train split.
5. `instanovo transformer train` fine-tunes with `configs/pxd059455`.
6. `instanovo transformer predict --evaluation` evaluates both the official
   and fine-tuned checkpoints on the held-out test split.
7. `scripts/05_evaluate_pxd059455.py` writes summary metrics and a comparison
   table.
8. `scripts/06_upload_aichor_artifacts.py` uploads selected local outputs when
   compatible output storage is available.

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
- Fine-tuning schedule (per-layer encoder-first gradual unfreezing, following the
  InstaNovo-P manuscript): head + embeddings first, then the encoder layers from the
  top (8) down to (0), then the decoder layers from the top down (encoder fully
  before decoder). Phase start steps are placed at fixed fractions of the total
  training steps; the manuscript spans ~10 transition epochs on a much larger
  corpus, so the same relative ordering is scaled to this run's step budget.
- Checkpoint selection: best validation loss.
- Evaluation: greedy decoding with phospho residues suppressed because this
  label set contains no phosphorylation annotations.

## Result

The reference run trained for 306 trainer steps, validated every 51 steps, and
evaluated on 78 held-out spectra. Validation loss decreased from `0.44818`
before training to `0.32243` at the final checkpoint.

Compared with the official InstaNovo v1.2.0 checkpoint on the held-out test
split, the fine-tuned checkpoint improved:

- Amino-acid precision: `0.77529` to `0.80758`.
- Amino-acid recall: `0.77605` to `0.80915`.
- Amino-acid error rate: `0.14314` to `0.11685`.
- Peptide precision/recall: `0.58974` to `0.62821`.
- 20 ppm precursor-mass pass count: `66/78` to `67/78`.

No phospho predictions were emitted. These numbers are from a local re-run with
the per-layer encoder-first schedule (the small test set means the peptide-level
and 20 ppm deltas are only a few spectra; the validation-loss drop is the
clearer signal).

## Dataset Size

This is a small supervised fine-tuning set. The reference split contains `831`
training spectra, `57` validation spectra, and `78` test spectra, so the result
should be interpreted as a proof of concept for this PXD059455 fine-tuning
workflow rather than as a fully powered domain adaptation run. A more
substantial fine-tuning effort would require many more labelled spectra,
ideally covering more raw files, organisms, peptide classes, charge states, and
relevant PTMs.

## Reproduce From Checkpoint

The fine-tuned checkpoint is too large to commit directly to Git. The public
checkpoint location is:

```text
https://github.com/BioGeek/fine_tuning_instanovo_Wenjing_right/releases/download/pxd059455-finetune/model_best.ckpt
```

Run the reproducibility check against the committed held-out test artifacts:

```bash
scripts/reproduce_release_checkpoint.sh
```

The script downloads `model_best.ckpt`, installs the local `configs/pxd059455`
Hydra config into the active InstaNovo environment, runs
`instanovo transformer predict --evaluation` on the committed test
SpectrumDataFrame, and compares the reproduced metrics with
`reference_artifacts/pxd059455_instanovo_9623d64d/reports/run_report.json`.

Use these environment variables when the active shell does not already resolve
the correct Python and InstaNovo executables:

```bash
PYTHON=/path/to/python \
INSTANOVO=/path/to/instanovo \
PXD059455_REPRO_WORKDIR=/tmp/pxd059455_release_repro \
scripts/reproduce_release_checkpoint.sh
```

Validated release checkpoint SHA256:
`3c0630a7f346088650b481398c979c7e264401781b5f8cb6d2c4d7225b76e02e`.
Running `scripts/reproduce_release_checkpoint.sh` against this release asset
reproduces the final reference metrics above.

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
the configured output bucket at the end of the run.
