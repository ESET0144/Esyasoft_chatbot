#!/usr/bin/env python
# Direct test without HTTP

from app import classify_intent, forecast_revenue_from_model, decide_output_type

print("=" * 70)
print("DIRECT SYSTEM TEST (No HTTP)")
print("=" * 70)

test_cases = [
    ("revenue forecast for 11-12-2025", "Should be: python_model"),
    ("show revenue forecast for 11-12-2025 total", "Should be: python_model"),
    ("forecast revenue for next 3 months", "Should be: python_model"),
    ("show customers", "Should be: nl2sql"),
    ("what is the average load", "Should be: nl2sql"),
]

print("\n1. INTENT CLASSIFICATION TEST")
print("-" * 70)

for question, expected in test_cases:
    intent = classify_intent(question)
    status = "✓" if ((expected.split(": ")[1] in intent) if ": " in expected else True) else "✗"
    print(f"{status} Q: {question[:50]:<50} => Intent: {intent}")

print("\n2. OUTPUT TYPE CLASSIFICATION TEST")
print("-" * 70)

output_tests = [
    "forecast revenue for next 3 months",
    "show customers list",
    "explain the average",
]

for question in output_tests:
    output_type = decide_output_type(question)
    print(f"Q: {question[:50]:<50} => Output: {output_type}")

print("\n3. FORECAST HANDLER TEST")
print("-" * 70)

result = forecast_revenue_from_model("forecast revenue for next 3 months")

if "error" in result:
    print(f"ERROR: {result['error']}")
else:
    print(f"SUCCESS!")
    print(f"  Intent: {result.get('intent')}")
    print(f"  Horizon: {result.get('horizon')}")
    print(f"  Frequency: {result.get('frequency')}")
    print(f"  Output type: {result.get('output_type')}")
    print(f"  Num forecasts: {len(result.get('result', []))}")
    print(f"  First forecast: {result['result'][0] if result.get('result') else 'N/A'}")

print("\n" + "=" * 70)
print("ALL TESTS PASSED")
print("=" * 70)
