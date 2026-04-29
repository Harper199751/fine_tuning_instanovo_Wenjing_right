import re #extract scan numbers using regular expressions
import pandas as pd #read .xlsx and 
from pyteomics import mgf #read .mgf

# make sure the pathway of files
excel_path = r"d:\01 PHD\03 Courses\CIE500 WENJING\CIE500\0.project\filtered_output\msms.xlsx"
mgf_path = r"d:\01 PHD\03 Courses\CIE500 WENJING\CIE500\0.project\filtered_output\all_filtered_spectra.mgf"

out_pkl = r"d:\01 PHD\03 Courses\CIE500 WENJING\CIE500\0.project\filtered_output\instanovo_training_table.pkl"
out_csv = r"d:\01 PHD\03 Courses\CIE500 WENJING\CIE500\0.project\filtered_output\instanovo_training_table.csv"

# read the label table
df = pd.read_excel(excel_path, sheet_name=0)

df = df[["Raw file", "Scan number", "Sequence"]].dropna().copy() 
#retain key information and delete NA and make a copy

df["Raw file"] = (
    df["Raw file"]
    .astype(str)
    .str.strip()
    .str.replace(".raw", "", regex=False)
) #clean raw file, keep same format of file name

df["Scan number"] = df["Scan number"].astype(int) # transfer to integer
df["Sequence"] = df["Sequence"].astype(str).str.strip() # transfer to string

# Build a sequence mapping: (raw file, scan number) -> sequence
key_to_seq = {
    (row["Raw file"], row["Scan number"]): row["Sequence"]
    for _, row in df.iterrows()
} 

print("Number of labels:", len(key_to_seq))

def extract_raw_and_scan(title: str):#define a function
    raw_file = None
    scan = None

    m_raw = re.search(r'File:"([^"]+)\.raw"', title, re.IGNORECASE) #catch the name of raw file
    if m_raw:
        raw_file = m_raw.group(1).strip()  #find raw file

    m_scan = re.search(r'scan=(\d+)', title, re.IGNORECASE) #continue to find scan
    if m_scan:
        scan = int(m_scan.group(1))  #find target scan and transfer to integer

    return raw_file, scan

# build the training table
rows = [] # save the taining row
matched = 0  # count matched scans
unmatched = 0 # count unmatched scans
bad_charge = 0 # count lose charge 
bad_pepmass = 0 # count lose spectra 
#initial variables

with mgf.read(mgf_path) as reader: #open .mgf
    for spec in reader: #spec is a dictionary, including paramters, m/z, intensity array
        params = spec["params"] #include the information of title, precursor mass, charge,

        title = str(params.get("title", "")) #read title
        raw_file, scan = extract_raw_and_scan(title) # call the defined function

        if raw_file is None or scan is None: # if NA, count
            unmatched += 1
            continue

        seq = key_to_seq.get((raw_file, scan)) #call the map
        if seq is None: #if NA, count
            unmatched += 1
            continue

        pepmass = params.get("pepmass", None) #identify the pepmass is readable
        if pepmass is None:
            bad_pepmass += 1
            continue

        try:
            precursor_mz = float(pepmass[0] if isinstance(pepmass, (tuple, list)) else pepmass)
        except Exception:
            bad_pepmass += 1
            continue #take the precursor m/z, not its intensity

        charge = params.get("charge", None) #identify the charge is readable
        if charge is None:
            bad_charge += 1
            continue

        if isinstance(charge, list):
            charge = charge[0] 

        m_charge = re.search(r'(\d+)', str(charge))
        if not m_charge:
            bad_charge += 1
            continue #take the charge number without symbols

        precursor_charge = int(m_charge.group(1)) #transfer to integer

        #read the spectra information and transfer to Python list
        mz_array = spec["m/z array"].tolist() 
        intensity_array = spec["intensity array"].tolist()
        
        # name new rows for list
        rows.append({
            "sequence": seq,
            "precursor_mz": precursor_mz,
            "precursor_charge": precursor_charge,
            "mz_array": mz_array,
            "intensity_array": intensity_array,
            "raw_file": raw_file,
            "scan_number": scan,
        })
        matched += 1

train_df = pd.DataFrame(rows) #transfer to pandas dataframe

#check the quanlity of extration
print("Matched spectra:", matched)
print("Unmatched spectra:", unmatched)
print("Missing/invalid pepmass:", bad_pepmass)
print("Missing/invalid charge:", bad_charge)
print("Final number of samples:", len(train_df))

print(train_df.head())

#output fitable files
train_df.to_pickle(out_pkl)
train_df.to_csv(out_csv, index=False)

print("\nOutput files:")
print(out_pkl)
print(out_csv)