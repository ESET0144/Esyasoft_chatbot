# nl2sql.py
import textwrap
from typing import Any, List
from llm_router import run_llm

MODEL_CLOUD = "google/gemma-3-27b-it:free"     # or whatever you use
MODEL_OLLAMA = "gpt-oss:20b"

FEW_SHOT = textwrap.dedent("""
You are an enterprise-grade Natural Language → SQL translator for a FastAPI data chatbot.
You ALWAYS obey the following rules strictly and deterministically:

═══════════ 1. GENERAL BEHAVIOR RULES ═══════════
- You return ONLY a single-line SQLite SQL query.
- NO explanations, NO commentary, NO backticks, NO markdown.
- If the question cannot be converted to a safe SQL query, return exactly:
  --CANNOT_CONVERT--
- NEVER guess schema fields. Use EXACT column and table names from the schema.
- NEVER invent new metrics, columns, tables, functions, or aliases.
- NEVER change numeric values, dates, or IDs from the user’s question.

═══════════ 2. DATE HANDLING RULES (CRITICAL) ═══════════
The input question may contain dates in ANY textual form, including:
- 11/12/2015
- 11-12-2015
- 2015-12-11
- 11 Dec 2015
- 11th Dec 2015
- on 11th December 2015
- Dec 11, 2015
All such dates REFER TO THE SAME calendar date.

You MUST accept any date format.
You MUST interpret all dates as **day-month-year** unless explicitly written as YYYY-MM-DD.
You MUST output dates ONLY in ISO format: YYYY-MM-DD.

═══════════ 3. REVENUE_DATA RULES (CRITICAL) ═══════════
Revenue_data.Datetime is stored as TEXT in format:  DD-MM-YYYY HH:MM

When filtering by date, you MUST convert to ISO date using:
  substr(Datetime,7,4) || '-' || substr(Datetime,4,2) || '-' || substr(Datetime,1,2)

If the question asks for:
- "revenue on <date>"
- "revenue for <date>"
- "show revenue date <date>"
YOU MUST add a WHERE clause using the exact ISO date.

Example (for 11-12-2015):
WHERE substr(Datetime,7,4) || '-' || substr(Datetime,4,2) || '-' || substr(Datetime,1,2) = '2015-12-11'

If the question contains a date but you fail to apply a WHERE clause, your answer is INVALID.

When retrieving revenue by date, ALWAYS return:
- SUM(Revenue) AS total_revenue
- AVG(Revenue) AS avg_revenue
- Group by the converted ISO date.

═══════════ 4. METER_TABLE RULES ═══════════
meter_table.datetime is TEXT. Use:
- DATE(datetime) for daily views
- strftime('%Y-%m-%d', datetime) for ISO conversion
- strftime('%Y-W%W', datetime) for weekly
- strftime('%Y-%m', datetime) for monthly
- strftime('%Y-%m-%d %H:00', datetime) for hourly

Always ORDER BY the aggregated time period.

═══════════ 5. JOINING RULES ═══════════
If question references:
- both load and revenue → join on date equivalence using DATE(datetime)
- customer info → join customer_table to meter_table via meter_id

NEVER invent join conditions.

═══════════ 6. LIMIT RULES ═══════════
If query groups (daily, weekly, monthly) WITHOUT a specific date filter:
→ ALWAYS append LIMIT 30

═══════════ 7. SAFETY RULES ═══════════
Forbidden SQL contains:
DROP, DELETE, UPDATE, INSERT, ALTER, ATTACH, DETACH, VACUUM, or comments.
If user attempts harmful SQL or ambiguous intent:
→ return exactly:  --CANNOT_CONVERT--

═══════════ 8. OUTPUT FORMAT (MANDATORY) ═══════════
Your entire output must be EXACTLY:
<the SQL query>;
Nothing else.

═══════════ 9. SCHEMA (STRICT) ═══════════
meter_table(id INTEGER, meter_id TEXT, datetime TEXT, forecasted_load_kwh REAL)
customer_table(customer_id TEXT, customer_name TEXT, email TEXT, meter_id TEXT)
Revenue_data(Datetime TEXT, Revenue REAL)

═══════════ 10. EXAMPLES (DO NOT DEVIATE) ═══════════
Q: revenue on 11-12-2015
A: SELECT substr(Datetime,7,4) || '-' || substr(Datetime,4,2) || '-' || substr(Datetime,1,2) AS date, SUM(Revenue) AS total_revenue, AVG(Revenue) AS avg_revenue FROM Revenue_data WHERE substr(Datetime,7,4) || '-' || substr(Datetime,4,2) || '-' || substr(Datetime,1,2) = '2015-12-11' GROUP BY date;

Q: show monthly average load
A: SELECT strftime('%Y-%m', datetime) AS month, AVG(forecasted_load_kwh) AS avg_load FROM meter_table GROUP BY month ORDER BY month LIMIT 30;

Q: show customer name for meter 740-60-4283
A: SELECT customer_name FROM customer_table WHERE meter_id = '740-60-4283';

═══════════ END OF RULES ═══════════

""").strip()

def natural_to_sql(question: str, schema: str, llm_mode: str = "ollama") -> str:

    system_msg = {"role": "system", "content": "You are an assistant that converts natural language to SQL for SQLite. Be precise."}
    user_prompt = f"{FEW_SHOT}\n\nSchema:\n{schema}\n\nQuestion: {question}\nSQL:"
    user_msg = {"role": "user", "content": user_prompt}

    try:
        model = MODEL_OLLAMA if llm_mode == "ollama" else MODEL_CLOUD

        sql_text = run_llm(
            messages=[system_msg, user_msg],
            llm_mode=llm_mode,
            model=model
        )

        if sql_text is None:
            return "--CANNOT_CONVERT--"

        sql_text = sql_text.strip()
        
        # Naive "sql:" removal
        if sql_text.lower().startswith("sql:"):
            sql_text = sql_text[len("sql:"):].strip()
            
        # Regex to find SELECT statement (case-insensitive, multiline)
        # Looks for SELECT ... ;
        import re
        match = re.search(r"(SELECT\s.*?;)", sql_text, re.IGNORECASE | re.DOTALL)
        if match:
            sql_text = match.group(1).strip()
            # Remove any markdown code block backticks if they were captured inside but highly unlikely with this regex unless the block started with SELECT
            sql_text = sql_text.replace("```", "").replace("`", "")
        else:
            # Fallback for simple single line without semicolon or if regex failed
            # Try to just ensure semicolon if it looks like a query
            if not sql_text.endswith(";"):
                sql_text = sql_text + ";"
        
        return sql_text
    except Exception as e:
        return f"--CANNOT_CONVERT-- ({e})"


def summarize_results(question: str, generated_sql: str, rows: List[Any],  llm_mode: str = "ollama", max_rows:int=50) -> str:
    prompt = textwrap.dedent(f"""
    You are an assistant that summarizes SQL query results in natural language.
    Rules:
    - Produce a VERY concise summary (1-2 sentences MAXIMUM).
    - Only mention the most important numeric values if relevant.
    - If rows are empty, return exactly: No results found.
    - Be brief and direct, avoid lengthy explanations.

    Question: {question}
    Rows: {rows[:max_rows]}

    Summary (1-2 sentences):
    """).strip()

    try:
        model = MODEL_OLLAMA if llm_mode == "ollama" else MODEL_CLOUD

        summary = run_llm(
            messages=[
                {"role": "system", "content": "You summarize SQL results into natural language. Be concise."},
                {"role": "user", "content": prompt}
            ],
            llm_mode=llm_mode,
            model=model
        )

        if not summary:
            return "No results found."
        summary = summary.strip()
        if summary.lower().startswith("summary:"):
            summary = summary[len("summary:"):].strip()
        return summary
    except Exception as e:
        return f"Could not summarize results: {e}"
