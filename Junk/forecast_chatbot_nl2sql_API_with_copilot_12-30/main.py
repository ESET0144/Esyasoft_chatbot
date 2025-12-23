from fastapi import FastAPI, Request, Depends, Form
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates

from auth import authenticate_user, create_access_token, JWTBearer
from chatbot_pipeline import is_greeting, classify_intent, handle_nl2sql
from chatbot_pipeline import decide_output_type

from security import allowed_tables_for_role
from db import init_db

app = FastAPI(title="Secure Forecast Chatbot API")
templates = Jinja2Templates(directory="templates")


@app.on_event("startup")
def startup():
    # Ensure DB exists with minimal tables
    init_db()


@app.get("/login", response_class=HTMLResponse)
def login_form(request: Request):
    return templates.TemplateResponse("login.html", {"request": request})


@app.post("/token")
def login(username: str = Form(...), password: str = Form(...)):
    user = authenticate_user(username, password)
    if not user:
        return JSONResponse(status_code=401, content={"error": "Invalid credentials"})
    token = create_access_token({"sub": user["username"], "role": user["role"]})
    return {"access_token": token, "token_type": "bearer", "role": user["role"]}


@app.post("/chat")
def chat_endpoint(body: dict, token_payload=Depends(JWTBearer())):
    question = body.get('question') if isinstance(body, dict) else None
    if not question:
        return JSONResponse(status_code=422, content={"error": "question required"})

    # Greeting shortcut
    if is_greeting(question):
        return {"question": question, "output_type": "nl", "summary": "Hi — I'm here and ready to help."}

    intent = classify_intent(question)
    # Python model path MUST bypass DB entirely
    if intent == "python_model":
        # In production this function should use a model that does not access DB
        # For this example we return a simulated forecast
        return {"question": question, "intent": "python_model", "output_type": "forecast", "summary": "Forecast (simulated) — model path bypasses DB entirely.", "result": []}

    # NL2SQL path — perform authorization BEFORE executing SQL (after NL2SQL generates SQL)
    role = token_payload.get('role')
    res = handle_nl2sql(question, role)
    status_code = res.pop('status_code', 200)
    if status_code != 200:
        return JSONResponse(status_code=status_code, content=res)
    return res
