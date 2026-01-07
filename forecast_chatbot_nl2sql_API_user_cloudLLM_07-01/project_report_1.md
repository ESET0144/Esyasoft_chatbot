Forecast Chatbot Project Report
1. Project Overview
The Forecast Chatbot is a comprehensive AI-powered application designed to provide revenue forecasting and database querying capabilities through a natural language interface. It supports both text and voice inputs, leveraging offline speech recognition, advanced machine learning for forecasting, and Large Language Models (LLMs) for natural language understanding and SQL generation.

The system is built as a web application with a FastAPI backend and a responsive HTML/JS frontend.

2. Technical Architecture & Stack
Core Frameworks
Backend: Python, FastAPI, Uvicorn (ASGI Server).
Frontend: HTML5, JavaScript, Vanilla CSS (Jinja2 Templates for login).
Database: SQLite (
forcast.db
, 
your_database.db
).
Authentication: JWT (JSON Web Tokens) with PyJWT.
Models & AI Components
Voice Assistant (Speech-to-Text):

Model: Vosk (Offline Speech Recognition).
Specific Model Used: vosk-model-small-en-us-0.15.
Mechanism: The frontend records audio, sends it to the /transcribe endpoint, where Vosk processes it locally to return text.
Revenue Forecasting:

Model: Linear Regression (scikit-learn compatible, saved as 
revenue_lr_model.joblib
).
Features: Time-based features including Timestamp, Month Sine/Cosine, Day-of-Week Sine/Cosine.
Logic: The system parses natural language time horizons (e.g., "next 3 months") and reference dates to project future revenue.
Natural Language to SQL (NL2SQL):

Logic: Converts user questions into SQL queries using an LLM.
Capability: Can query meter_table, customer_table, and Revenue_data.
Output: Returns raw tables, natural language summaries, or generates graphs (if requested).
Large Language Models (LLM):

Modes: Supports both Cloud (OpenAI) and Local (Ollama) models, switchable via the llm_mode parameter.
Usage: Used for Intent Classification (sometimes), SQL Generation, and Result Summarization.
3. Application Flow
The data flow primarily follows this path:

User Input: User speaks or types a query in the UI.
Transcription (If Voice): Audio is sent to /transcribe. Vosk converts it to text.
API Request: The text is sent to the /chat endpoint along with a JWT Auth Token.
Processing Pipeline:
Greeting Check: Simple heuristic to detect greetings.
Intent Classification: Determines if the user wants a Forecast (python_model) or Database Query (
nl2sql
).
Routing:
Forecast Route: simple parsers extract dates/horizons -> Linear Regression Model -> LLM Summary.
NL2SQL Route: LLM generates SQL -> SQL Normalization/Sanitization -> Security Check -> Database Execution -> LLM Summary.
Response: The backend returns a JSON object containing the answer, debug info, optional data tables, or base64 images (graphs).
4. Security & Access Control
Authentication:

Users log in via /login to receive a access_token (Bearer Token).
Endpoints are protected using Depends(JWTBearer()).
Users (Currently Hardcoded in 
auth.py
):
admin (Role: admin)
user
 (Role: 
user
)
Authorization (RBAC):

The system implements Role-Based Access Control to restrict data access.
Forecast: Checks if the user's role is allowed to access 
revenue_data
.
NL2SQL: allowed_tables_for_role restricts which tables a specific role can query. For example, a basic user might be restricted from accessing sensitive customer details.
5. Deployment & Configuration
Server: Uses uvicorn to run the FastAPI app.
Environment: Configuration (API Keys, Secrets) is managed via 
.env
 file (loaded by python-dotenv).
Dependencies: Listed in 
requirements.txt
 (including fastapi, uvicorn, openai, ollama, vosk via manual model download).
6. Key Features
Hybrid LLM Support: Switch between privacy-focused local models (Ollama) and high-performance cloud models (OpenAI).
Explainable Forecasting: Uses interpretable Linear Regression rather than a "black box" deep learning model for revenue trends.
Dynamic Visualization: Automatically generates PNG graphs for queries asking for "plots" or "trends".
Debug Mode: real-time display of Model used, Intent detected, and Execution Time.
