# app.py
import os
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
from typing import List
from nl2sql import natural_to_sql, summarize_results
from db import run_query
import os
import io
import tempfile
import wave
import json
from fastapi import UploadFile, File, HTTPException
from fastapi import BackgroundTasks
import re
import matplotlib
matplotlib.use("Agg")

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

# Simple heuristic to pick output type based on question words.
# Returns 'graph' | 'table' | 'nl'
def decide_output_type(question: str) -> str:
    q = question.lower()
    
    # Explicit format requests take highest priority
    if "table form" in q or "table" in q or "in table" in q or "show table" in q or "display table" in q:
        return "table"
    if "graph" in q or "chart" in q or "plot" in q or "visualization" in q:
        return "graph"
    
    graph_words = ["vs", "over time", "trend", "timeline", "time series", "show trend", "line"]
    table_words = ["show", "list", "entries", "rows", "display", "all entries", "select", "give me", "find"]
    nl_words = ["summary", "summarize", "explain", "what is", "tell me", "how many", "average", "max", "min", "mean", "median", "total"]
    customer_words = ["customer", "customer_name", "customer_id", "email"]

    for w in graph_words:
        if w in q:
            return "graph"
    for w in customer_words:
        if w in q:
            if any(x in q for x in nl_words):
                return "nl"
            return "table"
    for w in nl_words:
        if w in q:
            return "nl"
    for w in table_words:
        if w in q:
            return "table"
    if "date" in q or "time" in q or "between" in q:
        return "graph"
    return "table"

# Helper function to create date comparison that handles various datetime formats
def get_date_comparison(column_name: str, date_value: str, is_revenue: bool = False) -> str:
    """
    Returns SQL fragment for date comparison that handles various datetime formats.
    For Revenue_data (DD-MM-YYYY HH:MM format), use string manipulation.
    For other tables, use strftime.
    """
    if is_revenue:
        # Revenue_data is stored as DD-MM-YYYY HH:MM, convert to YYYY-MM-DD for comparison
        return f"substr({column_name}, 7, 4) || '-' || substr({column_name}, 4, 2) || '-' || substr({column_name}, 1, 2) = '{date_value}'"
    else:
        # For other datetime formats, use strftime
        return f"strftime('%Y-%m-%d', {column_name}) = '{date_value}'"

def get_date_join_condition(meter_col: str, revenue_col: str) -> str:
    """
    Returns SQL JOIN condition for matching dates between meter_table and Revenue_data.
    Handles format conversion for Revenue_data (DD-MM-YYYY HH:MM).
    """
    # Convert meter datetime to YYYY-MM-DD and Revenue to YYYY-MM-DD for comparison
    return f"strftime('%Y-%m-%d', {meter_col}) = substr({revenue_col}, 7, 4) || '-' || substr({revenue_col}, 4, 2) || '-' || substr({revenue_col}, 1, 2)"

# A small whitelist check to avoid destructive SQL
def is_query_safe(sql: str) -> bool:
    forbidden = ["drop ", "delete ", "update ", "alter ", "attach ", "detach ", "vacuum", ";--", "--"]
    low = sql.lower()
    for f in forbidden:
        if f in low:
            return False
    return True



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

    output_type = decide_output_type(question)

    generated_sql = natural_to_sql(question, SCHEMA)
    if generated_sql.startswith("--CANNOT_CONVERT--"):
        return JSONResponse(status_code=400, content={"error": "Could not convert question to SQL", "detail": generated_sql})

    lower_sql = generated_sql.lower()

    # --- INTELLIGENT QUERY ROUTING (multi-table joins) ---
    q_lower = question.lower()
    needs_customer = any(term in q_lower for term in ["customer", "email", "customer_name", "customer_id"])
    needs_meter = any(term in q_lower for term in ["load", "kwh", "forecasted", "meter"])
    needs_revenue = any(term in q_lower for term in ["revenue", "revenue_data"])
    
    # Extract identifiers from query
    customer_id = None
    meter_id = None
    date_filter = None
    
    m_cid = re.search(r"customer[_\s]*id\s*[:\s=]*'?([^',\s]+)'?", q_lower)
    if m_cid:
        customer_id = m_cid.group(1)
    
    m_mid = re.search(r"meter[_\s]*id\s*[:\s=]*'?([^',\s]+)'?", q_lower)
    if m_mid:
        meter_id = m_mid.group(1)
    
    # Extract date in multiple formats: DD-MM-YYYY or YYYY-MM-DD
    m_date_iso = re.search(r"(?:at|on)\s+([0-9]{4}-[0-9]{2}-[0-9]{2})", q_lower)
    m_date_dmy = re.search(r"(?:at|on)\s+([0-9]{1,2}-[0-9]{1,2}-[0-9]{4})", q_lower)
    
    if m_date_iso:
        date_filter = m_date_iso.group(1)  # Already YYYY-MM-DD format
    elif m_date_dmy:
        # Convert DD-MM-YYYY to YYYY-MM-DD
        date_str = m_date_dmy.group(1)
        parts = date_str.split('-')
        if len(parts) == 3:
            try:
                day, month, year = parts[0], parts[1], parts[2]
                date_filter = f"{year}-{month.zfill(2)}-{day.zfill(2)}"
            except:
                date_filter = None
    
    # CASE 1: Customer → Meter → Load + Revenue (three-table join)
    if needs_customer and (needs_meter or needs_revenue):
        if customer_id:
            # Customer specified: get all load and revenue data for this customer
            query_parts = [
                "SELECT c.customer_id, c.customer_name, c.email, m.datetime, m.forecasted_load_kwh, r.Revenue "
            ]
            query_parts.append(
                "FROM customer_table c "
                "LEFT JOIN meter_table m ON c.meter_id = m.meter_id "
                f"LEFT JOIN Revenue_data r ON {get_date_join_condition('m.datetime', 'r.Datetime')} "
            )
            query_parts.append(f"WHERE c.customer_id = '{customer_id}' ")
            
            if date_filter:
                query_parts.append(f"AND {get_date_comparison('m.datetime', date_filter)} ")
            
            query_parts.append("ORDER BY m.datetime;")
            generated_sql = "".join(query_parts)
        
        elif meter_id:
            # Meter specified: get load + revenue at that date
            query_parts = [
                "SELECT c.customer_id, c.customer_name, c.email, m.datetime, m.forecasted_load_kwh, r.Revenue "
            ]
            query_parts.append(
                "FROM customer_table c "
                "LEFT JOIN meter_table m ON c.meter_id = m.meter_id "
                f"LEFT JOIN Revenue_data r ON {get_date_join_condition('m.datetime', 'r.Datetime')} "
            )
            query_parts.append(f"WHERE c.meter_id = '{meter_id}' ")
            
            if date_filter:
                query_parts.append(f"AND {get_date_comparison('m.datetime', date_filter)} ")
            
            query_parts.append("ORDER BY m.datetime;")
            generated_sql = "".join(query_parts)
        
        else:
            # No specific ID: return sample data with all three tables
            generated_sql = (
                "SELECT c.customer_id, c.customer_name, c.email, m.datetime, m.forecasted_load_kwh, r.Revenue "
                "FROM customer_table c "
                "LEFT JOIN meter_table m ON c.meter_id = m.meter_id "
                f"LEFT JOIN Revenue_data r ON {get_date_join_condition('m.datetime', 'r.Datetime')} "
                "LIMIT 200;"
            )
        
        lower_sql = generated_sql.lower()
    
    # CASE 2: Meter + Revenue only (no customer)
    elif needs_meter and needs_revenue and not needs_customer:
        if meter_id:
            # Check aggregation type from question
            agg_period = None
            if "weekly" in q_lower:
                agg_period = "week"
                date_group = "strftime('%Y-W%W', m.datetime)"
            elif "monthly" in q_lower:
                agg_period = "month"
                date_group = "strftime('%Y-%m', m.datetime)"
            elif "hourly" in q_lower:
                agg_period = "hour"
                date_group = "strftime('%Y-%m-%d %H:00', m.datetime)"
            else:  # default to daily
                agg_period = "day"
                date_group = "DATE(m.datetime)"
            
            generated_sql = (
                f"SELECT {date_group} as period, AVG(m.forecasted_load_kwh) as avg_load, AVG(r.Revenue) as avg_revenue "
                "FROM meter_table m "
                f"LEFT JOIN Revenue_data r ON {get_date_join_condition('m.datetime', 'r.Datetime')} "
                f"WHERE m.meter_id = '{meter_id}' "
                f"GROUP BY {date_group} "
                f"ORDER BY period;"
            )
        else:
            # No specific meter, show overall trend
            generated_sql = (
                "SELECT DATE(m.datetime) as day, AVG(m.forecasted_load_kwh) as avg_load, AVG(r.Revenue) as avg_revenue "
                "FROM meter_table m "
                f"LEFT JOIN Revenue_data r ON {get_date_join_condition('m.datetime', 'r.Datetime')} "
                "GROUP BY DATE(m.datetime) "
                "ORDER BY day;"
            )
        
        lower_sql = generated_sql.lower()
    
    # --- REVENUE ONLY (no customer or meter) ---
    elif needs_revenue and not needs_customer and not needs_meter:
        # Check if asking for specific date or overall trend
        if date_filter:
            # Specific date: return total/sum of revenue for that day
            query_parts = [
                "SELECT substr(Datetime, 7, 4) || '-' || substr(Datetime, 4, 2) || '-' || substr(Datetime, 1, 2) as date, "
                "SUM(Revenue) as total_revenue, AVG(Revenue) as avg_revenue, COUNT(*) as record_count "
                "FROM Revenue_data "
            ]
            query_parts.append(f"WHERE {get_date_comparison('Datetime', date_filter, is_revenue=True)} ")
            query_parts.append("GROUP BY substr(Datetime, 7, 4) || '-' || substr(Datetime, 4, 2) || '-' || substr(Datetime, 1, 2);")
        else:
            # No specific date: return daily aggregate trend
            query_parts = [
                "SELECT substr(Datetime, 7, 4) || '-' || substr(Datetime, 4, 2) || '-' || substr(Datetime, 1, 2) as date, "
                "SUM(Revenue) as total_revenue, AVG(Revenue) as avg_revenue "
                "FROM Revenue_data "
                "GROUP BY substr(Datetime, 7, 4) || '-' || substr(Datetime, 4, 2) || '-' || substr(Datetime, 1, 2) "
                "ORDER BY date;"
            ]
        
        generated_sql = "".join(query_parts)
        lower_sql = generated_sql.lower()
    elif needs_customer and "customer_table" not in lower_sql:
        if customer_id:
            generated_sql = (
                f"SELECT c.customer_id, c.customer_name, c.email, c.meter_id "
                f"FROM customer_table c WHERE c.customer_id = '{customer_id}';"
            )
        elif meter_id:
            generated_sql = (
                "SELECT c.customer_id, c.customer_name, c.email, m.datetime, m.forecasted_load_kwh "
                "FROM customer_table c "
                "LEFT JOIN meter_table m ON c.meter_id = m.meter_id "
                f"WHERE c.meter_id = '{meter_id}' "
                "ORDER BY m.datetime;"
            )
        else:
            generated_sql = (
                "SELECT c.customer_id, c.customer_name, c.email, m.datetime, m.forecasted_load_kwh "
                "FROM customer_table c "
                "LEFT JOIN meter_table m ON c.meter_id = m.meter_id "
                "LIMIT 200;"
            )
        
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
    
    # --- DATETIME & AGGREGATION DETECTION ---
    # Check if query includes aggregations (weekly, daily, monthly, hourly)
    is_aggregated = any(agg in lower_sql for agg in ["group by", "avg(", "sum(", "count(", "min(", "max("])
    has_datetime = any(term in lower_sql for term in ["datetime", "date(", "strftime"])
    
    # Detect aggregation granularity
    agg_type = None
    if "strftime('%Y-W%W'" in lower_sql or "strftime('%Y-W" in lower_sql:
        agg_type = "weekly"
    elif "strftime('%Y-%m'" in lower_sql:
        agg_type = "monthly"
    elif "strftime('%Y-%m-%d %H:" in lower_sql or "strftime('%H:00'" in lower_sql:
        agg_type = "hourly"
    elif "date(" in lower_sql or "strftime('%Y-%m-%d'" in lower_sql:
        agg_type = "daily"
    
    # Format datetime values in results for better readability
    if rows and col_names:
        from datetime import datetime as dt
        formatted_rows = []
        for row in rows:
            formatted_row = []
            for i, val in enumerate(row):
                col_name_lower = col_names[i].lower() if i < len(col_names) else ""
                
                # Try to parse and format datetime columns
                if val and isinstance(val, str) and any(t in col_name_lower for t in ["date", "time", "week", "month", "hour", "day"]):
                    try:
                        # Try ISO format first
                        parsed_dt = dt.fromisoformat(val)
                        
                        # Format based on aggregation type
                        if agg_type == "weekly" and "week" in col_name_lower:
                            # Keep week identifier as-is (YYYY-Www format)
                            formatted_row.append(val)
                        elif agg_type == "monthly" and "month" in col_name_lower:
                            # Format: YYYY-MM
                            formatted_row.append(val)
                        elif agg_type == "hourly" and "hour" in col_name_lower:
                            # Format: YYYY-MM-DD HH:00
                            formatted_row.append(val)
                        elif agg_type == "daily" or "day" in col_name_lower:
                            # Format as YYYY-MM-DD
                            formatted_row.append(parsed_dt.strftime("%Y-%m-%d"))
                        else:
                            # Default: full datetime
                            formatted_row.append(parsed_dt.strftime("%Y-%m-%d %H:%M:%S"))
                    except:
                        formatted_row.append(val)
                else:
                    formatted_row.append(val)
            
            formatted_rows.append(formatted_row)
        
        rows = formatted_rows
    
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
              if 'datetime' in col_lower or 'date' in col_lower or 'time' in col_lower or 'week' in col_lower or 'month' in col_lower or 'hour' in col_lower or 'day' in col_lower:
                  datetime_idx = i
              if 'load' in col_lower or 'mw' in col_lower or 'kwh' in col_lower or 'revenue' in col_lower or 'avg' in col_lower or 'sum' in col_lower or 'total' in col_lower:
                  value_idx = i
          
          # Fallback: use first datetime-like column and last numeric column
          if datetime_idx is None:
              for i, r in enumerate(rows):
                  if i < len(col_names):
                      try:
                          # Try parsing as various datetime formats
                          val_str = str(r[i])
                          if len(val_str) >= 10:  # Minimum date length (YYYY-MM-DD)
                              datetime.fromisoformat(val_str.split()[0])  # Try just date part
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
          
          # Extract data with proper datetime parsing
          for r in rows:
              try:
                  dt_str = str(r[datetime_idx])
                  val_num = float(r[value_idx])
                  
                  # Parse different datetime formats
                  try:
                      # Try ISO format (YYYY-MM-DD or YYYY-MM-DD HH:MM:SS)
                      parsed_dt = datetime.fromisoformat(dt_str)
                  except:
                      try:
                          # Try week format (YYYY-Www)
                          if 'W' in dt_str and len(dt_str) == 8:
                              year, week = dt_str.split('-W')
                              parsed_dt = datetime.strptime(f"{year}-W{week}-1", "%Y-W%W-%w")
                          else:
                              # Try simple date format
                              parsed_dt = datetime.strptime(dt_str[:10], "%Y-%m-%d")
                      except:
                          continue
                  
                  dates.append(parsed_dt)
                  values.append(val_num)
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

      if (m.meta && m.meta.output_type === 'nl' && m.meta.summary) {
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
