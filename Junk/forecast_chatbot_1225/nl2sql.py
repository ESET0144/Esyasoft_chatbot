# nl2sql.py
from ollama import chat, Client
import os
import textwrap

# Optional: If Ollama runs on a different host/port, use a custom client:
# client = Client(host="http://localhost:11434")
# Then call client.chat(...)
# For the default local server, the top-level chat() helper works.

MODEL = "gemma3"   # or "codeup" or "llama3" — whichever you pulled

# A short few-shot prompt to improve SQL correctness.
# Keep it strict: ONLY return the SQL statement, nothing else.
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
    Convert a natural language question to a SQL string using a local Ollama model.
    Returns the SQL (string) or the special token '--CANNOT_CONVERT--' if model couldn't.
    """
    # Build the chat message list (system + user). Keep system short and strict.
    system_msg = {
        "role": "system",
        "content": "You are an assistant that converts natural language to SQL for SQLite. Be precise."
    }

    user_prompt = f"{FEW_SHOT}\n\nSchema:\n{schema}\n\nQuestion: {question}\nSQL:"
    # user message
    user_msg = {"role": "user", "content": user_prompt}

    # Use the convenience chat() function:
    try:
        response = chat(model=MODEL, messages=[system_msg, user_msg], stream=False)
        # The response structure has 'message' or 'message.content' depending on version.
        # We try to read both safely.
        sql_text = None
        if isinstance(response, dict):
            # response may have 'message' or 'message' object
            msg = response.get("message") or response.get("message", {})
            if isinstance(msg, dict):
                sql_text = msg.get("content") or msg.get("content", "")
            else:
                # fallback
                sql_text = str(response)
        else:
            # object with attribute access
            try:
                sql_text = response.message.content
            except Exception:
                sql_text = str(response)

        if sql_text is None:
            return "--CANNOT_CONVERT--"

        # Clean result: strip whitespace and remove any leading/trailing non-SQL text.
        sql_text = sql_text.strip()

        # Sometimes model adds "SQL:" prefix — remove it
        if sql_text.lower().startswith("sql:"):
            sql_text = sql_text[len("sql:"):].strip()

        # Ensure it ends with semicolon for sqlite (optional)
        if not sql_text.endswith(";"):
            sql_text = sql_text + ";"

        return sql_text
    except Exception as e:
        # If model not present, instruct caller to pull model
        return f"--CANNOT_CONVERT-- ({str(e)})"
