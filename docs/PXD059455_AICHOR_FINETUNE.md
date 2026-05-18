# PXD059455 InstaNovo Fine-Tune

This branch replaces the previous ultra-light fine-tune attempt with a
proper InstaNovo fine-tuning workflow for PXD059455. The failed run used plain
peptide labels, froze almost the whole model, used `learning_rate=1e-7`, and
trained for only 10 steps. The new workflow builds PTM-aware labels, uses the
PRIDE peak lists for the matched spectra, trains from the InstaNovo v1.2.0
checkpoint, and evaluates against the official checkpoint on held-out raw
files.

## Changes From Upstream

Compared with the upstream
[fine_tuning_instanovo_Wenjing_right](https://github.com/Harper199751/fine_tuning_instanovo_Wenjing_right)
repository, this branch replaces the previous ultra-light training attempt
with a fine-tuning workflow based on the InstaNovo-P publication and reference
repository, adapted for this wastewater dataset. The main changes are:

- PRIDE PXD059455 download and checksum verification for the labelled raw
  files in `docs/msms.xlsx`.
- Conversion from MaxQuant-style peptide annotations to InstaNovo residue and
  UNIMOD tokens.
- Content sniffing for PRIDE peak lists whose filenames end in `.mzXML` but
  whose XML root is mzML.
- Raw-file-level train/valid/test splits saved as InstaNovo
  SpectrumDataFrame parquet shards.
- A small-dataset fine-tuning schedule with validation/checkpointing once per
  epoch and no artificial step floor.
- A held-out comparison report for official InstaNovo v1.2.0 versus the
  PXD059455 fine-tuned checkpoint.

## Submit

[AIchor](https://aichor.ai/) is used here only as the available GPU execution platform.

```bash
aichor submit local experiment --repo-dir . --message "proper PXD059455 InstaNovo finetune trainer-step epochs" --project-name "DTU Denovo Sequencing"
```

The default AIchor manifest requests one
`NVIDIA-H100-80GB-HBM3-MIG-3g.40gb` GPU slice with 16 CPU cores and 160 GiB
memory.

Current successful experiment: `9623d64d-c085-42de-8c73-e43f47ccbf55`. Earlier
experiments were superseded before the final run: `03fea81f-ef4d-42c6-8a97-07fc4bcbb4c5`
had an excessive step floor, `3dccf233-4075-461c-820d-abfe651cd3cc` still
requested an unavailable A100, and `f126949b-7d2e-4ce5-876c-2594c910a122`
failed during checkpoint preparation because InstaNovo returned a plain dict
config in the container. `f55be93a-b5c2-4b3d-ad68-ff2c4fe08b6f` failed because
the downloader incorrectly treated PRIDE file accessions as SHA256 checksums;
the downloader now verifies files against the SHA1 values in `checksum.txt`.
`a5deb800-cc65-4f7b-9acc-4c15b506714e` failed because PRIDE names these peak
lists `.mzXML` even though their XML root is mzML; the builder now sniffs the
file content and chooses the mzML parser for those files.
`3810b0a8-cf70-4f97-9295-e3587aaaa466` failed because the InstaNovo CLI
resolves relative config paths under its installed package directory; the
entrypoint now installs `configs/pxd059455` into the package config tree before
training. `d55567ca-a917-4e5b-b02d-ed6f6e3123f7` failed because InstaNovo
forces TensorBoard logs to `AICHOR_LOGS_PATH` when that variable is present,
which triggered an object-store `SignatureDoesNotMatch` error before training;
the manifest now disables AIchor TensorBoard integration, and the entrypoint
keeps TensorBoard event files local before uploading them with the other run
artifacts. `1edb8cb5-19cf-4e75-82cd-c8cb79eb9b71` failed because InstaNovo's
trainer constructs `FinetuneScheduler` without passing `steps_per_epoch`, so
epoch-based unfreezing cannot initialize; the override generator now converts
the intended epoch boundaries to explicit `start_step` values before installing
the config for the CLI. `05a8819d-5499-49ec-8a92-e4bc5f4db436` failed on a
transient PRIDE HTTP 403 while downloading one mzXML file; the downloader now
uses a stable user agent, retries retryable HTTP responses, resets stale
partial downloads before retrying without `Range`, and falls back from
`ftp.pride.ebi.ac.uk` to the `ftp.ebi.ac.uk` HTTPS mirror.
`4974ae3f-7e1b-466f-8ec6-b22f4988c67e` succeeded, but the run was superseded
because the step calculation used effective batch size instead of InstaNovo's
trainer batch count; the override generator now computes epoch length from
`train_batch_size`, so 6 epochs correspond to about 306 trainer steps for the
current split.

## Result

The corrected 6-epoch run trained for 306 trainer steps on 831 training spectra,
validated every 51 steps on 57 validation spectra, and evaluated on 78 held-out
test spectra. Validation loss decreased from `0.45504` before training to
`0.32188` at the final checkpoint.

Compared with the official InstaNovo v1.2.0 checkpoint on the held-out test
split, the fine-tuned checkpoint improved amino-acid precision from `0.77529`
to `0.79437`, amino-acid recall from `0.77605` to `0.79747`, amino-acid error
rate from `0.14314` to `0.12658`, and peptide precision/recall from `0.58974`
to `0.62821`. The 20 ppm precursor-mass pass rate increased from `66/78` to
`67/78`, and no phospho predictions were emitted.

## What Runs In The Container

1. `scripts/01_prepare_instanovo_checkpoint.py` downloads `instanovo-v1.2.0`
   and writes a trainer-compatible resume checkpoint.
2. `scripts/02_download_pxd059455.py` downloads PXD059455 metadata and the
   mzXML files whose raw-file names appear in `docs/msms.xlsx`. Vendor `.raw`
   files are skipped by default.
3. `scripts/03_build_pxd059455_sdf.py` maps local `docs/msms.xlsx` labels to
   PRIDE mzXML scans, encodes PTMs as UNIMOD tokens, filters bad precursor
   mass matches, and saves train/valid/test SpectrumDataFrame shards.
4. `scripts/04_make_training_overrides.py` computes training steps and the
   step-based unfreezing schedule from the prepared train split.
5. `instanovo transformer train` fine-tunes with `configs/pxd059455`.
6. `instanovo transformer predict --evaluation` evaluates the official and
   fine-tuned checkpoints on the held-out test split.
7. `scripts/05_evaluate_pxd059455.py` writes summary metrics and a comparison
   table.
8. `scripts/06_upload_aichor_artifacts.py` uploads the selected local outputs
   when AIchor output storage is available.

## Defaults

- Effective batch size: 64 (`train_batch_size=16`, `grad_accumulation=4`).
- Epoch target: 6, converted to steps from the built training split.
- Minimum training steps: 0; no artificial floor is used on this small dataset.
- Warmup: 5% of total steps, minimum 5 steps.
- Learning rate: `5e-6`, cosine schedule.
- Validation/checkpoint interval: once per training epoch.
- Fine-tuning schedule: head from step 0, decoder after one computed training
  epoch, full model after two computed training epochs.
- Evaluation uses greedy decoding because InstaNovo 1.2.2 applies
  `suppressed_residues` only on the greedy path; this prevents the previous
  phospho-token collapse on a non-phospho dataset.

## Overfitting Guard

The local label table currently parses to 967 usable labels across 19 raw
files. The training script computes trainer steps from the final train split
instead of using a fixed step count. For the current 831-spectrum train split,
this is 51 trainer steps per epoch and 306 trainer steps total; with
`grad_accumulation=4`, that is about 76 optimizer updates. Validation and
checkpointing run once per computed training epoch.
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
- `tensorboard/`
- `predictions/official_instanovo_v1.2.0_test.csv`
- `predictions/pxd059455_finetuned_test.csv`
- `reports/summary_official_vs_finetuned.csv`
- `reports/comparison_official_vs_finetuned.csv`
- `reports/run_report.json`

When `AICHOR_OUTPUT_PATH` is present, the entrypoint uploads those artifacts to
the Aichor output bucket at the end of the run.
