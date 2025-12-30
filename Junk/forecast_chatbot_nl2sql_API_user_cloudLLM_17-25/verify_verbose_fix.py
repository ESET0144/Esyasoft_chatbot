
import sys
from unittest.mock import MagicMock
# Mocking the llm_router logic locally since we can't import print side-effects easily
# But we can import the function if we mock the dependencies?
# Let's just replicate the logic to test "this logic works on this object"

class MockMessage:
    def __init__(self, content):
        self.content = content

class MockResponse:
    def __init__(self, content):
        self.message = MockMessage(content)

def extract_content(resp):
    # This is the logic we just added to llm_router.py
    try:
        if hasattr(resp, "message") and hasattr(resp.message, "content"):
            return resp.message.content.strip()
        if isinstance(resp, dict):
            return resp.get("message", {}).get("content", "").strip()
    except Exception:
        pass
    return str(resp)

print("--- Testing Verbose Fix ---")

# Test Case 1: Object with message.content (The Issue)
obj_resp = MockResponse("Clean Summary")
extracted = extract_content(obj_resp)
print(f"Object Input -> Extracted: '{extracted}'")

if extracted == "Clean Summary":
    print("SUCCESS: Object extraction worked.")
else:
    print("FAILURE: Object extraction failed.")

# Test Case 2: Dict (Backward compatibility)
dict_resp = {"message": {"content": "Dict Summary"}}
extracted2 = extract_content(dict_resp)
print(f"Dict Input   -> Extracted: '{extracted2}'")

if extracted2 == "Dict Summary":
    print("SUCCESS: Dict extraction worked.")
else:
    print("FAILURE: Dict extraction failed.")
