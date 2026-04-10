import asyncio
import json
import sqlite3
import os
import re
from llm_engine import ping_model
import sys

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'database', 'odysseus.db')

# This is the system prompt that forces Gemma to act as the CTO/Orchestrator
SUPERVISOR_PROMPT = """You are the Supervisor of the Odysseus Agent OS.
Your job is to take a high-level user request and break it down into a sequence of actionable tasks.
Assign each task to either the 'Coder' (writes/executes code) or 'Reviewer' (checks for errors).

You must output ONLY a valid JSON array.

Example input: "Write a script to check my IP and review it."
Example output:
[
    {
        "title": "Write IP Check Script",
        "description": "Create a Python script that fetches the public IP address.",
        "assigned_agent": "Coder"
    },
    {
        "title": "Review IP Script",
        "description": "Test the IP script for network errors and edge cases.",
        "assigned_agent": "Reviewer"
    }
]

Do not include any other text, markdown, or explanations. Just the JSON array.
"""

def clean_json(text):
    """LLMs sometimes wrap JSON in markdown blocks (```json ... ```). This strips it out."""
    text = re.sub(r'^```json\s*', '', text, flags=re.MULTILINE|re.IGNORECASE)
    text = re.sub(r'^```\s*$', '', text, flags=re.MULTILINE)
    return text.strip()

async def orchestrate(user_request: str):
    print(f"Supervisor analyzing request: '{user_request}'...")
    
    # 1. Send the request to local Gemma 4
    raw_response = await ping_model(user_request, SUPERVISOR_PROMPT)
    
    if not raw_response or raw_response.strip() == "":
        print("\n[Watchdog Alert] The LLM returned an empty response. The model might be struggling with the prompt format.")
        return
    
    # 2. Parse the output into a Python list of dictionaries
    try:
        cleaned_response = clean_json(raw_response)
        tasks = json.loads(cleaned_response)
        
        # 3. Save the tasks to the SQLite Database
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        for task in tasks:
            # We insert them into the 'Backlog' column by default
            cursor.execute(
                "INSERT INTO tasks (title, description, status, assigned_agent) VALUES (?, ?, ?, ?)",
                (task['title'], task['description'], 'Backlog', task['assigned_agent'])
            )
            
        conn.commit()
        conn.close()
        print(f"\nSuccess! Added {len(tasks)} new tasks to the database.")
        
    except json.JSONDecodeError:
        print("\n[Watchdog Alert] The model failed to output valid JSON. This is why we build error loops!")
        print("Raw output:", raw_response)
    except KeyError as e:
        print(f"\n[Watchdog Alert] JSON was valid, but missing a required key: {e}")

if __name__ == "__main__":
    # If an argument is passed from main.py, use it. Otherwise, use a fallback.
    if len(sys.argv) > 1:
        goal = sys.argv[1]
    else:
        goal = "Write a Python script that checks my disk space and saves a warning to a text file if it is over 90% full. Then review the script."
        
    asyncio.run(orchestrate(goal))