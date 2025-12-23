import sqlite3

DB_PATH = "forcast.db"   # your database file

def run_query(query, max_rows: int = 50):
    """
    Run a SQL query against the SQLite DB.

    Safety: For `SELECT` queries that do not include a `LIMIT` clause,
    this function will append a `LIMIT {max_rows}` to avoid returning
    an entire table unexpectedly.
    """
    q = query.strip()
    low = q.lower()

    # If it's a SELECT and no explicit LIMIT exists, add a safeguard limit
    if low.startswith("select") and " limit " not in low and not low.endswith("limit"):
        # remove trailing semicolon if present, then append limit
        if q.endswith(";"):
            q = q[:-1]
        q = f"{q} LIMIT {max_rows};"

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    try:
        cursor.execute(q)
        rows = cursor.fetchall()
        col_names = [description[0] for description in cursor.description] if cursor.description else []
        conn.close()
        return {"rows": rows, "columns": col_names}
    except Exception as e:
        conn.close()
        return {"error": str(e)}
