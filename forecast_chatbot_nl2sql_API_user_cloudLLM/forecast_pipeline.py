# forecast_pipeline.py
import os
import re
import sqlite3
import joblib
import pandas as pd
import numpy as np
from datetime import datetime
import logging
from llm_router import run_llm

# ---------- LOGGER ----------
logger = logging.getLogger("FORECAST")
logger.setLevel(logging.INFO)

MODEL_PATH = "revenue_lr_model.joblib"
DB_PATH = "forcast.db"
TABLE_NAME = "Revenue_data"

# ---------- date parser ----------
def parse_reference_date(prompt: str):
    """
    Extracts a reference date from user prompt if present.
    Returns datetime or None.
    """
    patterns = [
        # Match dd-mm-yyyy or dd/mm/yyyy or d-m-yyyy etc.
        # We allow 1 or 2 digits for day/month, and 4 digits for year.
        # Separators can be -, /, ., or space
        r'(\d{1,2}[-/. ]\d{1,2}[-/. ]\d{4})',
        
        # Match yyyy-mm-dd (ISOish)
        r'(\d{4}[-/. ]\d{1,2}[-/. ]\d{1,2})',
        
        # Match dd Mon yyyy (e.g. 01 Jan 2020)
        r'(\d{1,2}\s+[A-Za-z]{3,9}\s+\d{4})'
    ]

    for p in patterns:
        m = re.search(p, prompt)
        if m:
            s_raw = m.group(1)
            # Normalize separators to dashes for easier parsing
            s = re.sub(r'[-/. ]', '-', s_raw)
            
            for fmt in (
                "%d-%m-%Y", 
                "%Y-%m-%d", 
                "%d-%b-%Y", # handled by normalization if spaces became dashes? 
                            # Wait, "01 Jan 2020" -> "01-Jan-2020"
                "%d-%B-%Y"
            ):
                try:
                     # Special case for alphabetic months which might not have dash in original string if we just replaced separators
                     # But our regex allows spaces. Only the numbered ones are critical.
                     # Let's rely on standard formats.
                     
                    return datetime.strptime(s, fmt)
                except:
                    # Retry with raw string for "01 Jan 2020" formats just in case normalization broke it
                    try:
                        if " " in s_raw:
                             return datetime.strptime(s_raw, fmt.replace("-", " "))
                    except:
                        pass
                    continue

    # fallback: pandas (handles many edge cases)
    ts = pd.to_datetime(prompt, dayfirst=True, errors='coerce')
    if not pd.isnull(ts):
        return ts.to_pydatetime()

    return None



# ---------- Horizon parser ----------
def parse_horizon(question: str, default: int = 12) -> int:
    logger.info("[FORECAST] Parsing forecast horizon")
    m = re.search(
        r'next\s+(\d+)\s*(years?|months?|weeks?|days?|hours?)',
        question.lower()
    )
    if m:
        qty = int(m.group(1))
        unit = m.group(2)
        if 'year' in unit:
            return qty * 12
        if 'month' in unit:
            return qty
        if 'week' in unit:
            return qty * 4
        return qty
    return default


# ---------- Load & clean revenue data ----------
def load_revenue_data() -> pd.DataFrame:
    logger.info("[FORECAST] Loading revenue data from DB")
    conn = sqlite3.connect(DB_PATH)
    try:
        df = pd.read_sql_query(
            f"SELECT Datetime, Revenue FROM {TABLE_NAME}",
            conn
        )
    finally:
        conn.close()

    if df.empty:
        logger.warning("[FORECAST] Revenue table is empty")
        return df

    def try_parse(x):
        s = str(x)
        for fmt in (
            "%Y-%m-%d %H:%M:%S",
            "%Y-%m-%d %H:%M",
            "%d-%m-%Y %H:%M:%S",
            "%d-%m-%Y %H:%M",
            "%d-%m-%Y",
            "%Y-%m-%d",
        ):
            try:
                return datetime.strptime(s, fmt)
            except:
                pass
        ts = pd.to_datetime(s, dayfirst=True, errors="coerce")
        return None if pd.isnull(ts) else ts.to_pydatetime()

    df["Datetime_parsed"] = df["Datetime"].apply(try_parse)
    df["Revenue"] = pd.to_numeric(df["Revenue"], errors="coerce")
    df = df.dropna(subset=["Datetime_parsed", "Revenue"])

    df["Datetime_parsed"] = pd.to_datetime(df["Datetime_parsed"])
    df = df.sort_values("Datetime_parsed").reset_index(drop=True)

    logger.info(f"[FORECAST] Loaded {len(df)} valid rows")
    return df


# ---------- Feature engineering ----------
def make_time_features(df: pd.DataFrame) -> pd.DataFrame:
    logger.info("[FORECAST] Generating time features")
    df = df.copy()
    dt = pd.to_datetime(df["Datetime_parsed"])

    try:
        ts = dt.astype("int64") // 10**9
    except:
        ts = dt.values.astype("datetime64[ns]").astype("int64") // 10**9

    df["ts"] = ts
    df["month"] = dt.dt.month
    df["dayofweek"] = dt.dt.dayofweek

    df["month_sin"] = np.sin(2 * np.pi * df["month"] / 12)
    df["month_cos"] = np.cos(2 * np.pi * df["month"] / 12)
    df["dow_sin"] = np.sin(2 * np.pi * df["dayofweek"] / 7)
    df["dow_cos"] = np.cos(2 * np.pi * df["dayofweek"] / 7)

    return df


# ---------- Main forecast entry ----------
def forecast_revenue(question: str, role: str, llm_mode: str = "ollama") -> dict:
    logger.info("===== FORECAST PIPELINE START =====")
    logger.info(f"[FORECAST] Question: {question} | Role: {role} | LLM Mode: {llm_mode}")
    
    # SECURITY CHECK
    from security import allowed_tables_for_role
    allowed = allowed_tables_for_role(role)
    if "revenue_data" not in allowed:
        logger.warning(f"[FORECAST] Access Denied for role {role}")
        return {
            "output_type": "error",
            "summary": "Access Denied: You do not have permission to access revenue forecasts.",
            "error": "Access Denied: You do not have permission to access revenue forecasts."
        }

    if not os.path.exists(MODEL_PATH):
        logger.error("[FORECAST] Model file not found")
        return {
            "output_type": "error",
            "summary": "Revenue forecast model not found. Please train the model first.",
            "error": "Revenue forecast model not found. Train the model first."
        }

    horizon = parse_horizon(question, default=12)
    logger.info(f"[FORECAST] Parsed horizon = {horizon}")

    df = load_revenue_data()
    if df.empty:
        logger.error("[FORECAST] No data available for forecasting")
        return {
            "output_type": "error",
            "summary": "No historical revenue data found.",
            "error": "No historical revenue data found."
        }

    # ---------- Detect frequency ----------
    deltas = df["Datetime_parsed"].diff().dropna().dt.total_seconds()
    median_delta = deltas.median() if not deltas.empty else None

    if median_delta is None:
        freq = "MS"
    elif median_delta <= 3600 + 1:
        freq = "h"
    elif median_delta <= 86400 + 1:
        freq = "D"
    else:
        freq = "MS"

    logger.info(f"[FORECAST] Detected data frequency = {freq}")

    # ---------- Load model ----------
    logger.info("[FORECAST] Loading ML model")
    model = joblib.load(MODEL_PATH)

    # ---------- Determine anchor date ----------
    anchor_date = parse_reference_date(question)

    if anchor_date is not None:
        logger.info(f"[FORECAST] Using anchor date from question: {anchor_date}")
        start_dt = pd.to_datetime(anchor_date)
    else:
        start_dt = df["Datetime_parsed"].iloc[-1]
        logger.info(f"[FORECAST] Using last available date as anchor: {start_dt}")

    # ---------- Future dates ----------
    future_idx = pd.date_range(
        start=start_dt,
        periods=horizon + 1,
        freq=freq
    )[1:]

    logger.info(f"[FORECAST] Generated future index: {len(future_idx)} rows")

    future_df = pd.DataFrame({"Datetime_parsed": future_idx})
    future_df = make_time_features(future_df)

    features = ["ts", "month_sin", "month_cos", "dow_sin", "dow_cos"]
    X_future = future_df[features].values

    logger.info("[FORECAST] Running model prediction")
    preds = model.predict(X_future)

    future_df["Predicted_Revenue"] = preds
    future_df["Datetime"] = future_df["Datetime_parsed"].astype(str)

    logger.info("[FORECAST] Forecast completed successfully")
    logger.info("===== FORECAST PIPELINE END =====")

    rows = [
        [r["Datetime"], r["Predicted_Revenue"]]
        for r in future_df[["Datetime", "Predicted_Revenue"]].to_dict(orient="records")
    ]

    anchor_txt = (
    anchor_date.strftime("%Y-%m-%d")
    if anchor_date else
    "last available date"
    )

    # ---------- LLM-based Summary ----------
    total_rev = future_df["Predicted_Revenue"].sum()
    avg_rev = future_df["Predicted_Revenue"].mean()
    
    prompt = (
        f"You are a data analyst assistant. \n"
        f"Question: {question}\n"
        f"Data Context: \n"
        f"- Forecast Horizon: {horizon} periods\n"
        f"- Start Date: {anchor_txt}\n"
        f"- Total Forecasted Revenue: {total_rev:,.2f}\n"
        f"- Average Forecasted Revenue: {avg_rev:,.2f}\n"
        f"Generate a concise (1-2 sentences) natural language answer to the user's question based on this data."
    )
    
    try:
        summary_text = run_llm(
             messages=[{"role": "user", "content": prompt}],
             llm_mode=llm_mode
        )
    except Exception as e:
        logger.error(f"LLM Summary failed: {e}")
        summary_text = f"Forecasted revenue for next {horizon} periods from {anchor_txt}. Total: {total_rev:,.2f}"

    return {
        "question": question,
        "intent": "python_model",
        "output_type": "forecast",
        "horizon": horizon,
        "frequency": freq,
        "columns": ["Datetime", "Predicted_Revenue"],
        "ncols": 2,
        "result": rows,   # ✅ array of arrays
        "summary": summary_text.strip(),
        "include_table": True
    }
