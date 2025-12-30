import sys
from unittest.mock import patch
import logging

# Configure logging to prevent error spam during test
logging.basicConfig(level=logging.CRITICAL)

from nl2sql_pipeline import handle_nl2sql

print("--- Testing Actual Pipeline Fix ---")

# Mock natural_to_sql to return --CANNOT_CONVERT--
with patch('nl2sql_pipeline.natural_to_sql', return_value="--CANNOT_CONVERT--"):
    result = handle_nl2sql("DROP TABLE customer_table;", "user", "schema", "cloud")
    
    print(f"Result Type: {result.get('output_type')}")
    print(f"Summary: {result.get('summary')}")
    
    if result.get("summary") == "I cannot answer this question because it might violate safety rules or is ambiguous.":
        print("SUCCESS: Pipeline correctly returned refusal message.")
    else:
        print("FAILURE: Pipeline did not catch CANNOT_CONVERT.")
