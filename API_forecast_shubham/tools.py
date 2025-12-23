# ============================================================
# tools.py — CLEAN VERSION (ONLY predict + retrain)
# ============================================================

from langchain_core.tools import tool
import joblib
import pandas as pd
import os
import sqlite3
from prophet import Prophet
import dateutil.parser

MODEL_PATH = "milan/prophet_load_forecast_model.pkl"
DB_PATH = "loadforecast.db"


# ============================================================
# UNIVERSAL DATE PARSER
# ============================================================
def parse_any_date(s: str) -> str:
    """
    Convert ANY human-readable date into ISO format.
    If time missing → defaults to 00:00:00.
    """
    if not isinstance(s, str):
        return s

    s = s.strip().replace("T", " ")

    try:
        dt = dateutil.parser.parse(s, dayfirst=True)
        return dt.strftime("%Y-%m-%d %H:%M:%S")
    except:
        return "INVALID_DATETIME_FORMAT"


# ============================================================
# DATABASE HELPERS (only for saving + retrain)
# ============================================================
def _get_conn():
    return sqlite3.connect(DB_PATH)


def _load_forecast_table_df():
    """Loads forecast table used for retraining."""
    conn = _get_conn()
    df = pd.read_sql_query("SELECT * FROM forecast;", conn)
    conn.close()
    return df


# ============================================================
# SAVE PREDICTION
# ============================================================
def save_prediction_to_db(datetime_str, predicted_load):
    conn = _get_conn()
    cur = conn.cursor()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS forecasted_values (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            datetime TEXT NOT NULL,
            predicted_load REAL NOT NULL
        );
    """)

    cur.execute(
        "INSERT INTO forecasted_values (datetime, predicted_load) VALUES (?, ?)",
        (datetime_str, predicted_load)
    )

    conn.commit()
    conn.close()

    return {"message": "Prediction saved successfully."}


# ============================================================
# TOOL: PREDICT
# ============================================================
@tool
def predict(datetime_str: str = None) -> str:
    """
    Predict electrical load using Prophet model.
    Accepts ANY human-readable date.
    Saves prediction to DB.
    """
    if not datetime_str:
        return "ERROR: datetime_str is required."

    norm = parse_any_date(datetime_str)
    if "INVALID" in norm:
        return f"ERROR: Cannot understand datetime '{datetime_str}'."

    # Load the Prophet model
    try:
        model = joblib.load(MODEL_PATH)
    except:
        return "ERROR: Prophet model not found."

    try:
        df = pd.DataFrame({"ds": [pd.to_datetime(norm)]})
        forecast = model.predict(df)
        load = float(forecast["yhat"].iloc[0])

        save_prediction_to_db(norm, load)

        return (
            f"Prediction successful.\n"
            f"Datetime: {norm}\n"
            f"Predicted Load: {load:.2f} MW\n"
            f"Stored into database."
        )

    except Exception as e:
        return f"Prediction failed: {str(e)}"


# ============================================================
# TOOL: RETRAIN
# ============================================================
@tool
def retrain() -> str:
    """
    Retrain Prophet model using rows from the 'forecast' table.
    """
    try:
        df = _load_forecast_table_df()
        df["Datetime"] = pd.to_datetime(df["Datetime"], errors="coerce")
        df = df.dropna(subset=["Datetime"])

        df = df.rename(columns={"Datetime": "ds", "COMED_MW": "y"})[["ds", "y"]]

        m = Prophet()
        m.fit(df)
        joblib.dump(m, MODEL_PATH)

        return f"Model retrained using {len(df)} rows."

    except Exception as e:
        return f"Retraining failed: {str(e)}"
