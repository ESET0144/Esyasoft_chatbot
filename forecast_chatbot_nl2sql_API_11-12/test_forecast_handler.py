#!/usr/bin/env python
# Test the forecast_revenue_from_model function

from app import forecast_revenue_from_model

print("Testing forecast_revenue_from_model function...\n")

result = forecast_revenue_from_model("forecast revenue for next 3 months")

print("Result keys:", list(result.keys()))
print()

if "error" in result:
    print("ERROR:", result.get("error"))
else:
    print("SUCCESS!")
    print("Intent:", result.get("intent"))
    print("Horizon:", result.get("horizon"))
    print("Frequency:", result.get("frequency"))
    print("Output type:", result.get("output_type"))
    num_forecasts = len(result.get("result", []))
    print(f"Number of forecasts: {num_forecasts}")
    if result.get("result"):
        print("\nFirst forecast:", result["result"][0])
