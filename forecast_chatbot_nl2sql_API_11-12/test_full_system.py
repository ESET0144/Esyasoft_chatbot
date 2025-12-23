#!/usr/bin/env python
# Test the complete chatbot flow

import requests
import json
import time

BASE_URL = "http://127.0.0.1:8001"

# Wait a moment for the server to be ready
time.sleep(2)

test_questions = [
    "revenue forecast for 11-12-2025",
    "show revenue forecast for 11-12-2025 total",
    "forecast revenue for next 3 months",
    "predict next 6 months revenue",
    "show customers",
    "what is the average load"
]

print("=" * 70)
print("CHATBOT SYSTEM TEST")
print("=" * 70)

for i, question in enumerate(test_questions, 1):
    print(f"\n[Test {i}] Question: {question}")
    print("-" * 70)
    
    try:
        response = requests.post(
            f"{BASE_URL}/ask",
            json={"question": question},
            timeout=10
        )
        
        if response.status_code == 200:
            data = response.json()
            print(f"Status: SUCCESS (200)")
            print(f"Intent/Output Type: {data.get('output_type', data.get('intent', 'N/A'))}")
            if data.get("intent") == "python_model":
                print(f"Forecast Horizon: {data.get('horizon')} periods")
                print(f"Frequency: {data.get('frequency')}")
                print(f"Number of forecasts: {len(data.get('result', []))}")
            elif data.get("summary"):
                print(f"Summary: {data.get('summary')[:100]}...")
            print(f"Columns: {data.get('columns', [])}")
        else:
            print(f"Status: FAILED ({response.status_code})")
            print(f"Response: {response.text[:200]}")
    
    except Exception as e:
        print(f"Status: ERROR")
        print(f"Error: {str(e)}")

print("\n" + "=" * 70)
print("TEST COMPLETE")
print("=" * 70)
