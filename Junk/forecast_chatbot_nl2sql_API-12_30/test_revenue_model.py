# test_revenue_model.py
import sqlite3
import pandas as pd
import numpy as np
from datetime import datetime
from sklearn.linear_model import LinearRegression
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score

DB_PATH = "forcast.db"
TABLE = "Revenue_data"

# ---------------- LOAD DATA ----------------
def load_data():
    conn = sqlite3.connect(DB_PATH)
    try:
        df = pd.read_sql_query(f"SELECT Datetime, Revenue FROM {TABLE}", conn)
    finally:
        conn.close()

    if df.empty:
        raise ValueError("No rows loaded from DB. Check DB_PATH and TABLE name.")

    # let pandas parse flexibly (handles both dd-mm-YYYY and YYYY-mm-dd)
    df["Datetime"] = pd.to_datetime(df["Datetime"], dayfirst=True, errors='coerce')
    if df["Datetime"].isnull().any():
        # try a more flexible pass for leftover unparsable rows and drop them
        df["Datetime"] = df["Datetime"].fillna(pd.to_datetime(df["Datetime"].astype(str), errors='coerce', dayfirst=False))
    df = df.dropna(subset=["Datetime"]).sort_values("Datetime").reset_index(drop=True)
    return df

# ---------------- FEATURES ----------------
# ---------------- FEATURES ----------------
def make_features(df):
    """
    Build features X and target y if present.
    If df does not contain 'Revenue', returns (X, None).
    """
    df = df.copy()
    # ensure Datetime dtype
    df["Datetime"] = pd.to_datetime(df["Datetime"])
    # safe timestamp conversion (avoid .view which warns)
    try:
        df["ts"] = df["Datetime"].astype("int64") // 10**9
    except Exception:
        # fallback (should rarely be needed)
        df["ts"] = (df["Datetime"].astype("int64") // 10**9).astype(int)

    df["hour"] = df["Datetime"].dt.hour
    df["dow"] = df["Datetime"].dt.dayofweek

    df["hour_sin"] = np.sin(2 * np.pi * df["hour"] / 24)
    df["hour_cos"] = np.cos(2 * np.pi * df["hour"] / 24)

    X = df[["ts", "hour_sin", "hour_cos", "dow"]]
    if "Revenue" in df.columns:
        y = df["Revenue"].astype(float)
    else:
        y = None
    return X, y

# ---------------- PREDICT A SPECIFIC DATE ----------------
def predict_for_date(model, date_string):
    # accept both 'dd-mm-YYYY HH:MM' and ISO
    dt = pd.to_datetime(date_string, dayfirst=True)
    df = pd.DataFrame({"Datetime": [dt]})
    X, y = make_features(df)
    # model.predict expects a 2D array; use X.values
    pred = model.predict(X.values)[0]
    print(f"\nPrediction for {date_string} = {pred:.2f}")


# ---------------- TRAIN & EVALUATE ----------------
def train_model(df):
    X, y = make_features(df)

    if len(X) < 10:
        raise ValueError("Not enough data to train (need >= 10 rows).")

    split = int(len(X) * 0.8)
    X_train, X_test = X.iloc[:split], X.iloc[split:]
    y_train, y_test = y.iloc[:split], y.iloc[split:]

    model = LinearRegression()
    model.fit(X_train, y_train)

    preds = model.predict(X_test)

    mae = mean_absolute_error(y_test, preds)
    rmse = mean_squared_error(y_test, preds) ** 0.5
    r2 = r2_score(y_test, preds)

    print("\n=== MODEL PERFORMANCE ===")
    print("Train size:", len(X_train))
    print("Test size:", len(X_test))
    print("MAE :", mae)
    print("RMSE:", rmse)
    print("R²  :", r2)

    return model


# ---------------- MAIN ----------------
if __name__ == "__main__":
    df = load_data()
    print("Loaded rows:", len(df))
    print("From:", df['Datetime'].min(), "To:", df['Datetime'].max())

    model = train_model(df)

    # Example: predict a future hour
    predict_for_date(model, "01-01-2019 01:00")
