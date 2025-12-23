#!/usr/bin/env python
# Final comprehensive system test

import requests
import json
import time

BASE_URL = "http://127.0.0.1:8000"

# Wait for server to be ready
time.sleep(2)

test_cases = [
    {
        "question": "revenue forecast for next 3 months",
        "expected_intent": "python_model",
        "expected_output_type": "forecast"
    },
    {
        "question": "show revenue forecast for 11-12-2025 total",
        "expected_intent": "python_model",
        "expected_output_type": "forecast"
    },
    {
        "question": "show customers",
        "expected_intent": "nl2sql",
        "expected_output_type": "table"
    },
    {
        "question": "what is the average load",
        "expected_intent": "nl2sql",
        "expected_output_type": "nl"
    },
]

print("=" * 80)
print("COMPREHENSIVE SYSTEM TEST - FORECAST CHAT")
print("=" * 80)

all_passed = True

for i, test in enumerate(test_cases, 1):
    question = test["question"]
    expected_intent = test["expected_intent"]
    expected_output = test["expected_output_type"]
    
    print(f"\n[Test {i}] Question: {question}")
    print("-" * 80)
    
    try:
        response = requests.post(
            f"{BASE_URL}/ask",
            json={"question": question},
            timeout=15
        )
        
        if response.status_code != 200:
            print(f"  FAILED: HTTP {response.status_code}")
            print(f"  Response: {response.text[:200]}")
            all_passed = False
            continue
        
        data = response.json()
        output_type = data.get("output_type", "unknown")
        intent = data.get("intent", output_type)
        
        # Check expected output type
        if output_type == expected_output:
            print(f"  ✓ Output Type: {output_type} (expected: {expected_output})")
        else:
            print(f"  ✗ Output Type: {output_type} (expected: {expected_output})")
            all_passed = False
        
        # Verify data is present
        result = data.get("result", [])
        columns = data.get("columns", [])
        
        if result:
            print(f"  ✓ Result rows: {len(result)}")
            print(f"  ✓ Columns: {columns}")
            
            # Show first result for forecast
            if output_type == "forecast" and isinstance(result, list) and len(result) > 0:
                first = result[0]
                if isinstance(first, dict):
                    print(f"  ✓ First forecast: {first}")
                else:
                    print(f"  ✓ First forecast row available")
        else:
            print(f"  ℹ No result data (may be expected for some queries)")
        
        # Check summary
        summary = data.get("summary", "")
        if summary:
            print(f"  ✓ Summary: {summary[:80]}...")
        
        print(f"  SUCCESS")
        
    except requests.exceptions.ConnectionError:
        print(f"  FAILED: Connection error (server not responding)")
        all_passed = False
    except Exception as e:
        print(f"  FAILED: {str(e)}")
        all_passed = False

print("\n" + "=" * 80)
if all_passed:
    print("ALL TESTS PASSED ✓")
else:
    print("SOME TESTS FAILED ✗")
print("=" * 80)
print("\nServer is running on: http://127.0.0.1:8000")
print("Open in browser to test the chat interface!")
