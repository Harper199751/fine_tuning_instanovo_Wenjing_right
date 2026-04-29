import pandas as pd

pkl_path = r"d:\01 PHD\03 Courses\CIE500 WENJING\CIE500\0.project\filtered_output\instanovo_training_table.pkl"
df = pd.read_pickle(pkl_path)

row = df.iloc[0]

print("sequence:", row["sequence"])
print("precursor_mz:", row["precursor_mz"])
print("precursor_charge:", row["precursor_charge"])
print("raw_file:", row["raw_file"])
print("scan_number:", row["scan_number"])

print("\nmz_array:")
print(row["mz_array"])

print("\nintensity_array:")
print(row["intensity_array"])

print("\nNumber of peaks:")
print("len(mz_array) =", len(row["mz_array"]))
print("len(intensity_array) =", len(row["intensity_array"]))