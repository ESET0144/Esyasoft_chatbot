import re
import logging
from nl2sql import natural_to_sql, summarize_results
from db import run_query
from security import allowed_tables_for_role
from chatbot_pipeline import render_graph_png

logger = logging.getLogger("chatbot")

# ---------------- SCHEMA ----------------
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


def handle_nl2sql(question: str, role: str, schema: str, llm_mode: str = "ollama"):
    logger.info("========== NL2SQL PIPELINE START ==========")
    logger.info(f"Question: {question}")
    logger.info(f"Role: {role}")

    # ---------- SQL GENERATION ----------
    generated_sql = natural_to_sql(question, schema, llm_mode=llm_mode)

    # ---- NORMALIZE LLM SQL OUTPUT ----
    generated_sql = generated_sql.strip()
    # Normalize quotes (cloud sometimes uses double quotes)
    generated_sql = re.sub(
        r'=\s*"([^"]+)"',
        r"= '\1'",
        generated_sql
    )

    logger.info(f"[RAW SQL AFTER NORMALIZATION] {generated_sql}")

    # Remove leading explanations
    if generated_sql.lower().startswith("select") is False:
        idx = generated_sql.lower().find("select")
        if idx != -1:
            generated_sql = generated_sql[idx:]

    # Remove SQL comments
    generated_sql = generated_sql.split("--")[0].strip()

    # Ensure semicolon
    if not generated_sql.endswith(";"):
        generated_sql += ";"
    
    if generated_sql.startswith("--CANNOT_CONVERT--"):
        logger.warning("NL2SQL → FAILED (cannot convert)")
        return {
            "question": question,
            "output_type": "nl",
            "summary": "I couldn’t convert this into a database query.",
            "include_table": False
        }

    logger.info(f"SQL GENERATED → {generated_sql}")
    lower_sql = generated_sql.lower()

    # ---------- ROLE-BASED ACCESS CONTROL ----------
    allowed_tables = allowed_tables_for_role(role)
    tables_used = re.findall(r"(?:from|join)\s+([a-zA-Z_]+)", lower_sql)

    for table in set(tables_used):
        if table not in allowed_tables:
            logger.warning(f"ACCESS DENIED → table={table}, role={role}")
            return {
                "question": question,
                "output_type": "nl",
                "summary": f"You are not authorized to access `{table}`.",
                "include_table": False
            }

    # ---------- SQL SAFETY ----------
    forbidden = ["drop ", "delete ", "update ", "alter ", "attach ", "detach ", "vacuum", "--"]
    if any(f in lower_sql for f in forbidden):
        logger.error("SQL BLOCKED → unsafe keywords detected")
        return {
            "question": question,
            "output_type": "nl",
            "summary": "Generated SQL was blocked for safety reasons.",
            "include_table": False
        }

    # ---------- EXECUTE SQL ----------
    rows_data = run_query(generated_sql)
    if isinstance(rows_data, dict) and rows_data.get("error"):
        logger.error(f"SQL EXECUTION FAILED → {rows_data['error']}")
        return {
            "question": question,
            "output_type": "nl",
            "summary": f"Query failed: {rows_data['error']}",
            "include_table": False
        }

    rows = rows_data["rows"]
    columns = rows_data["columns"]
    ncols = len(rows[0]) if rows else 0

    logger.info(f"SQL EXECUTED → rows={len(rows)}, cols={columns}")

    # ---------- OUTPUT TYPE DECISION ----------
    ql = question.lower()
    if any(w in ql for w in ["plot", "graph", "trend", "over time"]):
        output_type = "graph"
        logger.info("ROUTE SELECTED → GRAPH")
    elif any(w in ql for w in ["summary", "explain", "average", "max", "min"]):
        output_type = "nl"
        logger.info("ROUTE SELECTED → NL")
    else:
        output_type = "table"
        logger.info("ROUTE SELECTED → TABLE")

    # ---------- SUMMARY (ALWAYS) ----------
    summary = summarize_results(
    question,
    generated_sql,
    rows,
    llm_mode=llm_mode
)

    # ---------- GRAPH RENDER ----------
    if output_type == "graph":
        logger.info("GRAPH_RENDERER CALLED")
        image_b64 = render_graph_png(rows, columns)

        if not image_b64:
            logger.warning("GRAPH_RENDERER → NO IMAGE PRODUCED")
        else:
            logger.info("GRAPH_RENDERER → IMAGE GENERATED")

        return {
            "question": question,
            "output_type": "graph",
            "generated_sql": generated_sql,
            "columns": columns,
            "result": rows,
            "ncols": ncols,
            "image": image_b64,
            "summary": summary,
            "include_table": False
        }

    # ---------- TABLE / NL RESPONSE ----------
    logger.info("TABLE_RENDERER CALLED")

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
