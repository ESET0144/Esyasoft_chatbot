import sqlite3
import re
import sqlparse
from typing import List

DB_PATH = "forcast.db"   # your database file


def init_db(db_path: str = DB_PATH):
    """Create minimal tables if they don't exist (idempotent)."""
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute("""
    CREATE TABLE IF NOT EXISTS meter_table (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        meter_id TEXT NOT NULL,
        datetime TEXT NOT NULL,
        forecasted_load_kwh REAL
    );
    """)
    cur.execute("""
    CREATE TABLE IF NOT EXISTS customer_table (
        customer_id TEXT,
        customer_name TEXT,
        email TEXT,
        meter_id TEXT UNIQUE
    );
    """)
    cur.execute("""
    CREATE TABLE IF NOT EXISTS Revenue_data (
        Datetime TEXT,
        Revenue REAL
    );
    """)
    conn.commit()
    conn.close()


def _extract_table_names(sql: str) -> List[str]:
    """Extract table names conservatively.

    Strategy:
    - Find names that directly follow FROM/JOIN keywords (likely table identifiers)
    - Also detect any literal occurrence of known table names (e.g., Revenue_data)
      anywhere in the SQL text to catch subqueries, CTEs or aliasing attempts.

    Returns lower-cased unique table names.
    """
    tables = set()

    # 1) find names after FROM or JOIN
    for m in re.finditer(r"\b(?:from|join)\s+([A-Za-z_][A-Za-z0-9_]*)", sql, re.IGNORECASE):
        tables.add(m.group(1).lower())

    # 2) known table literals (helps catch mentions inside subqueries/CTEs)
    known = ["meter_table", "customer_table", "revenue_data"]
    for k in known:
        if re.search(rf"\b{k}\b", sql, re.IGNORECASE):
            tables.add(k)

    return sorted(tables)


def _is_safe_statement(sql: str) -> bool:
    """Reject dangerous SQL constructs before execution."""
    low = sql.lower()
    forbidden = ["drop ", "delete ", "update ", "insert ", "alter ", "attach ", "detach ", "vacuum", "pragma", "--", "/*", "sqlite_master"]
    # disallow multiple statements
    if sql.count(";") > 1:
        return False
    for f in forbidden:
        if f in low:
            return False
    return True


def secure_run_query(sql: str, role_allowed_tables: List[str], max_rows: int = 200):
    """Execute SQL against SQLite with authorization checks, transaction and rollback.

    Steps:
    1. Ensure statement is safe (no DDL, multiple statements, PRAGMA)
    2. Extract table names from SQL, normalize and verify against allowed tables
    3. Open DB transaction, execute, commit; on any error rollback

    Returns dict with keys: rows, columns or raises Exception with message.
    """
    if not _is_safe_statement(sql):
        return {"error": "Unsafe or disallowed SQL statement detected."}

    # Ensure SELECT queries don't return the whole DB accidentally
    q = sql.strip()
    low = q.lower()
    if low.startswith("select") and " limit " not in low and not low.endswith("limit"):
        if q.endswith(";"):
            q = q[:-1]
        q = f"{q} LIMIT {max_rows};"

    # Extract table names and validate
    tables = _extract_table_names(sql)
    # role_allowed_tables is expected lower-case
    for t in tables:
        if t in ("", ",", "select", "from", "where", "join", "on", "group", "by", "order"):
            continue
        # if this token looks like a function, skip
        if re.match(r"[a-zA-Z0-9_]+\(|'|\"", t):
            continue
        if t not in role_allowed_tables:
            return {"error": f"unauthorized_table_access: '{t}' is not permitted for your role", "unauthorized_table": t}

    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    try:
        cur.execute("BEGIN")
        cur.execute(q)
        rows = cur.fetchall()
        col_names = [description[0] for description in cur.description] if cur.description else []
        conn.commit()
        return {"rows": rows, "columns": col_names}
    except Exception as e:
        conn.rollback()
        return {"error": str(e)}
    finally:
        conn.close()


def run_query(query: str, max_rows: int = 50):
   
   """Legacy compatibility wrapper used by existing code.

    This executes queries with admin-level table access (for backward compatibility
    with existing code such as `app.py` which expects a `run_query` function).
    For new code paths prefer `secure_run_query` with explicit role checks.
    """
   allowed = ["meter_table", "customer_table", "revenue_data"]
   return secure_run_query(query, allowed, max_rows=max_rows)

