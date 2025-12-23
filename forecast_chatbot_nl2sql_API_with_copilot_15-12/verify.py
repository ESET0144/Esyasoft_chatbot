#!/usr/bin/env python
import time
time.sleep(3)  # Wait for server to start
import requests
response = requests.post("http://127.0.0.1:8000/ask", json={"question": "forecast next 3"}, timeout=5)
print(response.json())
