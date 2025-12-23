#!/usr/bin/env python
import requests
import json

try:
    # Test forecast endpoint
    response = requests.post(
        "http://127.0.0.1:8000/ask",
        json={"question": "forecast revenue for next 3 months"},
        timeout=10
    )
    
    print(f"Status: {response.status_code}")
    data = response.json()
    
    print(f"Output Type: {data.get('output_type')}")
    print(f"Intent: {data.get('intent')}")
    print(f"Horizon: {data.get('horizon')}")
    print(f"Columns: {data.get('columns')}")
    print(f"Result count: {len(data.get('result', []))}")
    
    if data.get('result'):
        print(f"First row: {data['result'][0]}")
    
    print("\n✓ SUCCESS - Forecast working!")
    
except Exception as e:
    print(f"✗ ERROR: {e}")
