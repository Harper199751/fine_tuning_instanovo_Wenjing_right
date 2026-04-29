import pandas as pd
from instanovo.utils.data_handler import SpectrumDataFrame

# ========= paths =========
train_pkl = r"d:\01 PHD\03 Courses\CIE500 WENJING\CIE500\0.project\filtered_output\train_table.pkl"
val_pkl = r"d:\01 PHD\03 Courses\CIE500 WENJING\CIE500\0.project\filtered_output\val_table.pkl"
output_dir = r"d:\01 PHD\03 Courses\CIE500 WENJING\CIE500\0.project\filtered_output\instanovo_dataset"

required_cols = ["sequence", "precursor_mz", "precursor_charge", "mz_array", "intensity_array"]

train_df = pd.read_pickle(train_pkl)[required_cols].dropna().copy()
val_df = pd.read_pickle(val_pkl)[required_cols].dropna().copy()

print("Train size:", len(train_df))
print("Val size:", len(val_df))

train_sdf = SpectrumDataFrame(train_df)
val_sdf = SpectrumDataFrame(val_df)

train_sdf.save(output_dir, partition="train", chunk_size=10000)
val_sdf.save(output_dir, partition="val", chunk_size=10000)

print("Saved native dataset to:", output_dir)