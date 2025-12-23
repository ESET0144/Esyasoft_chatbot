# nl2sql_pipeline.py
from chatbot_pipeline import render_graph_png
from nl2sql import natural_to_sql, summarize_results
from db import run_query

SCHEMA = """
meter_table (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    meter_id TEXT NOT NULL,
    datetime TEXT NOT NULL,
    forecasted_load_kwh REAL
),
customer_table (
    customer_id TEXT,
    customer_name TEXT,
    email TEXT,
    meter_id TEXT UNIQUE
),
Revenue_data (
    Datetime TEXT,
    Revenue REAL
)
"""

def handle_nl2sql(question: str) -> dict:
    # 1️⃣ NL → SQL
    generated_sql = natural_to_sql(question, SCHEMA)

    if generated_sql.startswith("--CANNOT_CONVERT--"):
        return {
            "status_code": 400,
            "error": "Could not convert question to SQL"
        }

    # 2️⃣ Execute SQL
    rows_data = run_query(generated_sql)

    if isinstance(rows_data, dict) and rows_data.get("error"):
        return {
            "status_code": 400,
            "error": rows_data["error"]
        }

    rows = rows_data["rows"]
    columns = rows_data["columns"]
    ncols = len(columns)

    # 3️⃣ Decide output type
    ql = question.lower()
    output_type = "table"

    if any(w in ql for w in ["plot", "graph", "trend", "over time"]):
        output_type = "graph"
    elif any(w in ql for w in ["summary", "explain", "average", "max", "min"]):
        output_type = "nl"

    # 4️⃣ Always generate summary
    summary = summarize_results(question, generated_sql, rows)

    # 5️⃣ Graph output (PNG base64)
    if output_type == "graph":
        image_b64 = render_graph_png(rows, columns)

        return {
            "question": question,
            "output_type": "graph",
            "generated_sql": generated_sql,
            "columns": columns,
            "result": rows,
            "ncols": ncols,
            "image": image_b64,
            "summary": summary
        }

    # 6️⃣ Table / NL output
    return {
        "question": question,
        "output_type": output_type,
        "generated_sql": generated_sql,
        "columns": columns,
        "result": rows,
        "ncols": ncols,
        "summary": summary,
        "include_table": True
    }
