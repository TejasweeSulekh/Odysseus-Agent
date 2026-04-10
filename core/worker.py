import sqlite3
import time
import os
import asyncio
import re
import subprocess
from llm_engine import ping_model

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'database', 'odysseus.db')

def fetch_pending_task():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT id, title, description, assigned_agent FROM tasks WHERE status = 'Backlog' ORDER BY created_at ASC LIMIT 1")
    task = cursor.fetchone()
    conn.close()
    return task

def update_task_status(task_id, new_status):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("UPDATE tasks SET status = ? WHERE id = ?", (new_status, task_id))
    conn.commit()
    conn.close()

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
    """Finds python code in the LLM output, saves it, and runs it."""
    # Look for standard markdown python code blocks
    match = re.search(r'```python\n(.*?)\n```', llm_output, re.DOTALL)
    
    if match:
        code = match.group(1)
        filename = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'workspace', f'task_{task_id}.py')
        
        # 1. Save the file to the disk
        with open(filename, "w") as f:
            f.write(code)
            
        # 2. Run the code and capture the output
        print(f"Executing {filename} on local machine...")
        try:
            result = subprocess.run(["python", filename], capture_output=True, text=True, timeout=10)
            
            execution_log = f"\n\n**Argus Execution Engine:**\n* Saved as `{filename}`\n"
            if result.stdout:
                execution_log += f"* **STDOUT:**\n```text\n{result.stdout}\n```\n"
            if result.stderr:
                execution_log += f"* **STDERR (Errors):**\n```text\n{result.stderr}\n```"
                
            return execution_log
            
        except subprocess.TimeoutExpired:
            return "\n\n**Argus Execution Engine:**\n* Error: Script execution timed out."
            
    return "\n\n**Argus Execution Engine:**\n* No executable Python block found in agent response."

async def execute_task(task_id, title, description, agent):
    """The actual brain of the worker."""
    print(f"\n[{agent} Agent] Picked up Task {task_id}: {title}")
    update_task_status(task_id, "In Progress")
    
    # 1. Get the agent's persona
    system_prompt = get_agent_prompt(agent)
    
    # 2. Add some context so the agent knows what to do
    action_prompt = f"Task: {title}\nDescription: {description}\n\nPlease execute this task and provide your reasoning."
    
    # 3. Ping the model!
    print(f"[{agent} Agent] Thinking...")
    llm_output = await ping_model(action_prompt, system_prompt)
    
    # 4. Save the thought process to the database for the UI
    if llm_output:
        # If it's the Coder, actually run the code it just wrote
        if agent == "Coder":
            execution_result = extract_and_run_code(llm_output, task_id)
            llm_output += execution_result  # Append the system result to the agent's thoughts
            
        log_execution(task_id, agent, llm_output)
    else:
        log_execution(task_id, agent, "Error: The agent failed to generate a response.")

    # 5. Move the card forward
    if agent == "Coder":
        update_task_status(task_id, "Review")
    else:
        update_task_status(task_id, "Done")

def worker_loop():
    print("Odysseus Worker threads started. Monitoring Backlog...")
    try:
        while True:
            task = fetch_pending_task()
            if task:
                task_id, title, description, agent = task
                # Run the async task execution
                asyncio.run(execute_task(task_id, title, description, agent))
            else:
                time.sleep(1)
                
    except KeyboardInterrupt:
        print("\nWorker threads shutting down gracefully.")

if __name__ == "__main__":
    worker_loop()