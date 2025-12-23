# # app.py
# from fastapi import FastAPI
# from nl2sql import natural_to_sql
# from db import run_query

# app = FastAPI()

# schema = """
# forecasted_table (
#     id INTEGER,
#     meter_id TEXT,
#     datetime TEXT,
#     forecasted_load_kwh REAL
# )
# """

# @app.get("/ask")
# def ask(question: str):
#     sql = natural_to_sql(question, schema)
#     # handle cannot convert
#     if sql.startswith("--CANNOT_CONVERT--"):
#         return {"error": "Could not convert question to SQL", "detail": sql}
#     result = run_query(sql)
#     return {"question": question, "generated_sql": sql, "result": result}

# app.py
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
from nl2sql import natural_to_sql
from db import run_query

app = FastAPI()

# Keep your schema consistent with the DB and nl2sql few-shot examples:
schema = """
forecasted_table (
    id INTEGER,
    meter_id TEXT,
    datetime TEXT,
    forecasted_load_kwh REAL
)
"""

@app.get("/ask")
def ask(question: str):
    """
    Existing NL -> SQL endpoint used by the frontend.
    Returns JSON: { question, generated_sql, result }
    """
    sql = natural_to_sql(question, schema)
    if sql.startswith("--CANNOT_CONVERT--"):
        return JSONResponse(status_code=400, content={"error": "Could not convert question to SQL", "detail": sql})
    result = run_query(sql)
    return {"question": question, "generated_sql": sql, "result": result}


# ---------- Simple Frontend ----------
INDEX_HTML = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width,initial-scale=1" />
  <title>Forecast NL→SQL Chat</title>
  <style>
    body { font-family: system-ui, -apple-system, "Segoe UI", Roboto, Arial; background:#f3f4f6; margin:0; padding:24px; }
    .card { max-width:900px; margin:0 auto; background:white; padding:20px; border-radius:12px; box-shadow:0 6px 18px rgba(0,0,0,0.08); }
    textarea { width:100%; height:72px; padding:10px; font-size:14px; border-radius:8px; border:1px solid #d1d5db; resize:vertical; }
    button { padding:10px 16px; border-radius:8px; border:none; background:#2563eb; color:white; font-weight:600; cursor:pointer; }
    pre { background:#111827; color:#e5e7eb; padding:12px; border-radius:8px; overflow:auto; }
    .muted { color:#6b7280; font-size:13px; }
    .row { display:flex; gap:12px; margin-top:12px; align-items:center; }
  </style>
</head>
<body>
  <div class="card">
    <h2>Forecast NL → SQL Chat</h2>
    <p class="muted">Type a natural-language question and the local Ollama model will be used to generate SQL which runs on the SQLite DB.</p>

    <form id="askForm" onsubmit="return false;">
      <label for="q">Question</label>
      <textarea id="q">show all entries for MTR001</textarea>

      <div class="row">
        <button id="askBtn">Ask</button>
        <button id="clearBtn" type="button">Clear</button>
        <div style="margin-left:auto" class="muted">Server: <strong>http://127.0.0.1:8000</strong></div>
      </div>
    </form>

    <div id="out" style="margin-top:18px"></div>
  </div>

<script>
const askBtn = document.getElementById('askBtn');
const clearBtn = document.getElementById('clearBtn');
const qInput = document.getElementById('q');
const out = document.getElementById('out');

clearBtn.onclick = () => {
  qInput.value = '';
  out.innerHTML = '';
};

askBtn.onclick = async () => {
  out.innerHTML = '<div class="muted">Running...</div>';
  const question = qInput.value.trim();
  if (!question) {
    out.innerHTML = '<div style="color:#b91c1c">Please enter a question.</div>';
    return;
  }

  try {
    // Use the same /ask endpoint your app exposes.
    const url = `/ask?question=${encodeURIComponent(question)}`;
    const res = await fetch(url);
    if (!res.ok) {
      const err = await res.json().catch(()=>({error:'Unknown error'}));
      out.innerHTML = `<div style="color:#b91c1c">Error: ${JSON.stringify(err)}</div>`;
      return;
    }
    const data = await res.json();

    // Render response
    const sqlHtml = `<div style="margin-top:12px"><strong>Generated SQL</strong><pre>${escapeHtml(data.generated_sql)}</pre></div>`;
    const resultHtml = `<div style="margin-top:12px"><strong>Result</strong><pre>${escapeHtml(JSON.stringify(data.result, null, 2))}</pre></div>`;
    out.innerHTML = sqlHtml + resultHtml;
  } catch (err) {
    out.innerHTML = `<div style="color:#b91c1c">Request failed: ${escapeHtml(String(err))}</div>`;
  }
};

function escapeHtml(s) {
  return String(s || '').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
}
</script>
</body>
</html>
"""

@app.get("/", response_class=HTMLResponse)
def index():
    # Serve the simple single-file frontend
    return HTMLResponse(INDEX_HTML)
