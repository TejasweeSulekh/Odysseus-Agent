import sqlite3
import time
import os
import asyncio
import re
import subprocess
import json
from core.llm_engine import ping_model
from core.tools import process_tool_call

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'database', 'odysseus.db')

def fetch_pending_task():
    """Grabs the oldest task that needs either Coding or Reviewing."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT id, title, description, assigned_agent FROM tasks WHERE status IN ('Backlog', 'Review') ORDER BY created_at ASC LIMIT 1")
    task = cursor.fetchone()
    conn.close()
    return task

def get_agent_prompt(agent_name):
    """Fetches the specific instructions for the Coder or Reviewer."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT system_prompt FROM agents WHERE name = ?", (agent_name,))
    row = cursor.fetchone()
    conn.close()
    return row[0] if row else "You are a helpful AI assistant."

def log_execution(task_id, agent_name, thought):
    """Saves the LLM's output so the Textual UI can display it."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO execution_logs (task_id, agent_name, thought) VALUES (?, ?, ?)",
        (task_id, agent_name, thought)
    )
    conn.commit()
    conn.close()

def extract_and_run_code(llm_output, task_id):
    """
    Returns a tuple: (is_success: bool, execution_result_or_error: str)
    """
    match = re.search(r'```json\n(.*?)\n```', llm_output, re.DOTALL)
    
    if match:
        json_str = match.group(1).strip()
        try:
            tool_data = json.loads(json_str)
            tool_name = tool_data.get("tool")
            tool_args = tool_data.get("args", {})
            
            if not tool_name:
                return False, "\n\n**Argus Execution Engine:**\n* ERROR: JSON found, but missing 'tool' key."

            print(f"Executing Tool: {tool_name} on local machine...")
            observation = process_tool_call(tool_name, tool_args)
            
            execution_log = f"\n\n**Argus Execution Engine (Tool: {tool_name}):**\n"
            execution_log += f"```text\n{observation}\n```\n"
            
            return True, execution_log
            
        except json.JSONDecodeError as e:
            # We catch the exact parsing error for the Healing Loop
            return False, f"\n\n**Argus Execution Engine:**\n* SYNTAX ERROR: {str(e)}\nYour JSON is malformed. Fix the syntax and try again."
            
    return False, "\n\n**Argus Execution Engine:**\n* ERROR: No valid JSON tool call block found in agent response."

def get_task_history(task_id):
    """Filters history to prevent Context Window Poisoning. 
    Only returns successful tool observations and the latest QA feedback."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT agent_name, thought FROM execution_logs WHERE task_id = ? ORDER BY timestamp ASC", (task_id,))
    logs = cursor.fetchall()
    conn.close()
    
    history = ""
    successful_actions = ""
    last_reviewer_feedback = ""

    for log_agent, thought in logs:
        # Skip the verbose system watchdog logs so the LLM doesn't get confused
        if log_agent.startswith("System"):
            continue

        if log_agent == "Coder":
            # Extract ONLY the tool's output, leaving behind any broken JSON syntax
            if "**Argus Execution Engine" in thought:
                parts = thought.split("**Argus Execution Engine")
                if len(parts) > 1:
                    successful_actions += f"\n--- Previous Tool Execution ---\n**Argus Execution Engine{parts[1]}\n"

        elif log_agent == "Reviewer":
            # Overwrite with the most recent feedback
            if "REJECT" in thought.upper():
                last_reviewer_feedback = thought

    # Assemble the clean, distilled memory
    if successful_actions:
        history += f"\n### COMPLETED TOOL ACTIONS:\n{successful_actions}\n"
    if last_reviewer_feedback:
        history += f"\n### LATEST QA FEEDBACK (MUST FIX):\n{last_reviewer_feedback}\n"

    return history

async def execute_task(task_id, title, description, agent):
    """The actual brain of the worker, now with Strict QA and Verbose Logging."""
    print(f"\n[{agent} Agent] Picked up Task {task_id}: {title}")
    
    conn = sqlite3.connect(DB_PATH)
    conn.cursor().execute("UPDATE tasks SET status = 'In Progress' WHERE id = ?", (task_id,))
    conn.commit()
    conn.close()
    
    system_prompt = get_agent_prompt(agent)
    base_prompt = f"Task: {title}\nDescription: {description}\n"
    
    history = get_task_history(task_id)
    if history:
        base_prompt += f"\n--- PREVIOUS WORK HISTORY ---\n{history}\n---------------------------\n"
    
    # --- IDENTITY ENFORCEMENT ---
    if agent == "Reviewer":
        base_prompt += "\nCRITICAL INSTRUCTION: You are the QA Reviewer. DO NOT write or execute new code. Evaluate the execution logs above AGAINST THE TASK DESCRIPTION. If the task description is fully complete (e.g., both researched AND written), end your response with exactly: [APPROVE]. If the task is incomplete (e.g., the Coder searched but hasn't written the file yet), explain what is missing and end with: [REJECT]."
    else:
        base_prompt += """
CRITICAL INSTRUCTION: You are the Coder. You execute complex tasks ONE STEP AT A TIME.
1. Read the task description and the PREVIOUS WORK HISTORY.
2. Determine the SINGLE next tool you need to call to progress the task.
   - If you need information you don't have, use `search_web`.
   - If you already have the information in your history, use `write_file`.
3. You MUST output a valid JSON block to call ONE tool. Do not try to call multiple tools at once.
"""

    MAX_RETRIES = 3
    attempt = 0
    success = False
    llm_output = ""
    action_prompt = base_prompt
    
    # --- Verbose UI Logging (Start) ---
    log_execution(task_id, "System", f"Starting {agent} execution loop. Max retries: {MAX_RETRIES}")

    while attempt < MAX_RETRIES and not success:
        if attempt > 0:
            retry_msg = f"Attempt {attempt}/{MAX_RETRIES} failed. Triggering TurboQuant Healing Loop..."
            print(f"[{agent} Agent] [HEALING] {retry_msg}")
            log_execution(task_id, "System-Watchdog", retry_msg)

        print(f"[{agent} Agent] Thinking (Attempt {attempt + 1})...")
        llm_output = await ping_model(action_prompt, system_prompt)

        if not llm_output or llm_output.strip() == "":
            # Handle the "Silent Hallucination" gracefully
            is_valid = False
            execution_result = "ERROR: The local model returned an empty response. You must generate valid JSON."
            llm_output = "*(Model returned empty response)*"
        elif agent == "Coder":
            is_valid, execution_result = extract_and_run_code(llm_output, task_id)
            llm_output += execution_result
        else:
            is_valid = True
            execution_result = ""

        if is_valid:
            success = True
        else:
            attempt += 1
            action_prompt = base_prompt + f"\n\nYOUR PREVIOUS ATTEMPT FAILED WITH THIS ERROR:\n{execution_result}\n\nPlease correct your logic and try again."

    # Process and Log the final LLM output
    log_execution(task_id, agent, llm_output)

    # --- STRICT QA ROUTING ---
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    if agent == "Coder":
        cursor.execute("UPDATE tasks SET status = 'Review', assigned_agent = 'Reviewer' WHERE id = ?", (task_id,))
    elif agent == "Reviewer":
        # Default-Deny: It MUST contain [APPROVE] to pass.
        if "[APPROVE]" in llm_output.upper() and "STDERR" not in history:
            print(f"[{agent} Agent] QA PASSED. Task Complete.")
            log_execution(task_id, "System-QA", "QA Passed. Moving to Done.")
            cursor.execute("UPDATE tasks SET status = 'Done' WHERE id = ?", (task_id,))
        else:
            print(f"[{agent} Agent] QA FAILED. Sending back to Coder.")
            log_execution(task_id, "System-QA", "QA Failed or response was invalid. Returning to Backlog.")
            # Send it back to the Backlog so the fetcher can see it
            cursor.execute("UPDATE tasks SET status = 'Backlog', assigned_agent = 'Coder' WHERE id = ?", (task_id,))
            
    conn.commit()
    conn.close()

def worker_loop():
    print("Odysseus Worker threads started. Monitoring Backlog...")
    try:
        while True:
            task = fetch_pending_task()
            if task:
                task_id, title, description, agent = task
                asyncio.run(execute_task(task_id, title, description, agent))
            else:
                time.sleep(1)
                
    except KeyboardInterrupt:
        print("\nWorker threads shutting down gracefully.")

if __name__ == "__main__":
    worker_loop()