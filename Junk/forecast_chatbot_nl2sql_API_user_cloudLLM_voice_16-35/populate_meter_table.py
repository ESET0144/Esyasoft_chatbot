# populate_meter_table.py
import sqlite3
from datetime import datetime, timedelta
import random
from math import ceil

# --- CONFIGURE ---
DB_PATH = "forcast.db"   # change to absolute path if your DB is elsewhere
TABLE_NAME = "meter_table"

# meter_id list (from your pasted data)
METER_IDS = [
    "740-60-4283","158-22-2786","147-22-2537","806-38-0276","200-32-8690",
    "106-84-1719","797-27-3543","359-97-6365","328-34-3129","108-13-7234",
    "607-85-4390","589-86-9998","880-38-1750","534-32-0837","249-45-6772"
]

# start datetime (taken from your first row). Ensure seconds present.
START_STR = "2026-01-01 00:00:00"
START_DT = datetime.strptime(START_STR, "%Y-%m-%d %H:%M:%S")

# how long to generate: 1 month (January 2026) -> end = 2026-02-01 00:00:00 (exclusive)
END_DT = datetime(2026, 2, 1, 0, 0, 0)

# interval
INTERVAL_MINUTES = 15
INTERVAL = timedelta(minutes=INTERVAL_MINUTES)

# insertion chunk size (tune if necessary)
CHUNK_SIZE = 5000

# --- Create table if not exists ---
def create_table(conn: sqlite3.Connection):
    conn.execute(f"""
    CREATE TABLE IF NOT EXISTS {TABLE_NAME} (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        meter_id TEXT NOT NULL,
        datetime TEXT NOT NULL,
        forecasted_load_kwh REAL
    );
    """)
    conn.commit()

# --- Generator for rows for a single meter_id ---
def generate_rows_for_meter(meter_id: str, start: datetime, end: datetime, interval: timedelta):
    t = start
    while t < end:
        # forecast value: uniform between 0 and 2, rounded to 3 decimals
        val = round(random.uniform(0.0, 2.0), 3)
        yield (meter_id, t.strftime("%Y-%m-%d %H:%M:%S"), val)
        t += interval

def main():
    total_rows = 0
    # open connection
    conn = sqlite3.connect(DB_PATH)
    create_table(conn)

    cur = conn.cursor()

    # Pre-calc total expected rows (optional)
    intervals = int((END_DT - START_DT).total_seconds() // (INTERVAL_MINUTES * 60))
    expected_per_meter = intervals
    expected_total = expected_per_meter * len(METER_IDS)
    print(f"Generating approx {expected_total} rows ({expected_per_meter} per meter)")

    batch = []
    inserted = 0

    try:
        for meter in METER_IDS:
            gen = generate_rows_for_meter(meter, START_DT, END_DT, INTERVAL)
            for row in gen:
                batch.append(row)
                if len(batch) >= CHUNK_SIZE:
                    cur.executemany(f"INSERT INTO {TABLE_NAME} (meter_id, datetime, forecasted_load_kwh) VALUES (?, ?, ?);", batch)
                    conn.commit()
                    inserted += len(batch)
                    print(f"Inserted {inserted}/{expected_total} rows...")
                    batch.clear()

        # insert remaining
        if batch:
            cur.executemany(f"INSERT INTO {TABLE_NAME} (meter_id, datetime, forecasted_load_kwh) VALUES (?, ?, ?);", batch)
            conn.commit()
            inserted += len(batch)
            batch.clear()

        print(f"Done. Inserted {inserted} rows into {TABLE_NAME} in {DB_PATH}")

    finally:
        conn.close()

if __name__ == "__main__":
    main()
