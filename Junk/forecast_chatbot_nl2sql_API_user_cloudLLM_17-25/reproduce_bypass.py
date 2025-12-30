
import re
from db import run_query, secure_run_query
from security import allowed_tables_for_role

# Simulate the Logic in nl2sql_pipeline.py
def simulate_pipeline(sql, role):
    print(f"--- Simulating Pipeline for role='{role}' SQL='{sql}' ---")
    
    # 1. Pipeline RBAC Check
    allowed_tables = allowed_tables_for_role(role)
    lower_sql = sql.lower()
    # Flawed Regex from nl2sql_pipeline.py
    tables_used = re.findall(r"(?:from|join)\s+([a-zA-Z_]+)", lower_sql)
    
    print(f"Pipeline extracted tables: {tables_used}")
    
    for table in set(tables_used):
        if table not in allowed_tables:
            print(f"Pipeline BLOCKED table '{table}'")
            return "BLOCKED"
            
    print("Pipeline PASSED check.")
    
# Test Case 3: Verify Fix (secure_run_query)
def test_secure_execution(sql, role):
    print(f"\n--- Testing secure_run_query for role='{role}' SQL='{sql}' ---")
    allowed = allowed_tables_for_role(role)
    print(f"Allowed tables: {allowed}")
    
    result = secure_run_query(sql, allowed)
    if "error" in result:
        print(f"Secure Execution BLOCKED: {result['error']}")
    else:
        print("Secure Execution SUCCESS (Bypass?)")

test_secure_execution('SELECT * FROM "Revenue_data" LIMIT 1;', "user")

