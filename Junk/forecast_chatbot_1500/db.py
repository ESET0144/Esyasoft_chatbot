import sqlite3

DB_PATH = "forcast.db"   # your database file

def run_query(query):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    try:
        cursor.execute(query)
        rows = cursor.fetchall()
        conn.close()
        return rows
    except Exception as e:
        conn.close()
        return {"error": str(e)}
