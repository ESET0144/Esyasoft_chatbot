from typing import Tuple, List
from fastapi import HTTPException
import re

from nl2sql import natural_to_sql, summarize_results
from db import secure_run_query
from security import allowed_tables_for_role, extract_table_names


def is_greeting(text: str) -> bool:
    q = text.strip().lower()
    greetings = ["hi", "hello", "hey", "good morning", "good afternoon", "good evening", "are you there", "available"]
    return any(q == g or q.startswith(g + " ") or q.endswith(" " + g) for g in greetings)


def classify_intent(question: str) -> str:
    # Rule-based fallback classifier: explicit LLM-based classification can be plugged here
    q = question.lower()
    forecast_keywords = ["forecast", "predict", "projection", "future", "will be", "predict revenue", "forecast revenue"]
    if any(kw in q for kw in forecast_keywords):
        return "python_model"
    return "nl2sql"


def decide_output_type(question: str) -> str:
    q = question.lower()
    if any(w in q for w in ["plot", "graph", "chart", "trend", "over time", "time series"]):
        return "graph"
    if any(w in q for w in ["summary", "summarize", "explain", "what is", "how many", "average", "max", "min"]):
        return "nl"
    return "table"


def handle_nl2sql(question: str, role: str) -> dict:
    """Convert question -> SQL, authorize, execute, format result.

    IMPORTANT: Authorization is performed AFTER NL2SQL generates SQL but BEFORE it is executed.
    We extract table names from the generated SQL, validate against role policy, and block if unauthorized.
    """
    sql = natural_to_sql(question, "")  # schema is embedded in nl2sql; caller ensures safety
    if not sql or sql.startswith("--CANNOT_CONVERT--"):
        return {"error": "Could not convert question to SQL", "status_code": 400}

    # Defensively reject multiple statements (LLM hallucination risk)
    if sql.count(";") > 1:
        return {"error": "Multiple statements are not allowed", "status_code": 400}

    # Determine which tables appear in the SQL
    tables = extract_table_names(sql)
    allowed = allowed_tables_for_role(role)

    # Enforce role-based access — block if any table is outside allowed list
    for t in tables:
        if t in ("", "select", "from", "where", "join", "on"):
            continue
        if t not in allowed:
            return {"error": f"forbidden: role '{role}' cannot access table '{t}'", "status_code": 403, "table": t}

    # Execute in a secure, transactional way
    res = secure_run_query(sql, allowed)
    if res.get("error"):
        # Bubble up DB or authorization error
        # Map unauthorized_table to 403
        if res.get("error").startswith("unauthorized_table_access") or res.get("unauthorized_table"):
            return {"error": f"forbidden: role '{role}' cannot access table '{res.get('unauthorized_table')}'", "status_code": 403}
        return {"error": res.get("error"), "status_code": 400}

    rows = res.get("rows", [])
    cols = res.get("columns", [])

    return {
        "question": question,
        "intent": "nl2sql",
        "generated_sql": sql,
        "result": rows,
        "columns": cols,
        "ncols": len(cols),
        "output_type": decide_output_type(question),
        "summary": summarize_results(question, sql, rows)
    }
