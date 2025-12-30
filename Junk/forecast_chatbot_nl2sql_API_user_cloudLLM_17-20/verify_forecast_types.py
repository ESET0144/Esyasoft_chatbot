
from forecast_pipeline import forecast_revenue
import logging

# Mute logs
logging.basicConfig(level=logging.CRITICAL)

print("--- Testing Forecast Differentiation ---")

# 1. Standard Forecast
print("\n[TEST] Question: 'forecast revenue'")
res1 = forecast_revenue("forecast revenue", role="admin")
print(f"Summary: {res1.get('summary')}")

# 2. Total Forecast
print("\n[TEST] Question: 'total forecast revenue'")
res2 = forecast_revenue("total forecast revenue", role="admin")
print(f"Summary: {res2.get('summary')}")

if "TOTAL" in res2.get("summary", ""):
    print("SUCCESS: 'TOTAL' keyword found in summary.")
else:
    print("FAILURE: 'TOTAL' keyword MISSING.")

# 3. Average Forecast
print("\n[TEST] Question: 'average forecast revenue'")
res3 = forecast_revenue("average forecast revenue", role="admin")
print(f"Summary: {res3.get('summary')}")

if "AVERAGE" in res3.get("summary", ""):
    print("SUCCESS: 'AVERAGE' keyword found in summary.")
else:
    print("FAILURE: 'AVERAGE' keyword MISSING.")
