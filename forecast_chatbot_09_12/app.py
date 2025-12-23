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
)
"""

# Simple heuristic to pick output type based on question words.
# Returns 'graph' | 'table' | 'nl'
def decide_output_type(question: str) -> str:
    q = question.lower()
    graph_words = ["plot", "graph", "chart", "vs", "over time", "trend", "timeline", "time series", "show trend", "line"]
    table_words = ["show", "list", "entries", "rows", "display", "table", "all entries", "select", "give me", "find"]
    nl_words = ["summary", "summarize", "explain", "what is", "tell me", "how many", "average", "max", "min", "mean", "median"]
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
    body = await request.json()
    question = body.get("question") or ""
    if not question:
        return JSONResponse(status_code=422, content={"error": "question required"})

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

    # --- GRAPH FALLBACK ---
    if output_type == "graph":
        if "datetime" not in lower_sql or "forecasted_load_kwh" not in lower_sql:
            generated_sql = "SELECT id, meter_id, datetime, forecasted_load_kwh FROM meter_table"
            m = re.search(r"where\s+meter_id\s*=\s*'([^']+)'", lower_sql)
            if m:
                mid = m.group(1)
                generated_sql += f" WHERE meter_id = '{mid}'"
            generated_sql += ";"

    if not is_query_safe(generated_sql):
        return JSONResponse(status_code=400, content={"error": "Generated SQL is not allowed for safety."})

    rows = run_query(generated_sql)
    if isinstance(rows, dict) and rows.get("error"):
        return JSONResponse(status_code=400, content={"error": rows["error"], "generated_sql": generated_sql})

    # infer ncols
    ncols = len(rows[0]) if rows else 0

    response = {
        "question": question,
        "output_type": output_type,
        "generated_sql": generated_sql,
        "result": rows,
        "ncols": ncols
    }

    if output_type == "nl":
        response["summary"] = summarize_results(question, generated_sql, rows)

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
    canvas { width:100%; height:360px; margin-top:12px; display:block; }
    .footer { position: fixed; left: 0; right: 0; bottom: 0; background: rgba(255,255,255,0.98); border-top: 1px solid #e6eef8; padding: 10px; display:flex; justify-content:center; z-index: 999; }
    .controls { width:100%; max-width:1000px; display:flex; gap:8px; align-items:center; }
    textarea { flex:1; min-height:48px; padding:10px; border-radius:8px; border:1px solid #e5e7eb; font-size:14px; resize:none; }
    button { padding:10px 14px; border-radius:8px; border:none; background:#6d28d9; color:white; cursor:pointer; }
  </style>
  <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
</head>
<body>
  <div class="container">
    <div class="card" id="mainCard">
      <h2>Forecast Chat (chat history)</h2>
      <div class="muted">Ask questions naturally. The system will auto-detect whether to show a table, graph or summary.</div>

      <div id="chat" class="chat"></div>
      <canvas id="chart" style="display:none;"></canvas>
    </div>
  </div>

  <div class="footer">
    <div class="controls">
      <textarea id="q" placeholder="Ask something...">show all entries for MTR001</textarea>
      <button id="sendBtn">Send</button>
      <button id="clearBtn">Clear</button>
    </div>
  </div>

<script>
const chatEl = document.getElementById('chat');
const qEl = document.getElementById('q');
const sendBtn = document.getElementById('sendBtn');
const clearBtn = document.getElementById('clearBtn');
const chartEl = document.getElementById('chart');
let chartInstance = null;
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
        p.textContent = m.meta.summary;
        d.appendChild(p);
      }

      if (m.meta && m.meta.output_type === 'table') {
        const rows = m.meta.result || [];
        if (rows.length === 0) {
          const em = document.createElement('div'); em.className='muted'; em.textContent = 'No rows returned.'; d.appendChild(em);
        } else {
          const tbl = document.createElement('table');
          const thead = document.createElement('thead');
          thead.innerHTML = '<tr><th>id</th><th>meter_id</th><th>datetime</th><th>forecasted_load_kwh</th></tr>';
          tbl.appendChild(thead);
          const tbody = document.createElement('tbody');
          for (const r of rows) {
            const tr = document.createElement('tr');
            tr.innerHTML = `<td>${escapeHtml(r[0] ?? '')}</td><td>${escapeHtml(r[1] ?? '')}</td><td>${escapeHtml(r[2] ?? '')}</td><td>${escapeHtml(r[3] ?? '')}</td>`;
            tbody.appendChild(tr);
          }
          tbl.appendChild(tbody);
          d.appendChild(tbl);
        }
      }

      if (m.meta && m.meta.output_type === 'graph') {
        const rows = m.meta.result || [];
        const note = document.createElement('div'); note.className='muted'; note.textContent = (rows.length ? 'Showing graph below.' : 'No rows to plot.'); d.appendChild(note);
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

    if (data.output_type === 'graph') {
      renderChartFromData(data);
    } else {
      if (chartInstance) { chartInstance.destroy(); chartInstance = null; chartEl.style.display='none'; }
    }
  } catch (e) {
    history.push({ role:'assistant', text:'Request failed: ' + String(e), meta:{ output_type:'error' }});
    renderChat();
  } finally {
    qEl.value = '';
  }
};

clearBtn.onclick = () => {
  history.length = 0;
  if (chartInstance) { chartInstance.destroy(); chartInstance = null; chartEl.style.display='none'; }
  renderChat();
};

function renderChartFromData(data) {
  const rows = data.result || [];
  if (!rows || rows.length === 0) {
    if (chartInstance) { chartInstance.destroy(); chartInstance = null; chartEl.style.display='none'; }
    return;
  }

  const ncols = data.ncols || (Array.isArray(rows[0]) ? rows[0].length : 1);
  let labels = [];
  let values = [];

  if (ncols >= 3) {
    const first = rows[0];
    let datetimeIndex = 2;
    if (!first[2] || String(first[2]).match(/^\\d{4}-\\d{2}-\\d{2}/) === null) {
      for (let ci = 0; ci < first.length; ci++) {
        if (String(first[ci]).match(/^\\d{4}-\\d{2}-\\d{2}/)) { datetimeIndex = ci; break; }
      }
    }
    let valueIndex = first.length - 1;
    labels = rows.map(r => r[datetimeIndex]);
    values = rows.map(r => Number(r[valueIndex]) || 0);
  } else if (ncols === 2) {
    labels = rows.map(r => r[0]);
    values = rows.map(r => Number(r[1]) || 0);
  } else {
    labels = rows.map((_, i) => i+1);
    values = rows.map(r => Number(Array.isArray(r) ? r[0] : r) || 0);
  }

  chartEl.style.display='block';
  if (chartInstance) { chartInstance.destroy(); chartInstance = null; }
  const ctx = chartEl.getContext('2d');
  chartInstance = new Chart(ctx, {
    type: 'line',
    data: {
      labels,
      datasets: [{ label: 'forecasted_load_kwh', data: values, borderWidth: 2, tension: 0.2, pointRadius: 2 }]
    },
    options: { responsive: true, maintainAspectRatio: false, scales: { x:{ display:true }, y:{ display:true } } }
  });

  chartEl.scrollIntoView({ behavior:'smooth', block:'end' });
}

renderChat();
</script>
</body>
</html>
"""


@app.get("/", response_class=HTMLResponse)
def index():
    return HTMLResponse(INDEX_HTML)
