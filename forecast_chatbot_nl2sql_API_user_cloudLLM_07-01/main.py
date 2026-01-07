# main.py
import os
from dotenv import load_dotenv
load_dotenv(override=True)
from fastapi import FastAPI, Request, Depends, Form
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, FileResponse
from fastapi.templating import Jinja2Templates


from auth import authenticate_user, create_access_token, JWTBearer
from chatbot_pipeline import (
    is_greeting,
    greeting_response,
    classify_intent,
)
from nl2sql_pipeline import handle_nl2sql

from nl2sql_pipeline import SCHEMA
from forecast_pipeline import forecast_revenue
from db import init_db

import logging



print("BASE URL =", os.getenv("OPENAI_BASE_URL"))
print("OPENAI_API_KEY loaded:", bool(os.getenv("OPENAI_API_KEY")))



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


# ... imports ...
from fastapi import FastAPI, Request, Depends, Form, UploadFile, File
import vosk
import json
import wave

# Initialize Vosk Model
MODEL_PATH = "models/vosk-model-small-en-us-0.15"
if not os.path.exists(MODEL_PATH):
    print(f"WARNING: Vosk model not found at {MODEL_PATH}")
    vosk_model = None
else:
    vosk.SetLogLevel(-1)
    vosk_model = vosk.Model(MODEL_PATH)

@app.post("/transcribe")
async def transcribe_audio(file: UploadFile = File(...)):
    if not vosk_model:
        return JSONResponse(status_code=500, content={"error": "Vosk model not loaded"})
    
    try:
        audio_data = await file.read()
        rec = vosk.KaldiRecognizer(vosk_model, 16000)
        
        # Determine if we need to process as stream or whole block
        # For simplicity, assuming the frontend sends a WAV with correct header/format (16kHz mono)
        # However, WebAudio API usually creates headers. 
        # Vosk expects raw PCM or WAV.
        
        if rec.AcceptWaveform(audio_data):
            res = json.loads(rec.Result())
            text = res.get("text", "")
        else:
            res = json.loads(rec.PartialResult()) # Sometimes needed if audio is short
            # But normally we want FinalResult
            res = json.loads(rec.FinalResult())
            text = res.get("text", "")
            
        return {"text": text}
    except Exception as e:
        logger.error(f"Transcribe error: {e}")
        return JSONResponse(status_code=500, content={"error": str(e)})

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


# ... imports ...
import time 

@app.post("/chat")
def chat_endpoint(body: dict, token_payload=Depends(JWTBearer())):
    start_time = time.time()
    llm_mode = body.get("llm_mode", "ollama")
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
            "summary": greeting_response(),
            "debug_info": {
                "llm_mode": llm_mode,
                "intent": "greeting",
                "time_taken": f"{time.time() - start_time:.2f}s"
            }
        }

    # 2️⃣ INTENT
    intent = classify_intent(question)
    logger.info(f"Intent classified as: {intent}")

    # 3️⃣ FORECAST
    if intent == "python_model":
        logger.info("Route → FORECAST PIPELINE")
        response = forecast_revenue(question, role, llm_mode=llm_mode)
        response["debug_info"] = {
            "llm_mode": llm_mode,
            "intent": intent,
            "time_taken": f"{time.time() - start_time:.2f}s"
        }
        return response

    # 4️⃣ NL2SQL
    logger.info("Route → NL2SQL PIPELINE")

    result = handle_nl2sql(
        question=question,
        role=role,
        schema=SCHEMA,
        llm_mode=llm_mode
    )

    if "generated_sql" in result:
        logger.info(f"Generated SQL: {result['generated_sql']}")

    if isinstance(result.get("result"), list):
        logger.info(f"Rows returned: {len(result['result'])}")
    
    result["debug_info"] = {
        "llm_mode": llm_mode,
        "intent": intent,
        "time_taken": f"{time.time() - start_time:.2f}s"
    }

    return result
