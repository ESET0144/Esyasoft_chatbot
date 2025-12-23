from typing import Dict

def is_greeting(q: str) -> bool:
    return q.lower().strip() in ["hi", "hello", "hey"]

def classify_intent(q: str) -> str:
    if any(w in q.lower() for w in ["forecast", "predict"]):
        return "python_model"
    return "nl2sql"

def decide_output_type(q: str) -> str:
    if any(w in q.lower() for w in ["plot", "graph", "trend"]):
        return "graph"
    return "table"

def handle_nl2sql(question: str, role: str) -> Dict:
    # stub for now
    return {
        "question": question,
        "output_type": "nl",
        "summary": f"NL2SQL handled for role={role}",
        "result": [],
        "status_code": 200
    }
