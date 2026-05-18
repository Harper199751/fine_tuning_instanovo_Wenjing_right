# Fine-Tuning InstaNovo for Wastewater Bacterial Proteomics

This repository contains a fine-tuning workflow for applying InstaNovo to the
PXD059455 wastewater metaproteomics dataset.

The workflow uses MaxQuant-derived high-confidence PSM labels from
`docs/msms.xlsx`, downloads the corresponding PXD059455 mzXML/mzML peak-list
files from PRIDE, builds InstaNovo SpectrumDataFrame train/validation/test
shards, fine-tunes from the official `instanovo-v1.2.0` checkpoint, and
evaluates the fine-tuned checkpoint on held-out raw files.

Full workflow documentation is in
[`docs/PXD059455_AICHOR_FINETUNE.md`](docs/PXD059455_AICHOR_FINETUNE.md).

## Reference Run

- Train spectra: `831`
- Validation spectra: `57`
- Test spectra: `78`
- Training steps: `306`
- Effective batch size: `64`
- Learning rate: `5e-6`
- Checkpoint selection: best validation loss

Compared with the official InstaNovo v1.2.0 checkpoint on the held-out test
split, the fine-tuned checkpoint improved:

- Amino-acid precision: `0.77529` to `0.79437`
- Amino-acid recall: `0.77605` to `0.79747`
- Amino-acid error rate: `0.14314` to `0.12658`
- Peptide precision/recall: `0.58974` to `0.62821`
- 20 ppm precursor-mass pass count: `66/78` to `67/78`

Reference artifacts are committed under
[`reference_artifacts/pxd059455_instanovo_9623d64d`](reference_artifacts/pxd059455_instanovo_9623d64d).

## Checkpoint

The fine-tuned checkpoint is available from the GitHub release:

```text
https://github.com/BioGeek/fine_tuning_instanovo_Wenjing_right/releases/download/pxd059455-finetune/model_best.ckpt
```

Validated checkpoint SHA256:

```text
3c0630a7f346088650b481398c979c7e264401781b5f8cb6d2c4d7225b76e02e
```

Reproduce the held-out test metrics with:

```bash
scripts/reproduce_release_checkpoint.sh
```

## Run The Workflow

The workflow is containerized. The reference run was executed on
[AIchor](https://aichor.ai/) using an H100 GPU, but the same container should be
portable to other GPU environments with the same dependencies.

```bash
aichor submit local experiment --repo-dir . --message "PXD059455 InstaNovo finetune" --project-name "DTU Denovo Sequencing"
```
