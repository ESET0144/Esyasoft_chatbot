# forecast_revenue_model.py
import re
import sqlite3
import pandas as pd
import numpy as np
from datetime import datetime
from sklearn.linear_model import Ridge
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import mean_absolute_error, mean_squared_error
import joblib
import os
from typing import Tuple

# ---------- CONFIG ----------
DB_PATH = "forcast.db"        # adjust to your sqlite file (kept same name used in test file)
TABLE_NAME = "Revenue_data"
MODEL_PATH = "revenue_lr_model.joblib"
# -----------------------------

FORECAST_KEYWORDS = [
    "forecast", "predict", "projection", "future revenue", "next", "predict revenue",
    "forecast revenue", "how much will", "what will be", "predict next"
]

def detect_intent(prompt: str) -> str:
    p = prompt.lower()
    for kw in FORECAST_KEYWORDS:
        if kw in p:
            return "forecast"
    if re.search(r'\b(select|show|where|group by|order by|join|count|avg|sum)\b', p):
        return "nl2sql"
    return "nl2sql"

def parse_horizon(prompt: str, default_horizon: int = 12) -> int:
    m = re.search(r'next\s+(\d+)\s*(years|year|months|month|weeks|week|days|day|hours|hour)', prompt.lower())
    if m:
        qty = int(m.group(1))
        unit = m.group(2)
        if 'year' in unit:
            return qty * 12
        if 'month' in unit:
            return qty
        if 'week' in unit:
            return qty * 4
        if 'day' in unit:
            return qty
        if 'hour' in unit:
            return qty
    m2 = re.search(r'for\s+(\d+)\s*(periods|steps)?', prompt.lower())
    if m2:
        return int(m2.group(1))
    return default_horizon

# ---------- Data loader ----------
def load_revenue_data(db_path=DB_PATH, table=TABLE_NAME) -> pd.DataFrame:
    """
    Loads Datetime and Revenue from the given table and returns a cleaned dataframe
    with a 'Datetime_parsed' column.
    """
    conn = sqlite3.connect(db_path)
    try:
        df = pd.read_sql_query(f"SELECT Datetime, Revenue FROM {table}", conn)
    finally:
        conn.close()

    if df.empty:
        return df

    # robust parsing: try several formats, fall back to pandas with dayfirst=True
    def try_parse_value(x):
        s = str(x)
        for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%d-%m-%Y %H:%M:%S", "%d-%m-%Y %H:%M", "%d-%m-%Y", "%Y-%m-%d"):
            try:
                return datetime.strptime(s, fmt)
            except Exception:
                continue
        # last resort: let pandas try (handles many formats)
        ts = pd.to_datetime(s, dayfirst=True, errors='coerce')
        if pd.isnull(ts):
            return None
        return ts.to_pydatetime()

    df['Datetime_parsed'] = df['Datetime'].apply(try_parse_value)
    df = df.dropna(subset=['Datetime_parsed', 'Revenue']).copy()
    df['Revenue'] = pd.to_numeric(df['Revenue'], errors='coerce')
    df = df.dropna(subset=['Revenue'])
    # convert to pandas Timestamp dtype for dt operations
    df['Datetime_parsed'] = pd.to_datetime(df['Datetime_parsed'])
    df = df.sort_values('Datetime_parsed').reset_index(drop=True)
    return df

# ---------- Feature engineering ----------
def make_time_features(df: pd.DataFrame, datetime_col='Datetime_parsed') -> pd.DataFrame:
    df = df.copy()
    dt = pd.to_datetime(df[datetime_col])
    # numeric timestamp (seconds since epoch) — safe conversion
    try:
        ts_vals = dt.astype('int64') // 10**9  # Use astype instead of view
    except Exception:
        # fallback
        ts_vals = (dt.values.astype('datetime64[ns]').astype('int64')) // 10**9
    df['ts'] = ts_vals
    df['year'] = dt.dt.year
    df['month'] = dt.dt.month
    df['day'] = dt.dt.day
    df['hour'] = dt.dt.hour
    df['dayofweek'] = dt.dt.dayofweek
    df['month_sin'] = np.sin(2 * np.pi * df['month'] / 12.0)
    df['month_cos'] = np.cos(2 * np.pi * df['month'] / 12.0)
    df['dow_sin'] = np.sin(2 * np.pi * df['dayofweek'] / 7.0)
    df['dow_cos'] = np.cos(2 * np.pi * df['dayofweek'] / 7.0)
    return df

def build_X_y(df: pd.DataFrame) -> Tuple[np.ndarray, np.ndarray, pd.DataFrame]:
    df2 = make_time_features(df)
    features = ['ts', 'month_sin', 'month_cos', 'dow_sin', 'dow_cos']
    X = df2[features].values
    y = df2['Revenue'].values
    return X, y, df2

def train_and_save_model(df: pd.DataFrame, model_path=MODEL_PATH):
    X, y, df2 = build_X_y(df)
    if len(X) < 10:
        raise ValueError("Not enough rows to train model (need >= 10).")
    split = int(len(X) * 0.8)
    X_train, X_test = X[:split], X[split:]
    y_train, y_test = y[:split], y[split:]
    pipeline = Pipeline([
        ('scaler', StandardScaler()),
        ('reg', Ridge(alpha=1.0))
    ])
    pipeline.fit(X_train, y_train)
    preds_test = pipeline.predict(X_test)
    mae = mean_absolute_error(y_test, preds_test)
    mse = mean_squared_error(y_test, preds_test)
    rmse = np.sqrt(mse)  # Calculate RMSE from MSE
    joblib.dump(pipeline, model_path)
    return pipeline, {'mae': mae, 'rmse': rmse, 'train_size': len(X_train), 'test_size': len(X_test)}, df2

def forecast(pipeline, df: pd.DataFrame, horizon: int, freq: str = 'M') -> pd.DataFrame:
    """
    freq: pandas freq string like 'M','D','H'
    """
    last_dt = pd.to_datetime(df['Datetime_parsed'].iloc[-1])
    # create a date_range that starts after last_dt by using periods and slicing
    future_idx = pd.date_range(start=last_dt, periods=horizon + 1, freq=freq)[1:]
    future_df = pd.DataFrame({'Datetime_parsed': future_idx})
    future_df = make_time_features(future_df, 'Datetime_parsed')
    features = ['ts', 'month_sin', 'month_cos', 'dow_sin', 'dow_cos']
    X_future = future_df[features].values
    preds = pipeline.predict(X_future)
    future_df['Predicted_Revenue'] = preds
    return future_df[['Datetime_parsed', 'Predicted_Revenue']]

# ---------- Router & handler ----------
def handle_prompt(prompt: str):
    intent = detect_intent(prompt)
    if intent == 'nl2sql':
        return {"intent": "nl2sql", "result": "Route to your NL2SQL handler."}
    horizon = parse_horizon(prompt, default_horizon=12)
    df = load_revenue_data()
    if df.empty:
        return {"error": "No data loaded from DB."}
    # determine frequency
    deltas = df['Datetime_parsed'].diff().dropna().map(lambda x: x.total_seconds())
    median_delta = deltas.median() if not deltas.empty else None
    if median_delta is None:
        freq = 'M'
    elif median_delta <= 3600 + 1:
        freq = 'h'  # Use lowercase 'h' for hourly (newer pandas convention)
    elif median_delta <= 86400 + 1:
        freq = 'D'
    else:
        freq = 'MS'  # Use 'MS' for month start instead of 'M'
    if os.path.exists(MODEL_PATH):
        pipeline = joblib.load(MODEL_PATH)
    else:
        pipeline, metrics, _ = train_and_save_model(df)
    future = forecast(pipeline, df, horizon, freq=freq)
    return {
        "intent": "forecast",
        "horizon": horizon,
        "freq": freq,
        "forecast": future.to_dict(orient='records')
    }

if __name__ == "__main__":
    prompts = [
        "Please forecast revenue for the next 12 months",
        "Show me revenue where year = 2015"
    ]
    for p in prompts:
        print("PROMPT:", p)
        print(handle_prompt(p))
