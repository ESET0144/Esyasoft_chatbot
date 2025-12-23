import joblib
import pandas as pd

# --------------------------------------------------------
# Load the trained Prophet model (run once)
# --------------------------------------------------------
MODEL_PATH = "milan/prophet_load_forecast_model.pkl"   # your joblib file

model = joblib.load(MODEL_PATH)


# --------------------------------------------------------
# Function to forecast load for a given datetime
# --------------------------------------------------------
def forecast_load(datetime_str):
    """
    Predict energy load for a given datetime using a Prophet model saved with joblib.
    
    Input:
        datetime_str (str): "YYYY-MM-DD HH:MM:SS"
    
    Output:
        float: predicted load value (yhat)
    """
    # Prepare input for Prophet
    input_df = pd.DataFrame({"ds": [pd.to_datetime(datetime_str)]})

    # Predict
    forecast = model.predict(input_df)

    # Get the predicted load value
    predicted_load = float(forecast["yhat"].iloc[0])

    return predicted_load


# --------------------------------------------------------
# Example usage
# --------------------------------------------------------
if __name__ == "__main__":
    ts = "2017-03-01 1:00:00"
    print("Forecasted Load:", forecast_load(ts))

