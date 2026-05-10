import asyncio
import json
import time
import sys
import os

# Ensure absolute imports work when run directly
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.llm_engine import ping_model
from core.supervisor import SUPERVISOR_PROMPT
from core.telemetry import get_llm_metrics

# The synthetic dataset to test our Router's intelligence
TEST_CASES = [
    {
        "name": "Simple Greeting",
        "prompt": "Hello Odysseus, how are you today?",
        "expected_intent": "chat"
    },
    {
        "name": "Direct Tool Question",
        "prompt": "What files are in my workspace?",
        "expected_intent": "chat"
    },
    {
        "name": "Explicit Build Command",
        "prompt": "Build a python script that calculates the Fibonacci sequence and save it to math.py",
        "expected_intent": "orchestrate"
    },
    {
        "name": "Tricky Edge Case (Asking about code vs Writing code)",
        "prompt": "Can you explain how a React component works?",
        "expected_intent": "chat"
    }
]

async def run_evals():
    print("===========================================")
    print("🚀 INITIATING ODYSSEUS EVALUATION PIPELINE")
    print("===========================================\n")
    
    passed = 0
    total = len(TEST_CASES)
    total_tps = 0.0
    
    for i, test in enumerate(TEST_CASES):
        print(f"Test {i+1}/{total}: {test['name']}")
        print(f"Prompt: '{test['prompt']}'")
        
        start_time = time.time()
        
        # Ping the router directly
        raw_response = await ping_model(f"USER COMMAND: {test['prompt']}", SUPERVISOR_PROMPT)
        
        # Fetch the telemetry from the database to check speed
        metrics = get_llm_metrics()
        total_tps += metrics['tps']
        
        # Assertions
        try:
            clean_response = raw_response.replace("```json", "").replace("```", "").strip()
            parsed_data = json.loads(clean_response)
            actual_intent = parsed_data.get("intent", "UNKNOWN")
            
            if actual_intent == test['expected_intent']:
                print(f"✅ PASS | Intent: {actual_intent} | Speed: {metrics['tps']} T/s")
                passed += 1
            else:
                print(f"❌ FAIL | Expected: {test['expected_intent']}, Got: {actual_intent}")
                print(f"   Raw Output: {clean_response}")
                
        except json.JSONDecodeError:
            print("❌ FAIL | Model failed to output valid JSON schema.")
            print(f"   Raw Output: {raw_response}")
            
        print("-" * 40)
        
    print("\n===========================================")
    print("📊 EVALUATION REPORT")
    print("===========================================")
    print(f"Success Rate:   {(passed/total)*100}% ({passed}/{total})")
    print(f"Average Speed:  {round(total_tps/total, 2)} Tokens/sec")
    print("===========================================\n")

if __name__ == "__main__":
    # Suppress standard print statements from llm_engine to keep the report clean
    sys.stdout = open(os.devnull, 'w')
    # Save original stdout to restore it for our custom print statements
    original_stdout = sys.__stdout__
    
    async def main():
        sys.stdout = original_stdout
        await run_evals()
        
    asyncio.run(main())