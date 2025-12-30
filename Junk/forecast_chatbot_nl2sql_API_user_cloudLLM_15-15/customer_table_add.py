import sqlite3, csv

DB = "forcast.db"
CSV = "customer_table.csv"

conn = sqlite3.connect(DB)
cur = conn.cursor()

# Create table (4 columns)
cur.execute("""
CREATE TABLE IF NOT EXISTS customer_table (
    customer_id TEXT,
    customer_name TEXT,
    email TEXT,
    meter_id TEXT UNIQUE
);
""")

# Try both comma and tab delimiters
with open(CSV, encoding="utf-8") as f:
    sample = f.read(200)
    delim = "\t" if "\t" in sample else ","
    f.seek(0)
    reader = csv.reader(f, delimiter=delim)

    # Skip header
    next(reader, None)

    for row in reader:
        if len(row) < 4: 
            continue
        cur.execute(
            "INSERT OR IGNORE INTO customer_table (customer_id, customer_name, email, meter_id) VALUES (?, ?, ?, ?)",
            (row[0], row[1], row[2], row[3])
        )

conn.commit()
conn.close()

print("Import complete.")
