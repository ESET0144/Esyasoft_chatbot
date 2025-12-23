# nl2sql.py
import textwrap
from typing import Any, List
from ollama import chat

MODEL = "gemma3"   # change if you use a different model

# --- FEW-SHOT & natural->SQL ---
FEW_SHOT = textwrap.dedent("""
You are a strict assistant that converts plain English to a valid single-line SQLite SQL query.
Rules:
- Use only the table and column names provided in the schema.
- Return ONLY the SQL query (one statement). Do NOT add explanations or backticks.
- Use single quotes for string literals.
- If the question cannot be converted to SQL (ambiguous / no columns), respond with exactly: --CANNOT_CONVERT--
Examples:

Schema:
forecasted_table(id INTEGER, meter_id TEXT, datetime TEXT, forecasted_load_kwh REAL)
Question: show all rows for meter MTR001
SQL: SELECT * FROM forecasted_table WHERE meter_id = 'MTR001';

Schema:
forecasted_table(id INTEGER, meter_id TEXT, datetime TEXT, forecasted_load_kwh REAL)
Question: count rows
SQL: SELECT COUNT(*) FROM forecasted_table;
""").strip()

def natural_to_sql(question: str, schema: str) -> str:
    """
    Convert natural language question -> SQL using a local Ollama model.
    Returns SQL string ending with semicolon, or '--CANNOT_CONVERT--' on failure.
    """
    system_msg = {"role": "system", "content": "You are an assistant that converts natural language to SQL for SQLite. Be precise."}
    user_prompt = f"{FEW_SHOT}\n\nSchema:\n{schema}\n\nQuestion: {question}\nSQL:"
    user_msg = {"role": "user", "content": user_prompt}

    try:
        resp = chat(model=MODEL, messages=[system_msg, user_msg], stream=False)
        # extract text robustly
        sql_text = ""
        if isinstance(resp, dict):
            msg = resp.get("message") or resp.get("message", {})
            if isinstance(msg, dict):
                sql_text = msg.get("content", "")
            else:
                sql_text = str(resp)
        else:
            # object-like response
            try:
                sql_text = resp.message.content
            except Exception:
                sql_text = str(resp)

        if sql_text is None:
            return "--CANNOT_CONVERT--"

        sql_text = sql_text.strip()
        # remove "SQL:" prefix if present
        if sql_text.lower().startswith("sql:"):
            sql_text = sql_text[len("sql:"):].strip()
        # ensure semicolon
        if not sql_text.endswith(";"):
            sql_text = sql_text + ";"
        return sql_text
    except Exception as e:
        # Don't expose internal stack; return the special token with message
        return f"--CANNOT_CONVERT-- ({e})"


# --- Summarize results (rows) into natural language ---
def summarize_results(question: str, generated_sql: str, rows: List[Any], max_rows:int=200) -> str:
    """
    Summarize query results into 1-3 sentences using the local model.
    rows: list of tuples (as returned by sqlite3). We convert to list of lists for readability.
    """
    # limit rows to avoid massive prompts
    sample_rows = rows[:max_rows]
    prompt = textwrap.dedent(f"""
    You are an assistant that summarizes SQL query results in natural language.
    Rules:
    - Produce a concise summary (1-3 sentences).
    - Mention important numeric values (counts, max/min) if helpful.
    - If rows are empty, return exactly: No results found.

    Query: {generated_sql}
    Question: {question}
    Rows: {sample_rows}

    Summary:
    """).strip()

    try:
        resp = chat(model=MODEL, messages=[
            {"role": "system", "content": "You summarize SQL results into natural language. Be concise."},
            {"role": "user", "content": prompt}
        ], stream=False)

        summary = ""
        if isinstance(resp, dict):
            msg = resp.get("message") or {}
            if isinstance(msg, dict):
                summary = msg.get("content","")
            else:
                summary = str(resp)
        else:
            try:
                summary = resp.message.content
            except Exception:
                summary = str(resp)

        if not summary:
            return "No results found."

        summary = summary.strip()
        if summary.lower().startswith("summary:"):
            summary = summary[len("summary:"):].strip()
        return summary
    except Exception as e:
        return f"Could not summarize results: {e}"
