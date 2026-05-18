# PXD059455 InstaNovo Reference Artifacts

Reference artifacts from the successful PXD059455 InstaNovo fine-tuning run.

- AIchor project: `2e6da747-d6d3-4f62-a056-b5b13d8db3fc`
- AIchor experiment: `9623d64d-c085-42de-8c73-e43f47ccbf55`
- Commit message: `proper PXD059455 InstaNovo finetune trainer-step epochs`
- Model baseline: `instanovo-v1.2.0`

## Contents

- `dataset_metadata.json`: split counts, raw files by split, and matching
  statistics.
- `sdf/`: processed InstaNovo SpectrumDataFrame parquet shards and split
  metadata.
- `predictions/`: prediction CSVs for the official and fine-tuned checkpoints
  on the held-out test split.
- `reports/`: summary metrics, per-spectrum comparison table, and JSON report.
- `tensorboard/`: TensorBoard event file from the fine-tuning run.
- `SHA256SUMS`: checksums for the files in this reference bundle.

## Result Summary

Held-out test split: 78 spectra.

| Metric | Official InstaNovo v1.2.0 | Fine-tuned |
| --- | ---: | ---: |
| AA precision | 0.77529 | 0.79437 |
| AA recall | 0.77605 | 0.79747 |
| AA error rate | 0.14314 | 0.12658 |
| Peptide precision | 0.58974 | 0.62821 |
| Peptide recall | 0.58974 | 0.62821 |
| 20 ppm pass count | 66/78 | 67/78 |

The trained checkpoint is not committed to Git because it is a large binary
artifact. The public checkpoint location is:

```text
https://github.com/BioGeek/fine_tuning_instanovo_Wenjing_right/releases/download/pxd059455-finetune/model_best.ckpt
```

Use `scripts/reproduce_release_checkpoint.sh` from the repository root to
download that checkpoint, run it on the committed held-out test split, and
compare the reproduced metrics with `reports/run_report.json`.

Validated release checkpoint SHA256:
`3c0630a7f346088650b481398c979c7e264401781b5f8cb6d2c4d7225b76e02e`.
Running `scripts/reproduce_release_checkpoint.sh` against this release asset
reproduces the metrics in `reports/run_report.json`.
