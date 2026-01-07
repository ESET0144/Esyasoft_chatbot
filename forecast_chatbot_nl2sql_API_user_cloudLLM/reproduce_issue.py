import re
from datetime import datetime
import pandas as pd

def parse_reference_date(prompt: str):
    print(f"Testing prompt: '{prompt}'")
    patterns = [
        r'(\d{2}-\d{2}-\d{4})',
        r'(\d{4}-\d{2}-\d{2})',
        r'(\d{2}\s+[A-Za-z]{3,9}\s+\d{4})'
    ]

    for p in patterns:
        m = re.search(p, prompt)
        if m:
            s = m.group(1)
            print(f"  Match found: '{s}' with pattern '{p}'")
            for fmt in ("%d-%m-%Y", "%Y-%m-%d", "%d %b %Y", "%d %B %Y"):
                try:
                    dt = datetime.strptime(s, fmt)
                    print(f"  Successfully parsed with format '{fmt}': {dt}")
                    return dt
                except Exception as e:
                    # print(f"  Failed format '{fmt}': {e}")
                    continue
        else:
            print(f"  No match for pattern '{p}'")

    # fallback: pandas
    print("  Attempting pandas fallback...")
    try:
        ts = pd.to_datetime(prompt, dayfirst=True, errors='coerce')
        if not pd.isnull(ts):
            print(f"  Pandas parsed: {ts}")
            return ts.to_pydatetime()
        else:
            print("  Pandas returned NaT")
    except Exception as e:
        print(f"  Pandas error: {e}")

    return None

# Test Cases
prompts = [
    "show me revenue forecast for 1-1-2020",
    "show me revenue forecast for 11-12-2020",
    "forecast for 2020-01-01",
    "show me revenue forecast for 01-01-2020"
]

for p in prompts:
    print("-" * 20)
    res = parse_reference_date(p)
    if res is None:
        print("RESULT: FAIL (None)")
    else:
        print(f"RESULT: SUCCESS ({res})")
