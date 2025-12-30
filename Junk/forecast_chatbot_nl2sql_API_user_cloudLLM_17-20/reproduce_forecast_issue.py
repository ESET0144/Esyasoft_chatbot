
from forecast_pipeline import forecast_revenue
import logging

# Setup Logger to avoid clutter
logging.basicConfig(level=logging.ERROR)

print("--- Testing Forecast Pipeline Security (Fix Verification) ---")

question = "show me revenue forecast for next year"
print(f"Question: {question}")

# Test Case 1: USER ROLE (Should be DENIED)
print("\n[TEST] Role = 'user'")
try:
    result = forecast_revenue(question, role="user")
    
    if result.get("output_type") == "error" and "Access Denied" in result.get("error", ""):
        print("SUCCESS: Access was correctly DENIED for user role.")
    else:
        print(f"FAILURE: User role was NOT blocked! Result: {result.get('summary')}")

except Exception as e:
    print(f"Execution Error (User): {e}")

# Test Case 2: ADMIN ROLE (Should be ALLOWED)
print("\n[TEST] Role = 'admin'")
try:
    result = forecast_revenue(question, role="admin")
    
    if result.get("output_type") == "forecast":
        print("SUCCESS: Access was GRANTED for admin role.")
    else:
        print(f"FAILURE: Admin role was blocked or failed! Result: {result}")

except Exception as e:
    print(f"Execution Error (Admin): {e}")
