# main.py
from fastapi import FastAPI, Request, Depends, Form
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, FileResponse
from fastapi.templating import Jinja2Templates

from auth import authenticate_user, create_access_token, JWTBearer
from chatbot_pipeline import (
    is_greeting,
    greeting_response,
    classify_intent,
    handle_nl2sql,
)
from nl2sql_pipeline import SCHEMA
from forecast_pipeline import forecast_revenue
from db import init_db

import logging

# ---------------- LOGGING ----------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s"
)
logger = logging.getLogger("chatbot")

# ---------------- APP ----------------
app = FastAPI(title="Forecast Chatbot API")
templates = Jinja2Templates(directory="templates")


@app.on_event("startup")
def startup():
    init_db()


@app.get("/")
def root():
    return RedirectResponse("/login")


@app.get("/login", response_class=HTMLResponse)
def login_form(request: Request):
    return templates.TemplateResponse("login.html", {"request": request})


@app.post("/token")
def login(username: str = Form(...), password: str = Form(...)):
    user = authenticate_user(username, password)
    if not user:
        return JSONResponse(status_code=401, content={"error": "Invalid credentials"})

    token = create_access_token(
        {"sub": user["username"], "role": user["role"]}
    )
    return {"access_token": token, "token_type": "bearer"}


@app.get("/chat-ui", response_class=HTMLResponse)
def chat_ui():
    return FileResponse("index.html")


@app.post("/chat")
def chat_endpoint(body: dict, token_payload=Depends(JWTBearer())):
    question = body.get("question")
    role = token_payload.get("role")

    logger.info(f"Incoming question: {question!r} | role={role}")

    if not question:
        logger.warning("Empty question received")
        return JSONResponse(status_code=422, content={"error": "question required"})

    # 1️⃣ GREETING
    if is_greeting(question):
        logger.info("Route → GREETING")
        return {
            "question": question,
            "output_type": "nl",
            "summary": greeting_response()
        }

    # 2️⃣ INTENT
    intent = classify_intent(question)
    logger.info(f"Intent classified as: {intent}")

    # 3️⃣ FORECAST
    if intent == "python_model":
        logger.info("Route → FORECAST PIPELINE")
        return forecast_revenue(question)

    # 4️⃣ NL2SQL
    logger.info("Route → NL2SQL PIPELINE")

    result = handle_nl2sql(
        question=question,
        role=role,
        schema=SCHEMA
    )

    if "generated_sql" in result:
        logger.info(f"Generated SQL: {result['generated_sql']}")

    if isinstance(result.get("result"), list):
        logger.info(f"Rows returned: {len(result['result'])}")

    return result
