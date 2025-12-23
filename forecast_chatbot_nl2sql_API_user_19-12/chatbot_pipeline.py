# chatbot_pipeline.py
import logging
from nl2sql import natural_to_sql, summarize_results
from db import run_query
import io
import base64
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from datetime import datetime

logger = logging.getLogger("chatbot")

# ---------- GREETING ----------
def is_greeting(q: str) -> bool:
    q = q.lower().strip()
    greetings = ["hi", "hello", "hey", "good morning", "good evening"]
    return any(q == g or q.startswith(g + " ") for g in greetings)


def greeting_response() -> str:
    return (
        "Hello 👋 How may I help you?\n"
        "• Ask about customers or meters\n"
        "• View load or revenue trends\n"
        "• Forecast future revenue"
    )


# ---------- INTENT ----------
def classify_intent(q: str) -> str:
    ql = q.lower()
    if any(w in ql for w in ["forecast", "predict", "projection", "future"]):
        return "python_model"
    return "nl2sql"


# ---------- NL2SQL ----------
# chatbot_pipeline.py
import re
import logging
from datetime import datetime as _dt

from nl2sql import natural_to_sql, summarize_results
from db import run_query
from security import allowed_tables_for_role

logger = logging.getLogger("chatbot")

def parse_datetime_safe(val):
    s = str(val)

    for fmt in (
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d %H:%M",
        "%Y-%m-%d",
        "%Y-%m",
    ):
        try:
            return datetime.strptime(s, fmt)
        except:
            pass

    # weekly buckets: YYYY-Wxx
    try:
        return datetime.strptime(s + "-1", "%Y-W%W-%w")
    except:
        pass

    return None

def render_graph_png(rows, columns):
    if not rows:
        return None

    # Detect datetime and numeric value columns
    datetime_idx = None
    value_idx = None

    for i, col in enumerate(columns):
        c = col.lower()
        if datetime_idx is None and ("date" in c or "time" in c):
            datetime_idx = i
        if value_idx is None and any(x in c for x in ["load", "mw", "kwh", "revenue"]):
            value_idx = i

    # Fallbacks
    if datetime_idx is None:
        datetime_idx = 0
    if value_idx is None:
        value_idx = len(columns) - 1

    dates, values = [], []

    for r in rows:
        try:
            dt = parse_datetime_safe(r[datetime_idx])
            if dt is None:
                continue
            val = float(r[value_idx])
            dates.append(dt)
            values.append(val)
        except Exception:
            continue

    if not dates or not values:
        return None

    # 🔽 Downsample (avoid stretched graphs)
    MAX_POINTS = 200
    if len(dates) > MAX_POINTS:
        step = len(dates) // MAX_POINTS
        dates = dates[::step]
        values = values[::step]

    # 🎨 Compact plot (NOT stretched)
    plt.figure(figsize=(8, 3))   # ← critical: compact width
    plt.plot(dates, values, linewidth=1.5)

    plt.xlabel("Time", fontsize=8)
    plt.ylabel(columns[value_idx], fontsize=8)
    plt.title("Trend", fontsize=10)

    plt.xticks(rotation=45, fontsize=7)
    plt.yticks(fontsize=7)
    plt.tight_layout()

    buf = io.BytesIO()
    plt.savefig(buf, format="png", dpi=120)
    plt.close()
    buf.seek(0)

    return base64.b64encode(buf.getvalue()).decode("utf-8")

