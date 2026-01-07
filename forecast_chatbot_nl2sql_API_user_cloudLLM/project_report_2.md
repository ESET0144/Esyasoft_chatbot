# Forecast Chatbot Project Report

## 1. Project Overview
So, this is the Forecast Chatbot! It's a pretty cool AI-powered app that lets you chat with your data. Whether you want to know future revenue trends or just query the database, you can do it all using natural language. No complex SQL queries needed!

Here’s what it does in a nutshell:
*   **Talk or Type:** It supports both voice and text inputs.
*   **Offline First:** Uses offline speech recognition, so it's fast and private.
*   **Smart Forecasting:** Uses machine learning to predict revenue.
*   **Database Whiz:** Converts your questions into SQL queries automatically.
*   **Hybrid AI:** Switches between local and cloud LLMs depending on what you need.

## 2. Technical Stuff & Stack
We built this using some solid tech. Here’s the breakdown:

### Core Frameworks
*   **Backend:** Python with FastAPI (super fast!).
*   **Server:** Uvicorn.
*   **Frontend:** HTML5, JavaScript, and Vanilla CSS. We use Jinja2 for those login templates.
*   **Database:** SQLite (`forcast.db` and `your_database.db`).
*   **Auth:** JWT (JSON Web Tokens) to keep things secure.

### The Brains (Models)
We are using some specific models to make the magic happen:

*   **Voice Assistant (Speech-to-Text)**
    *   **Model:** `vosk-model-small-en-us-0.15`
    *   **Type:** Offline Speech Recognition.
    *   **How it works:** You speak, the frontend hits the `/transcribe` endpoint, and Vosk converts audio to text locally.

*   **Revenue Forecasting**
    *   **Model:** Linear Regression (saved as `revenue_lr_model.joblib`).
    *   **Features:** Time-based stuff like Month Sine/Cosine and Day-of-Week.
    *   **Logic:** It understands things like "next 3 months" effectively.

*   **Large Language Models (LLMs)**
    *   **Local Mode:** `gpt-oss:20b` (Great for privacy).
    *   **Cloud Mode:** `google/gemma-3-27b-it:free` (When you need more power).
    *   **Role:** These handle parsing questions, generating SQL, and summarizing results.

## 3. How It Flows
Here is how the data moves through the system:

```mermaid
graph TD
    User[User Input (Voice/Text)] -->|Audio| Vosk[Vosk: vosk-model-small-en-us-0.15]
    Vosk -->|Text| Router{Intent Classification}
    User -->|Text| Router
    Router -->|Forecast| ForecastPipe[Forecast Pipeline]
    Router -->|Database Query| NL2SQL[NL2SQL Pipeline]
    ForecastPipe -->|Linear Regression| LRModel[revenue_lr_model.joblib]
    ForecastPipe -->|Summary| LLM[LLM: gpt-oss:20b / gemma-3-27b-it]
    NL2SQL -->|Generate SQL| LLM
    NL2SQL -->|Execute SQL| DB[(SQLite DB)]
    DB -->|Results| LLM
    LLM -->|Final Response| UI[User Interface]
```

*   **Step 1:** You ask a question.
*   **Step 2:** If you spoke, Vosk transcribes it.
*   **Step 3:** The app checks if you're greeting it or asking for real work.
*   **Step 4:** It sends you to either the **Forecast Direct** or **NL2SQL** pipeline.
*   **Step 5:** You get a smart response, charts, or tables!

## 4. Security & Access
We didn’t skimp on security. Here’s the deal:

*   **Login Required:** You need a Bearer Token to talk to the API.
*   **Roles:**
    *   `admin`: Can see everything.
    *   `user`: Restricted access.
*   **Smart Checks:**
    *   **Forecast:** Checks if you are allowed to see `revenue_data`.
    *   **NL2SQL:** We use `allowed_tables_for_role` to make sure you only query what you're supposed to.

## 5. Deployment & Config
Getting it running is straightforward:

*   **Server:** Just run it with `uvicorn`.
*   **Secrets:** All API keys live in `.env`.
*   **Dependencies:** Everything is in `requirements.txt`.

## 6. Key Features
*   **Hybrid LLM:** Choose between `gpt-oss:20b` (Local) and `google/gemma-3-27b-it:free` (Cloud).
*   **Explainable AI:** Uses Linear Regression for forecasts so you can actually credit the trend, not just a black box.
*   **Visuals:** Ask for "plots" and it generates graphs on the fly.
*   **Debug Info:** Tells you exactly which model it used and how long it took.
