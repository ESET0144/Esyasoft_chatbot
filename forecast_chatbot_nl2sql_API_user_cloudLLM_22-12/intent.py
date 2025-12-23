# intent.py
from ollama import chat

MODEL = "gpt-oss:20b"

def classify_intent(question: str) -> str:
    prompt = f"""
You are an intelligent intent classifier for a data analytics chatbot.

The chatbot has TWO capabilities:

1. NL2SQL - Query and analyze EXISTING data:
   - Queries customer data (names, emails, IDs)
   - Analyzes forecasted load data from meters
   - Analyzes historical revenue data
   - Shows tables, graphs, or summaries
   - Keywords: show, display, list, plot, graph, trend,
     what is, how many, average, summary, explain

2. PYTHON_MODEL - FORECAST revenue using machine learning:
   - Predicts future revenue
   - Only for FORWARD-LOOKING projections
   - Keywords: forecast, predict, projection, next, future

Question: {question}

Rules:
- Forecast / predict → python_model
- Otherwise → nl2sql

Respond with ONLY one word: nl2sql or python_model
"""

    try:
        resp = chat(
            model=MODEL,
            messages=[{"role": "user", "content": prompt}],
            stream=False,
        )
        result = resp["message"]["content"].strip().lower()

        if "python_model" in result:
            return "python_model"
        return "nl2sql"

    except Exception:
        if any(k in question.lower() for k in ["forecast", "predict", "future"]):
            return "python_model"
        return "nl2sql"
