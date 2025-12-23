# nl2sql.py
import textwrap
from typing import Any, List
from ollama import chat

MODEL = "gemma3"   # change if needed

FEW_SHOT = textwrap.dedent("""
You are a strict assistant that converts plain English to a valid single-line SQLite SQL query.
Rules:
- Use only the table and column names provided in the schema.
- Return ONLY the SQL query (one statement). Do NOT add explanations or backticks.
- Use single quotes for string literals.
- If the question cannot be converted to SQL (ambiguous / no columns), respond with exactly: --CANNOT_CONVERT--
Examples:

Schema:
meter_table(id INTEGER, meter_id TEXT, datetime TEXT, forecasted_load_kwh REAL)
customer_table(customer_id TEXT, customer_name TEXT, email TEXT, meter_id TEXT)
comed_hourly(id INTEGER, meter_id TEXT, datetime TEXT, hourly_load_kwh REAL)

Question: show 10 rows for meter data
SQL: SELECT * FROM meter_table WHERE meter_id = 'MTR001';

Schema:
meter_table(id INTEGER, meter_id TEXT, datetime TEXT, forecasted_load_kwh REAL)
customer_table(customer_id TEXT, customer_name TEXT, email TEXT, meter_id TEXT)
comed_hourly(id INTEGER, meter_id TEXT, datetime TEXT, hourly_load_kwh REAL)
Question: show customer name and email for meter 740-60-4283
SQL: SELECT c.customer_name, c.email FROM customer_table c WHERE c.meter_id = '740-60-4283';

Schema:
meter_table(id INTEGER, meter_id TEXT, datetime TEXT, forecasted_load_kwh REAL)
customer_table(customer_id TEXT, customer_name TEXT, email TEXT, meter_id TEXT)
comed_hourly(id INTEGER, meter_id TEXT, datetime TEXT, hourly_load_kwh REAL)
Question: show hourly data for meter 740-60-4283
SQL: SELECT * FROM comed_hourly WHERE meter_id = '740-60-4283';

Schema:
meter_table(id INTEGER, meter_id TEXT, datetime TEXT, forecasted_load_kwh REAL)
customer_table(customer_id TEXT, customer_name TEXT, email TEXT, meter_id TEXT)
comed_hourly(id INTEGER, meter_id TEXT, datetime TEXT, hourly_load_kwh REAL)
Question: count rows in meter_table
SQL: SELECT COUNT(*) FROM meter_table;
""").strip()

def natural_to_sql(question: str, schema: str) -> str:
    system_msg = {"role": "system", "content": "You are an assistant that converts natural language to SQL for SQLite. Be precise."}
    user_prompt = f"{FEW_SHOT}\n\nSchema:\n{schema}\n\nQuestion: {question}\nSQL:"
    user_msg = {"role": "user", "content": user_prompt}

    try:
        resp = chat(model=MODEL, messages=[system_msg, user_msg], stream=False)
        sql_text = ""
        if isinstance(resp, dict):
            msg = resp.get("message") or {}
            if isinstance(msg, dict):
                sql_text = msg.get("content", "")
            else:
                sql_text = str(resp)
        else:
            try:
                sql_text = resp.message.content
            except Exception:
                sql_text = str(resp)

        if sql_text is None:
            return "--CANNOT_CONVERT--"

        sql_text = sql_text.strip()
        if sql_text.lower().startswith("sql:"):
            sql_text = sql_text[len("sql:"):].strip()
        if not sql_text.endswith(";"):
            sql_text = sql_text + ";"
        return sql_text
    except Exception as e:
        return f"--CANNOT_CONVERT-- ({e})"


def summarize_results(question: str, generated_sql: str, rows: List[Any], max_rows:int=200) -> str:
    prompt = textwrap.dedent(f"""
    You are an assistant that summarizes SQL query results in natural language.
    Rules:
    - Produce a concise summary (1-3 sentences).
    - Mention important numeric values (counts, max/min) if helpful.
    - If rows are empty, return exactly: No results found.

    Query: {generated_sql}
    Question: {question}
    Rows: {rows[:max_rows]}

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
