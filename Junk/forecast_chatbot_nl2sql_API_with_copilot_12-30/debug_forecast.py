#!/usr/bin/env python
# Debug script to check forecast pipeline step by step

import sys
sys.path.insert(0, '.')

from app import forecast_revenue_from_model
from datetime import datetime
import pandas as pd

print("=" * 80)
print("FORECAST PIPELINE DEBUG")
print("=" * 80)

# Test 1: Check current date recognition
print("\n1. DATE RECOGNITION TEST")
print("-" * 80)
today = pd.to_datetime(datetime.now().date())
print(f"Current date (today): {today}")
print(f"Current full datetime: {datetime.now()}")

# Test 2: Run forecast with debug
print("\n2. RUNNING FORECAST FUNCTION")
print("-" * 80)

question = "forecast revenue for next 3 months"
print(f"Question: {question}")

result = forecast_revenue_from_model(question)

# Check for errors
if "error" in result:
    print(f"ERROR: {result['error']}")
    sys.exit(1)

print(f"✓ No errors returned")

# Test 3: Check output structure
print("\n3. OUTPUT STRUCTURE CHECK")
print("-" * 80)

print(f"Output type: {result.get('output_type')}")
print(f"Intent: {result.get('intent')}")
print(f"Horizon: {result.get('horizon')}")
print(f"Frequency: {result.get('frequency')}")
print(f"Columns: {result.get('columns')}")
print(f"Number of results: {len(result.get('result', []))}")

# Test 4: Check actual dates in results
print("\n4. FORECAST DATES CHECK")
print("-" * 80)

results = result.get('result', [])

if not results:
    print("ERROR: No results returned!")
    sys.exit(1)

print(f"Total forecasts: {len(results)}")

# Show first 3 forecasts
for i, forecast in enumerate(results[:3]):
    if isinstance(forecast, dict):
        dt = forecast.get('Datetime', 'N/A')
        rev = forecast.get('Predicted_Revenue', 'N/A')
        print(f"  [{i+1}] {dt} => Revenue: {rev}")
    else:
        print(f"  [{i+1}] {forecast}")

# Test 5: Validate dates are in the future
print("\n5. FUTURE DATE VALIDATION")
print("-" * 80)

today = pd.to_datetime(datetime.now().date())
future_count = 0
past_count = 0

for forecast in results:
    if isinstance(forecast, dict):
        dt_str = forecast.get('Datetime', '')
        try:
            dt = pd.to_datetime(dt_str)
            if dt.date() >= today.date():
                future_count += 1
            else:
                past_count += 1
        except:
            pass

print(f"Forecasts in future: {future_count}")
print(f"Forecasts in past: {past_count}")

if future_count > 0:
    print("✓ SUCCESS: Forecasts are correctly in the future!")
else:
    print("✗ ERROR: All forecasts are in the past!")
    sys.exit(1)

print("\n" + "=" * 80)
print("ALL DEBUG TESTS PASSED")
print("=" * 80)
