import pandas as pd
import sqlite3

# ----------------------------------------
# 1. LOAD CSV
# ----------------------------------------
csv_path = "COMED_hourly.csv"   # <-- replace with your actual filename

try:
    df = pd.read_csv(csv_path)
    print("Loaded CSV preview:")
    print(df.head())
except Exception as e:
    print(f"❌ Error loading CSV: {e}")
    exit()


# ----------------------------------------
# 2. CLEAN / STANDARDIZE COLUMNS
# Prophet requires:
#    ds = datetime column
#    y  = numerical target
# ----------------------------------------

expected_datetime_cols = ["Datetime", "datetime", "date", "timestamp"]
expected_load_cols = ["COMED_MW", "load", "value", "y"]

datetime_col = None
load_col = None

# Detect datetime column
for col in expected_datetime_cols:
    if col in df.columns:
        datetime_col = col
        break

# Detect load column
for col in expected_load_cols:
    if col in df.columns:
        load_col = col
        break

if datetime_col is None or load_col is None:
    print("❌ ERROR: CSV does not contain required columns.")
    print("CSV must contain one datetime column and one load column.")
    print("Expected datetime column: Datetime / date / timestamp")
    print("Expected load column: COMED_MW / load")
    exit()


# Ensure datetime is proper format
df[datetime_col] = pd.to_datetime(df[datetime_col], errors="coerce")

if df[datetime_col].isna().sum() > 0:
    print("⚠ WARNING: Some datetime values could not be parsed, they will be dropped.")
    df = df.dropna(subset=[datetime_col])

# Rename columns to match Prophet pipeline
df = df.rename(columns={
    datetime_col: "Datetime",
    load_col: "COMED_MW"
})


# ----------------------------------------
# 3. WRITE DATAFRAME INTO SQLITE
# ----------------------------------------

db_path = "loadforecast.db"
table_name = "forecast"

try:
    conn = sqlite3.connect(db_path)

    df.to_sql(
        name=table_name,
        con=conn,
        if_exists="replace",   # replace table each time
        index=False
    )

    conn.commit()
    conn.close()

    print(f"\n✔ SUCCESS: CSV uploaded into '{db_path}' → table '{table_name}'")
    print(f"Rows inserted: {len(df)}")

except Exception as e:
    print(f"❌ Database Error: {e}")
