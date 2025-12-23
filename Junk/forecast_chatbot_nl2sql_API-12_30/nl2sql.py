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
- DATETIME HANDLING: datetime columns are stored as TEXT. For aggregations/grouping, use strftime() to convert.
- For weekly aggregations: use strftime('%Y-W%W', datetime)
- For daily aggregations: use DATE(datetime) or strftime('%Y-%m-%d', datetime)
- For monthly aggregations: use strftime('%Y-%m', datetime)
- For hourly aggregations: use strftime('%Y-%m-%d %H:00', datetime)
- Always ORDER BY the grouped datetime column to maintain chronological order.
- If the question cannot be converted to SQL (ambiguous / no columns), respond with exactly: --CANNOT_CONVERT--

Schema:
meter_table(id INTEGER, meter_id TEXT, datetime TEXT, forecasted_load_kwh REAL)
customer_table(customer_id TEXT, customer_name TEXT, email TEXT, meter_id TEXT)
Revenue_data(Datetime TEXT, Revenue REAL)

Examples:
Question: show customer name and email for meter 740-60-4283
SQL: SELECT c.customer_name, c.email FROM customer_table c WHERE c.meter_id = '740-60-4283';

Question: show weekly average load for meter 740-60-4283
SQL: SELECT strftime('%Y-W%W', datetime) as week, AVG(forecasted_load_kwh) as avg_load FROM meter_table WHERE meter_id = '740-60-4283' GROUP BY strftime('%Y-W%W', datetime) ORDER BY week;

Question: show daily total load for meter 740-60-4283
SQL: SELECT DATE(datetime) as day, SUM(forecasted_load_kwh) as total_load FROM meter_table WHERE meter_id = '740-60-4283' GROUP BY DATE(datetime) ORDER BY day;

Question: show monthly average revenue
SQL: SELECT strftime('%Y-%m', Datetime) as month, AVG(Revenue) as avg_revenue FROM Revenue_data GROUP BY strftime('%Y-%m', Datetime) ORDER BY month;

Question: show revenue on 31-12-2011
SQL: SELECT substr(Datetime, 7, 4) || '-' || substr(Datetime, 4, 2) || '-' || substr(Datetime, 1, 2) as date, SUM(Revenue) as total_revenue, AVG(Revenue) as avg_revenue FROM Revenue_data WHERE substr(Datetime, 7, 4) || '-' || substr(Datetime, 4, 2) || '-' || substr(Datetime, 1, 2) = '2011-12-31' GROUP BY substr(Datetime, 7, 4) || '-' || substr(Datetime, 4, 2) || '-' || substr(Datetime, 1, 2);

Question: show weekly load and revenue together
SQL: SELECT strftime('%Y-W%W', m.datetime) as week, AVG(m.forecasted_load_kwh) as avg_load, AVG(r.Revenue) as avg_revenue FROM meter_table m LEFT JOIN Revenue_data r ON DATE(m.datetime) = DATE(r.Datetime) GROUP BY strftime('%Y-W%W', m.datetime) ORDER BY week;
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


def summarize_results(question: str, generated_sql: str, rows: List[Any], max_rows:int=50) -> str:
    # Enhanced context for aggregated results
    sql_context = ""
    sql_lower = generated_sql.lower()
    
    if "group by" in sql_lower:
        if "strftime('%Y-W%W'" in sql_lower:
            sql_context = " (weekly aggregation)"
        elif "strftime('%Y-%m'" in sql_lower:
            sql_context = " (monthly aggregation)"
        elif "strftime('%Y-%m-%d %H:" in sql_lower or "strftime('%H:00'" in sql_lower:
            sql_context = " (hourly aggregation)"
        elif "date(" in sql_lower or "strftime('%Y-%m-%d'" in sql_lower:
            sql_context = " (daily aggregation)"
    
    prompt = textwrap.dedent(f"""
    You are an assistant that summarizes SQL query results in natural language.
    Rules:
    - Produce a VERY concise summary (1-2 sentences MAXIMUM).
    - For aggregated data, mention the aggregation period (weekly, daily, monthly, hourly).
    - Highlight key metrics: averages, totals, trends.
    - Only mention the most important numeric values if relevant.
    - If rows are empty, return exactly: No results found.
    - Be brief and direct, avoid lengthy explanations.

    Question: {question}
    Query Type: {sql_context}
    Sample Results: {rows[:max_rows]}

    Summary (1-2 sentences):
    """).strip()

    try:
        resp = chat(model=MODEL, messages=[
            {"role": "system", "content": "You summarize SQL results into natural language. Be concise and highlight key metrics."},
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
