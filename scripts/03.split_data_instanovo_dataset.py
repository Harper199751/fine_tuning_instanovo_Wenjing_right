import pandas as pd
import torch
from torch.utils.data import random_split
from instanovo.utils.data_handler import SpectrumDataFrame

# temporary compatibility patch for pandas
def _write_parquet(self, path):
    return self.to_parquet(path, index=False)

pd.DataFrame.write_parquet = _write_parquet

# make sure the pathway of dataset
input_pkl = r"d:\01 PHD\03 Courses\CIE500 WENJING\CIE500\0.project\filtered_output\instanovo_training_table.pkl"

train_pkl = r"d:\01 PHD\03 Courses\CIE500 WENJING\CIE500\0.project\filtered_output\train_table.pkl"
val_pkl = r"d:\01 PHD\03 Courses\CIE500 WENJING\CIE500\0.project\filtered_output\val_table.pkl"
test_pkl = r"d:\01 PHD\03 Courses\CIE500 WENJING\CIE500\0.project\filtered_output\test_table.pkl"

train_csv = r"d:\01 PHD\03 Courses\CIE500 WENJING\CIE500\0.project\filtered_output\train_table.csv"
val_csv = r"d:\01 PHD\03 Courses\CIE500 WENJING\CIE500\0.project\filtered_output\val_table.csv"
test_csv = r"d:\01 PHD\03 Courses\CIE500 WENJING\CIE500\0.project\filtered_output\test_table.csv"

output_dir = r"d:\01 PHD\03 Courses\CIE500 WENJING\CIE500\0.project\filtered_output\instanovo_dataset"

# read key values
df = pd.read_pickle(input_pkl)

print("Total samples before filtering:", len(df))

# keep only the columns required by InstaNovo
df = df[
    ["sequence", "precursor_mz", "precursor_charge", "mz_array", "intensity_array"]
].dropna().copy().reset_index(drop=True)

print("Total samples after filtering:", len(df))

# set split sizes
n_total = len(df)
n_train = int(n_total * 0.70)
n_val = int(n_total * 0.15)
n_test = n_total - n_train - n_val

print("\nPlanned split sizes:")
print("Train:", n_train)
print("Validation:", n_val)
print("Test:", n_test)

# random split by indices
indices = list(range(n_total))

generator = torch.Generator().manual_seed(42)
train_subset, val_subset, test_subset = random_split(
    indices,
    [n_train, n_val, n_test],
    generator=generator
)

train_indices = list(train_subset)
val_indices = list(val_subset)
test_indices = list(test_subset)

train_df = df.iloc[train_indices].reset_index(drop=True)
val_df = df.iloc[val_indices].reset_index(drop=True)
test_df = df.iloc[test_indices].reset_index(drop=True)

# save as pkl / csv
train_df.to_pickle(train_pkl)
val_df.to_pickle(val_pkl)
test_df.to_pickle(test_pkl)

train_df.to_csv(train_csv, index=False)
val_df.to_csv(val_csv, index=False)
test_df.to_csv(test_csv, index=False)

# convert to SpectrumDataFrame
train_sdf = SpectrumDataFrame(train_df)
val_sdf = SpectrumDataFrame(val_df)
test_sdf = SpectrumDataFrame(test_df)

# save in InstaNovo native parquet format
train_sdf.save(output_dir, partition="train")
val_sdf.save(output_dir, partition="val")
test_sdf.save(output_dir, partition="test")

print("\nSplit completed.")
print(f"Train samples: {len(train_df)} ({len(train_df)/n_total:.2%})")
print(f"Validation samples: {len(val_df)} ({len(val_df)/n_total:.2%})")
print(f"Test samples: {len(test_df)} ({len(test_df)/n_total:.2%})")

print("\nOutput files:")
print(train_pkl)
print(val_pkl)
print(test_pkl)
print(train_csv)
print(val_csv)
print(test_csv)

print("\nSaved SpectrumDataFrame dataset to:")
print(output_dir)

