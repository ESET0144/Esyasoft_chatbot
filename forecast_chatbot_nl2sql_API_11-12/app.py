# app.py
import os
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
from nl2sql import natural_to_sql, summarize_results
from db import run_query
import os
import matplotlib
matplotlib.use("Agg")
from ollama import chat
import joblib
import pandas as pd
from datetime import datetime
import numpy as np

app = FastAPI()

# Keep schema consistent
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

# ============ INTENT CLASSIFIER ============
# Uses LLM to classify user intent into two main categories:
# 1) "nl2sql" - Query/analyze existing data from meter_table, customer_table, revenue_data
# 2) "python_model" - Forecast revenue using revenue_lr_model.joblib
def classify_intent(question: str) -> str:
    """
    Classifies user question into one of two intents:
    - "nl2sql": Data querying, analysis, and summary (scraps/summarizes existing data)
    - "python_model": Revenue forecasting/prediction using ML model
    
    Returns: "nl2sql" | "python_model"
    """
    MODEL = "gpt-oss:20b"
    
    prompt = f"""You are an intelligent intent classifier for a data analytics chatbot.

The chatbot has TWO capabilities:

1. NL2SQL - Query and analyze EXISTING data:
   - Queries customer data (names, emails, IDs)
   - Analyzes forecasted load data from meters (historical trends, patterns)
   - Analyzes historical revenue data (past revenue statistics)
   - Shows data in tables, graphs, or summaries
   - Keywords: "show", "display", "list", "plot", "graph", "trend", "what is", "how many", "average", "summary", "explain"

2. PYTHON_MODEL - FORECAST revenue using machine learning:
   - Predicts future revenue based on trained model
   - Only for FORWARD-LOOKING projections
   - Keywords: "forecast", "predict", "projection", "next", "future", "will be", "predict revenue", "forecast revenue"

Given a user question, classify it into ONE of these intents:

Question: {question}

Rules:
1. If question asks to FORECAST or PREDICT revenue → "python_model"
2. If question asks about FUTURE revenue projections → "python_model"
3. If question asks to QUERY, DISPLAY, or ANALYZE existing data → "nl2sql"
4. If question asks for trends, patterns, summaries of historical data → "nl2sql"
5. Default to "nl2sql" if ambiguous

Respond with ONLY one of: nl2sql or python_model"""
    
    try:
        resp = chat(model=MODEL, messages=[
            {"role": "system", "content": "You classify questions into nl2sql or python_model. Respond with only: nl2sql or python_model"},
            {"role": "user", "content": prompt}
        ], stream=False)
        
        result = ""
        if isinstance(resp, dict):
            msg = resp.get("message") or {}
            if isinstance(msg, dict):
                result = msg.get("content", "").strip().lower()
            else:
                result = str(resp).strip().lower()
        else:
            try:
                result = resp.message.content.strip().lower()
            except Exception:
                result = str(resp).strip().lower()
        
        # Validate and extract intent
        if "python_model" in result or "forecast" in result or "predict" in result:
            return "python_model"
        elif "nl2sql" in result or "query" in result or "sql" in result:
            return "nl2sql"
        else:
            return "nl2sql"  # Default fallback
    except Exception as e:
        # Fallback to rule-based if LLM fails
        q = question.lower()
        forecast_keywords = ["forecast", "predict", "projection", "future revenue", "next", "predict revenue", 
                            "forecast revenue", "how much will", "what will be", "predict next"]
        for kw in forecast_keywords:
            if kw in q:
                return "python_model"
        return "nl2sql"


# Returns 'graph' | 'table' | 'nl'
def decide_output_type(question: str) -> str:
    MODEL = "gpt-oss:20b"
    
    prompt = f"""You are an executive assistant (uses pyramid structure to give output) that classifies user questions about data into output types.

Given a user question, determine the BEST output type:
- "graph": User is asking for a visual trend, plot, chart, or time-series visualization (e.g., "show trend over time", "plot load", "chart revenue")
- "table": User is asking for structured data in rows/columns (e.g., "show customers", "list all entries", "give me details")
- "nl": User is asking for a summary, explanation, or aggregate metrics (e.g., "summarize", "explain", "how many", "what is the average")

Rules:
1. If question mentions visualization keywords (plot, graph, chart, trend, timeline, vs, over time, line), return "graph"
2. If question asks for structured display (show, list, entries, rows, display, table, select), return "table"
3. If question asks for explanations or metrics (summary, explain, what is, how many, average, max, min), return "nl"
4. If question mentions dates/time ranges for filtering, prefer "graph" unless it's a simple lookup
5. If customer/account info is needed for display, return "table"
6. Default to "table" if ambiguous

Question: {question}

Respond with ONLY one word: graph, table, or nl"""
    
    try:
        resp = chat(model=MODEL, messages=[
            {"role": "system", "content": "You classify questions into output types. Respond with only: graph, table, or nl"},
            {"role": "user", "content": prompt}
        ], stream=False)
        
        result = ""
        if isinstance(resp, dict):
            msg = resp.get("message") or {}
            if isinstance(msg, dict):
                result = msg.get("content", "").strip().lower()
            else:
                result = str(resp).strip().lower()
        else:
            try:
                result = resp.message.content.strip().lower()
            except Exception:
                result = str(resp).strip().lower()
        
        # Validate output
        if result in ["graph", "table", "nl"]:
            return result
        else:
            # Fallback to table if LLM returns something unexpected
            return "table"
    except Exception as e:
        # Fallback to rule-based if LLM fails
        q = question.lower()
        if any(w in q for w in ["plot", "graph", "chart", "vs", "over time", "trend", "timeline", "time series", "line"]):
            return "graph"
        if any(w in q for w in ["summary", "summarize", "explain", "what is", "tell me", "how many", "average", "max", "min"]):
            return "nl"
        return "table"

# A small whitelist check to avoid destructive SQL
def is_query_safe(sql: str) -> bool:
    forbidden = ["drop ", "delete ", "update ", "alter ", "attach ", "detach ", "vacuum", ";--", "--"]
    low = sql.lower()
    for f in forbidden:
        if f in low:
            return False
    return True


# ============ REVENUE FORECAST HANDLER ============
def forecast_revenue_from_model(question: str) -> dict:
    """
    Uses the pre-trained revenue_lr_model.joblib to forecast future revenue.
    Loads the model, extracts forecast horizon from question, and returns predictions.
    """
    import sqlite3
    import re
    
    try:
        # Load the pre-trained model
        if not os.path.exists("revenue_lr_model.joblib"):
            return {
                "error": "Revenue forecast model not found. Please train the model first.",
                "output_type": "error"
            }
        
        pipeline = joblib.load("revenue_lr_model.joblib")
        
        # Load revenue data from database
        conn = sqlite3.connect("forcast.db")
        try:
            df = pd.read_sql_query("SELECT Datetime, Revenue FROM Revenue_data ORDER BY Datetime", conn)
        finally:
            conn.close()
        
        if df.empty:
            return {
                "error": "No historical revenue data found in database.",
                "output_type": "error"
            }
        
        # Parse datetime with robust fallback
        def try_parse_dt(x):
            s = str(x)
            for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%d-%m-%Y %H:%M:%S", "%d-%m-%Y %H:%M", "%d-%m-%Y", "%Y-%m-%d"):
                try:
                    return datetime.strptime(s, fmt)
                except:
                    continue
            ts = pd.to_datetime(s, dayfirst=True, errors='coerce')
            if pd.isnull(ts):
                return None
            return ts.to_pydatetime()
        
        df['Datetime_parsed'] = df['Datetime'].apply(try_parse_dt)
        df = df.dropna(subset=['Datetime_parsed', 'Revenue']).copy()
        df['Revenue'] = pd.to_numeric(df['Revenue'], errors='coerce')
        df = df.dropna(subset=['Revenue'])
        df['Datetime_parsed'] = pd.to_datetime(df['Datetime_parsed'])
        df = df.sort_values('Datetime_parsed').reset_index(drop=True)
        
        # Parse forecast horizon from question
        horizon = 12  # default
        m = re.search(r'next\s+(\d+)\s*(years?|months?|weeks?|days?|hours?)', question.lower())
        if m:
            qty = int(m.group(1))
            unit = m.group(2).lower()
            if 'year' in unit:
                horizon = qty * 12
            elif 'month' in unit:
                horizon = qty
            elif 'week' in unit:
                horizon = qty * 4
            elif 'day' in unit:
                horizon = qty
            elif 'hour' in unit:
                horizon = qty
        
        # Determine frequency from data
        deltas = df['Datetime_parsed'].diff().dropna().map(lambda x: x.total_seconds())
        median_delta = deltas.median() if not deltas.empty else None
        
        if median_delta is None:
            freq = 'MS'
        elif median_delta <= 3600 + 1:
            freq = 'h'
        elif median_delta <= 86400 + 1:
            freq = 'D'
        else:
            freq = 'MS'
        
        # Create future dates and features
        last_dt = pd.to_datetime(df['Datetime_parsed'].iloc[-1])
        future_idx = pd.date_range(start=last_dt, periods=horizon + 1, freq=freq)[1:]
        future_df = pd.DataFrame({'Datetime_parsed': future_idx})
        
        # Make time features (same as in forecast_revenue_model.py)
        dt = pd.to_datetime(future_df['Datetime_parsed'])
        try:
            ts_vals = dt.astype('int64') // 10**9
        except:
            ts_vals = (dt.values.astype('datetime64[ns]').astype('int64')) // 10**9
        
        future_df['ts'] = ts_vals
        future_df['year'] = dt.dt.year
        future_df['month'] = dt.dt.month
        future_df['day'] = dt.dt.day
        future_df['hour'] = dt.dt.hour
        future_df['dayofweek'] = dt.dt.dayofweek
        future_df['month_sin'] = np.sin(2 * np.pi * future_df['month'] / 12.0)
        future_df['month_cos'] = np.cos(2 * np.pi * future_df['month'] / 12.0)
        future_df['dow_sin'] = np.sin(2 * np.pi * future_df['dayofweek'] / 7.0)
        future_df['dow_cos'] = np.cos(2 * np.pi * future_df['dayofweek'] / 7.0)
        
        # Make predictions
        features = ['ts', 'month_sin', 'month_cos', 'dow_sin', 'dow_cos']
        X_future = future_df[features].values
        preds = pipeline.predict(X_future)
        future_df['Predicted_Revenue'] = preds
        
        # Format results
        result_rows = future_df[['Datetime_parsed', 'Predicted_Revenue']].copy()
        result_rows['Datetime_parsed'] = result_rows['Datetime_parsed'].astype(str)
        result_rows.columns = ['Datetime', 'Predicted_Revenue']
        
        return {
            "question": question,
            "output_type": "forecast",
            "intent": "python_model",
            "horizon": horizon,
            "frequency": freq,
            "result": result_rows.to_dict(orient='records'),
            "ncols": 2,
            "columns": ["Datetime", "Predicted_Revenue"],
            "summary": f"Forecasted revenue for next {horizon} periods. Model used: Ridge Regression with temporal features."
        }
    
    except Exception as e:
        return {
            "error": f"Forecast generation failed: {str(e)}",
            "output_type": "error"
        }



# replace the existing ask(...) implementation in app.py with this
@app.post("/ask")
async def ask(request: Request):
    import re  # local import so function is self-contained
    body = await request.json()
    question = body.get("question") or ""
    if not question:
        return JSONResponse(status_code=422, content={"error": "question required"})

    # Quick greeting handler: respond directly for simple conversational queries
    q_lower = question.strip().lower()
    greetings = ["hi", "hello", "hey", "are you available", "are you there", "available", "good morning", "good evening", "good afternoon"]
    if any(q_lower == g or q_lower.startswith(g + " ") or q_lower.endswith(" " + g) or (g in q_lower and len(q_lower.split())<=3) for g in greetings):
      # Return a short natural-language reply instead of attempting SQL conversion
      return {
        "question": question,
        "output_type": "nl",
        "generated_sql": "",
        "result": [],
        "ncols": 0,
        "summary": "Hi — I'm here and ready to help. Ask me about the data or request a graph.",
        "include_table": False
      }

    # ============ INTENT CLASSIFICATION LAYER ============
    # Determine if user wants to query data (nl2sql) or forecast revenue (python_model)
    intent = classify_intent(question)
    
    # If user is asking for revenue forecast, use the ML model
    if intent == "python_model":
        forecast_result = forecast_revenue_from_model(question)
        return forecast_result
    
    # Otherwise, proceed with NL2SQL workflow
    # ============ NL2SQL WORKFLOW ============
    output_type = decide_output_type(question)

    generated_sql = natural_to_sql(question, SCHEMA)
    if generated_sql.startswith("--CANNOT_CONVERT--"):
        return JSONResponse(status_code=400, content={"error": "Could not convert question to SQL", "detail": generated_sql})

    lower_sql = generated_sql.lower()

    # --- JOIN HEURISTIC (customer lookup) ---
    if ("customer" in question.lower() or "email" in question.lower()) and "customer_table" not in lower_sql:
        mid = None
        m = re.search(r"meter_id\s*=\s*'([^']+)'", lower_sql)
        if m:
            mid = m.group(1)

        cid = None
        m2 = re.search(r"customer_id\s*=\s*'([^']+)'", lower_sql)
        if m2:
            cid = m2.group(1)

        if cid:
            generated_sql = (
                f"SELECT c.customer_id, c.customer_name, c.email, c.meter_id "
                f"FROM customer_table c WHERE c.customer_id = '{cid}';"
            )
        elif mid:
            generated_sql = (
                "SELECT c.customer_id, c.customer_name, c.email, m.datetime, m.forecasted_load_kwh "
                "FROM customer_table c "
                "LEFT JOIN meter_table m ON c.meter_id = m.meter_id "
                f"WHERE c.meter_id = '{mid}';"
            )
        else:
            generated_sql = (
                "SELECT c.customer_id, c.customer_name, c.email, m.datetime, m.forecasted_load_kwh "
                "FROM customer_table c "
                "LEFT JOIN meter_table m ON c.meter_id = m.meter_id "
                "LIMIT 200;"
            )

        # update lower_sql because we rewrote generated_sql
        lower_sql = generated_sql.lower()

    # --- GRAPH FALLBACK (ensure datetime/value present for plots) ---
    if output_type == "graph":
        if "datetime" not in lower_sql or "forecasted_load_kwh" not in lower_sql:
            generated_sql = "SELECT id, meter_id, datetime, forecasted_load_kwh FROM meter_table"
            m = re.search(r"where\s+meter_id\s*=\s*'([^']+)'", lower_sql)
            if m:
                mid = m.group(1)
                generated_sql += f" WHERE meter_id = '{mid}'"
            generated_sql += ";"
            lower_sql = generated_sql.lower()

    if not is_query_safe(generated_sql):
        return JSONResponse(status_code=400, content={"error": "Generated SQL is not allowed for safety."})

    rows_data = run_query(generated_sql)
    if isinstance(rows_data, dict) and rows_data.get("error"):
        return JSONResponse(status_code=400, content={"error": rows_data["error"], "generated_sql": generated_sql})

    # Extract rows and column names
    rows = rows_data["rows"]
    col_names = rows_data["columns"]
    # --- Fallback: handle cases where CSV headers ended up as data (e.g. 'Datetime')
    # If query was a MIN/MAX over datetime but returned non-datetime (like the string 'Datetime'),
    # recompute min/max ignoring non-date rows.
    try:
      from datetime import datetime as _dt
      needs_fix = False
      if rows and len(rows) > 0:
        first_row = rows[0]
        for i, val in enumerate(first_row):
          # If column name or value suggests a datetime but value is not parseable, mark for fix
          col_l = col_names[i].lower() if i < len(col_names) else ''
          val_s = str(val) if val is not None else ''
          if ('date' in col_l or 'time' in col_l or 'min' in col_l or 'max' in col_l) and val_s:
            try:
              _dt.fromisoformat(val_s)
            except Exception:
              # also treat header-like tokens as invalid (contain letters)
              if any(c.isalpha() for c in val_s):
                needs_fix = True
                break
      if needs_fix and ('min(' in generated_sql.lower() or 'max(' in generated_sql.lower()):
        # find table name from the generated SQL
        m_tab = re.search(r"from\s+([a-zA-Z0-9_]+)", generated_sql, re.IGNORECASE)
        if m_tab:
          table_name = m_tab.group(1)
          # pick a datetime-like column from SCHEMA if available
          dt_col = None
          m_schema = re.search(rf"{table_name}\s*\((.*?)\)", SCHEMA, re.DOTALL | re.IGNORECASE)
          if m_schema:
            cols_part = m_schema.group(1)
            # look for columns declared as TEXT that contain date/time
            candidates = re.findall(r"([A-Za-z0-9_]+)\s+TEXT", cols_part)
            for c in candidates:
              if 'date' in c.lower() or 'time' in c.lower():
                dt_col = c
                break
          if not dt_col:
            # fallback to common names
            if 'datetime' in generated_sql.lower():
              dt_col = 'datetime'
            else:
              dt_col = 'Datetime'

          # run a safe MIN/MAX that ignores non-numeric/date-like values
          try:
            fix_q = f"SELECT MIN({dt_col}), MAX({dt_col}) FROM {table_name} WHERE {dt_col} GLOB '[0-9]*';"
            fix_res = run_query(fix_q)
            if isinstance(fix_res, dict) and fix_res.get('error'):
              pass
            else:
              rows = fix_res.get('rows', rows)
              col_names = fix_res.get('columns', col_names)
          except Exception:
            pass
    except Exception:
      pass
    
    # infer ncols
    ncols = len(rows[0]) if rows else 0

    # ---- If graph requested, render compact PNG and return base64 image ----
    if output_type == "graph":
      try:
          import io, base64
          import matplotlib
          matplotlib.use("Agg")
          import matplotlib.pyplot as plt
          from datetime import datetime

          if not rows:
              return {
                  "question": question,
                  "output_type": "graph",
                  "generated_sql": generated_sql,
                  "result": rows,
                  "ncols": 0,
                  "columns": col_names,
                  "image": None
              }

          # --- Extract datetime + value ---
          dates = []
          values = []
          
          # Find datetime and numeric columns dynamically
          datetime_idx = None
          value_idx = None
          
          for i, col in enumerate(col_names):
              col_lower = col.lower()
              if 'datetime' in col_lower or 'date' in col_lower or 'time' in col_lower:
                  datetime_idx = i
              if 'load' in col_lower or 'mw' in col_lower or 'kwh' in col_lower:
                  value_idx = i
          
          # Fallback: use first datetime-like column and last numeric column
          if datetime_idx is None:
              for i, r in enumerate(rows):
                  if i < len(col_names):
                      try:
                          datetime.fromisoformat(str(r[i]))
                          datetime_idx = i
                          break
                      except:
                          pass
          
          if value_idx is None and len(col_names) > 0:
              value_idx = len(col_names) - 1
          
          if datetime_idx is None:
              datetime_idx = 0
          if value_idx is None:
              value_idx = 1
          
          # Extract data
          for r in rows:
              try:
                  dt = datetime.fromisoformat(str(r[datetime_idx]))
                  dates.append(dt)
                  values.append(float(r[value_idx]))
              except:
                  continue

          if not dates or not values:
              return {
                  "question": question,
                  "output_type": "graph",
                  "generated_sql": generated_sql,
                  "result": rows,
                  "ncols": len(rows[0]) if rows else 0,
                  "columns": col_names,
                  "image": None
              }

          # --- DOWNSAMPLE automatically ---
          MAX_POINTS = 200   # draw at MOST 200 data points
          if len(dates) > MAX_POINTS:
              step = len(dates) // MAX_POINTS
              dates = dates[::step]
              values = values[::step]

          # --- Plot clean compact graph ---
          plt.figure(figsize=(8, 3))
          plt.plot(dates, values, linewidth=1.5)

          plt.xlabel("Time", fontsize=8)
          plt.ylabel("Load (kWh)", fontsize=8)
          plt.title("Load Trend", fontsize=10)

          plt.xticks(fontsize=7, rotation=45)
          plt.yticks(fontsize=7)

          # Show approx 6 ticks max
          plt.gca().xaxis.set_major_locator(matplotlib.ticker.MaxNLocator(6))

          plt.tight_layout()

          # Convert → base64
          buf = io.BytesIO()
          plt.savefig(buf, format="png", dpi=120)
          plt.close()
          buf.seek(0)
          img_b64 = base64.b64encode(buf.getvalue()).decode("utf-8")

          return {
              "question": question,
              "output_type": "graph",
              "generated_sql": generated_sql,
              "result": rows,
              "ncols": len(rows[0]),
              "columns": col_names,
              "image": img_b64
          }

      except Exception as e:
          return JSONResponse(
              status_code=500,
              content={"error": f"Graph rendering failed: {e}", "generated_sql": generated_sql}
          )

    # ---- Non-graph outputs: Always summarize first, then optionally show table ----
    response = {
        "question": question,
        "output_type": "nl",  # Always use nl (summary) as primary output
        "generated_sql": generated_sql,
        "result": rows,
        "ncols": ncols,
        "columns": col_names
    }

    # Generate summary
    response["summary"] = summarize_results(question, generated_sql, rows)
    
    # Include table data as well for reference
    response["include_table"] = True

    return response


#---------- Frontend (single-file HTML) ----------
INDEX_HTML = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width,initial-scale=1" />
  <title>Forecast Chat — Chat UI</title>
  <style>
    html,body { height:100%; margin:0; }
    body { font-family: system-ui, -apple-system, "Segoe UI", Roboto, Arial; background:#f3f4f6; display:flex; flex-direction:column; }
    .container { max-width:1000px; margin:0 auto; width:100%; display:flex; flex-direction:column; flex:1; }
    .card { background:white; margin:16px; padding:18px; border-radius:12px; box-shadow:0 6px 18px rgba(0,0,0,0.06); flex:1; overflow:auto; display:flex; flex-direction:column; }
    .chat { margin-top:8px; display:flex; flex-direction:column; gap:10px; padding-bottom:140px; } /* padding-bottom for sticky input */
    .msg { max-width:80%; padding:10px 12px; border-radius:12px; }
    .user { align-self:flex-end; background:#ede9fe; color:#111827; border-bottom-right-radius:4px; }
    .assistant { align-self:flex-start; background:#0f172a; color:#e6eef8; border-bottom-left-radius:4px; }
    .sql { background:#111827; color:#e6eef8; padding:10px; border-radius:8px; overflow:auto; font-family:monospace; font-size:13px; margin-top:8px; }
    table { width:100%; border-collapse:collapse; margin-top:8px; }
    th, td { padding:8px 10px; border-bottom:1px solid #e6eef8; text-align:left; }
    .muted { color:#6b7280; font-size:13px; }
    canvas { width:100%; max-height:360px; height:360px; margin-top:12px; display:block; }
    .footer { position: fixed; left: 0; right: 0; bottom: 0; background: rgba(255,255,255,0.98); border-top: 1px solid #e6eef8; padding: 10px; display:flex; justify-content:center; z-index: 999; }
    .controls { width:100%; max-width:1000px; display:flex; gap:8px; align-items:center; }
    textarea { flex:1; min-height:48px; padding:10px; border-radius:8px; border:1px solid #e5e7eb; font-size:14px; resize:none; }
    button { padding:10px 14px; border-radius:8px; border:none; background:#6d28d9; color:white; cursor:pointer; }
    button:disabled { background:#9333ea; cursor:not-allowed; opacity:0.7; }
  </style>
  <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
</head>
<body>
  <div class="container">
    <div class="card" id="mainCard">
      <h2>Forecast Chat (chat history)</h2>
      <div class="muted">Ask questions naturally. The system will auto-detect whether to show a table, graph or summary.</div>

      <div id="chat" class="chat"></div>
    </div>
  </div>

  <div class="footer">
    <div class="controls">
      <textarea id="q" placeholder="Ask something...">show unique customers</textarea>
      <button id="sendBtn">Send</button>
      <button id="clearBtn">Clear</button>
    </div>
  </div>

<script>
const chatEl = document.getElementById('chat');
const qEl = document.getElementById('q');
const sendBtn = document.getElementById('sendBtn');
const clearBtn = document.getElementById('clearBtn');
const history = [];

function renderChat() {
  chatEl.innerHTML = '';
  for (const m of history) {
    const d = document.createElement('div');
    d.className = 'msg ' + (m.role === 'user' ? 'user' : 'assistant');
    if (m.role === 'user') {
      d.textContent = m.text;
    } else {
      const header = document.createElement('div');
      header.style.fontSize = '13px';
      header.style.marginBottom = '6px';
      header.textContent = m.meta && m.meta.output_type ? `Assistant (${m.meta.output_type})` : 'Assistant';
      d.appendChild(header);

      if (m.meta && m.meta.generated_sql) {
        const pre = document.createElement('pre');
        pre.className = 'sql';
        pre.textContent = m.meta.generated_sql;
        d.appendChild(pre);
      }

      if (m.meta && (m.meta.output_type === 'nl' || m.meta.output_type === 'forecast') && m.meta.summary) {
        const p = document.createElement('div');
        p.style.marginTop = '8px';
        p.style.fontWeight = 'bold';
        p.textContent = m.meta.summary;
        d.appendChild(p);
      }

      if (m.meta && m.meta.include_table) {
        const rows = m.meta.result || [];
        if (rows.length > 0) {
          const tableLabel = document.createElement('div');
          tableLabel.style.marginTop = '12px';
          tableLabel.style.fontSize = '12px';
          tableLabel.style.color = '#9ca3af';
          tableLabel.textContent = 'Data Table:';
          d.appendChild(tableLabel);
          
          const tbl = document.createElement('table');
          const thead = document.createElement('thead');
          const columns = m.meta.columns || [];
          let headerHtml = '<tr>';
          if (columns.length > 0) {
            for (let i = 0; i < columns.length; i++) {
              headerHtml += '<th>' + escapeHtml(columns[i]) + '</th>';
            }
          } else {
            const ncols = rows[0] ? rows[0].length : 0;
            for (let i = 0; i < ncols; i++) {
              headerHtml += '<th>Col ' + (i+1) + '</th>';
            }
          }
          headerHtml += '</tr>';
          thead.innerHTML = headerHtml;
          tbl.appendChild(thead);
          const tbody = document.createElement('tbody');
          for (const r of rows) {
            const tr = document.createElement('tr');
            let cellHtml = '';
            for (let i = 0; i < r.length; i++) {
              cellHtml += `<td>${escapeHtml(r[i] ?? '')}</td>`;
            }
            tr.innerHTML = cellHtml;
            tbody.appendChild(tr);
          }
          tbl.appendChild(tbody);
          d.appendChild(tbl);
        }
      }

      if (m.meta && m.meta.output_type === 'forecast') {
        const rows = m.meta.result || [];
        if (rows.length > 0) {
          const tableLabel = document.createElement('div');
          tableLabel.style.marginTop = '12px';
          tableLabel.style.fontSize = '12px';
          tableLabel.style.color = '#9ca3af';
          tableLabel.textContent = 'Forecast Results:';
          d.appendChild(tableLabel);
          
          const tbl = document.createElement('table');
          const thead = document.createElement('thead');
          const columns = m.meta.columns || ['Datetime', 'Predicted_Revenue'];
          let headerHtml = '<tr>';
          for (let i = 0; i < columns.length; i++) {
            headerHtml += '<th>' + escapeHtml(columns[i]) + '</th>';
          }
          headerHtml += '</tr>';
          thead.innerHTML = headerHtml;
          tbl.appendChild(thead);
          const tbody = document.createElement('tbody');
          for (const r of rows) {
            const tr = document.createElement('tr');
            let cellHtml = '';
            // Handle both array and object row formats
            if (Array.isArray(r)) {
              for (let i = 0; i < r.length; i++) {
                cellHtml += `<td>${escapeHtml(r[i] ?? '')}</td>`;
              }
            } else {
              // Object format (dict from python)
              for (const col of columns) {
                const val = r[col] ?? '';
                cellHtml += `<td>${escapeHtml(val)}</td>`;
              }
            }
            tr.innerHTML = cellHtml;
            tbody.appendChild(tr);
          }
          tbl.appendChild(tbody);
          d.appendChild(tbl);
        }
      }

      if (m.meta && m.meta.output_type === 'graph') {
        const rows = m.meta.result || [];
        if (rows.length > 0 && m.meta.image) {
          const imgContainer = document.createElement('div');
          imgContainer.style.marginTop = '8px';
          imgContainer.style.maxWidth = '100%';
          const img = document.createElement('img');
          img.src = 'data:image/png;base64,' + m.meta.image;
          img.style.maxWidth = '100%';
          img.style.height = 'auto';
          img.style.borderRadius = '8px';
          imgContainer.appendChild(img);
          d.appendChild(imgContainer);
        } else {
          const note = document.createElement('div'); 
          note.className='muted'; 
          note.textContent = 'No data to plot.'; 
          d.appendChild(note);
        }
      }
    }
    chatEl.appendChild(d);
  }
  chatEl.scrollTop = chatEl.scrollHeight;
}

function escapeHtml(s) {
  return String(s || '').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
}

sendBtn.onclick = async () => {
  const question = qEl.value.trim();
  if (!question) return;
  history.push({ role:'user', text: question });
  renderChat();

  // Set loading state
  sendBtn.disabled = true;
  sendBtn.textContent = 'Loading...';
  const originalBtnText = 'Send';

  try {
    const res = await fetch('/ask', {
      method: 'POST',
      headers: {'Content-Type':'application/json'},
      body: JSON.stringify({ question })
    });
    if (!res.ok) {
      const err = await res.json().catch(()=>({error:'unknown'}));
      history.push({ role:'assistant', text:'Error: ' + (err.error || JSON.stringify(err)), meta:{ output_type:'error' }});
      renderChat();
      return;
    }
    const data = await res.json();
    history.push({ role:'assistant', text:'', meta: data });
    renderChat();

    // No need to call renderChartFromData anymore - graph is embedded in chat message
  } catch (e) {
    history.push({ role:'assistant', text:'Request failed: ' + String(e), meta:{ output_type:'error' }});
    renderChat();
  } finally {
    qEl.value = '';
    sendBtn.disabled = false;
    sendBtn.textContent = originalBtnText;
  }
};

clearBtn.onclick = () => {
  history.length = 0;
  renderChat();
};

renderChat();
</script>
</body>
</html>
"""


@app.get("/", response_class=HTMLResponse)
def index():
    return HTMLResponse(INDEX_HTML)
