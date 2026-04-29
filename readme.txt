# Fine-tuning InstaNovo for Wastewater Bacterial Proteomics

This project uses InstaNovo for de novo peptide sequencing on wastewater bacterial proteomics data.
The whole idea is in the slide of "Bacterial Fine-Tuning of InstaNovo for Large-Scale Wastewater Proteomics_Wenjing"

1. Environment

The project was run on Windows using a conda environment.

#powershell:
conda create -n instanovo_clean python=3.10
conda activate instanovo_clean


(1)Install required packages:

#powershell:
pip install instanovo
pip install torch pandas pyarrow openpyxl tensorboard

May have block for system, using:
python -c "from instanovo.cli import instanovo_entrypoint; instanovo_entrypoint()"

2. Dataset

files:
data_split/parquet/dataset-ms-train-0000-0001.parquet
data_split/parquet/dataset-ms-val-0000-0001.parquet
data_split/parquet/dataset-ms-test-0000-0001.parquet

3. Fine-tuning Command
Fine-tuned model
#powershell:
instanovo transformer train `
  dataset.train_path="XXX" `
  dataset.valid_path="XXX" `
  dataset.train_partition="train" `
  dataset.valid_partition="val" `
  resume_checkpoint_path="XXX\instanovo-v1.2.0.ckpt" `
  train_batch_size=4 `
  predict_batch_size=4 `
  learning_rate=1e-7 `
  warmup_iters=2 `
  training_steps=10 `
  validation_interval=10 `
  checkpoint_interval=10 `
  use_neptune=false

4. Run and evaluated  model

python -c "from instanovo.cli import instanovo_entrypoint; instanovo_entrypoint()" transformer predict `
  --data-path "xxxx.parquet" `
  --output-path "xxxx.csv" `
  --instanovo-model "instanovo-v1.2.0" `
  --evaluation

python -c "from instanovo.cli import instanovo_entrypoint; instanovo_entrypoint()" transformer predict `
  --data-path "xxx.parquet" `
  --output-path "xxx.csv" `
  --instanovo-model "models\FINAL_trained_ultra_light_instanovo.ckpt" `
  --evaluation





