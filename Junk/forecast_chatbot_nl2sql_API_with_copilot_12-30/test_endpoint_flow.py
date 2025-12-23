#!/usr/bin/env python
# Simulate the /ask endpoint logic

import asyncio
import json
from app import classify_intent, forecast_revenue_from_model, decide_output_type

async def simulate_ask(question):
    """Simulate what the /ask endpoint does"""
    print(f"\nQuestion: {question}")
    print("-" * 70)
    
    # 1. Greeting check
    q_lower = question.strip().lower()
    greetings = ["hi", "hello", "hey"]
    if any(q_lower == g or q_lower.startswith(g + " ") for g in greetings):
        print("Response: Greeting detected - returning quick response")
        return
    
    # 2. Intent classification (NEW LAYER)
    intent = classify_intent(question)
    print(f"Intent Classification: {intent}")
    
    # 3. If python_model, use forecast handler
    if intent == "python_model":
        result = forecast_revenue_from_model(question)
        print(f"Using: forecast_revenue_from_model()")
        if "error" not in result:
            print(f"Result: SUCCESS - {result.get('output_type')} with {len(result.get('result', []))} forecasts")
            return
    
    # 4. Otherwise use nl2sql workflow
    print(f"Using: NL2SQL workflow")
    output_type = decide_output_type(question)
    print(f"Output Type Decision: {output_type}")
    print("Would proceed to: NL2SQL conversion -> Query execution -> Formatting")

# Test the flow
async def main():
    test_questions = [
        "revenue forecast for 11-12-2025",
        "show revenue forecast for 11-12-2025 total",
        "show customers",
        "what is the average load",
        "hello",
    ]
    
    print("=" * 70)
    print("ENDPOINT FLOW SIMULATION")
    print("=" * 70)
    
    for q in test_questions:
        await simulate_ask(q)
    
    print("\n" + "=" * 70)
    print("FLOW SIMULATION COMPLETE")
    print("=" * 70)

if __name__ == "__main__":
    asyncio.run(main())
