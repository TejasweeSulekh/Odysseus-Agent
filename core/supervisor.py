import asyncio
import json
import sqlite3
import os
import re
from core.llm_engine import ping_model
import sys

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'database', 'odysseus.db')

SUPERVISOR_PROMPT = """You are Odysseus, the master AI OS Supervisor.
You have TWO modes of operation:

MODE 1: CHAT
If the user is asking a general question, reply as a helpful AI assistant.

MODE 2: ORCHESTRATE (Task Generation)
If the user explicitly asks you to BUILD, WRITE CODE, CREATE A FILE, or EXECUTE A SCRIPT, transition to Orchestrate Mode.
Output ONLY a JSON array of tasks. Assign EVERY task to the 'Coder'.

CRITICAL TASK GROUPING RULE: 
Do NOT over-fragment tasks. If a goal requires researching a topic and THEN writing a file, combine them into a SINGLE task. This ensures the Coder has the research in its short-term memory when writing the code.

Example JSON Output:
```json
[
    {
        "title": "Research and Write Server",
        "description": "Use search_web to find FastAPI documentation, then use write_file to create server.py.",
        "assigned_agent": "Coder"
    }
]
```
"""

def clean_json(text):
    text = re.sub(r'^```json\s*', '', text, flags=re.MULTILINE|re.IGNORECASE)
    text = re.sub(r'^```\s*$', '', text, flags=re.MULTILINE)
    return text.strip()

def save_chat(role, content):
    """Saves a message to the chat history."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("INSERT INTO chat_messages (role, content) VALUES (?, ?)", (role, content))
    conn.commit()
    conn.close()

def get_chat_history():
    """Fetches the last 5 messages to give the Supervisor short-term memory."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT role, content FROM chat_messages ORDER BY timestamp DESC LIMIT 5")
    rows = cursor.fetchall()
    conn.close()
    
    # Reverse to get chronological order
    history = ""
    for role, content in reversed(rows):
        history += f"\n{role.upper()}: {content}"
    return history

def extract_task_json(text):
    """Cleanly extracts a JSON array from the model's output."""
    # 1. First, try to cleanly split by the markdown block
    if "```json" in text.lower():
        parts = re.split(r'```json', text, flags=re.IGNORECASE)
        if len(parts) > 1:
            content = parts[1].split('```')[0].strip()
            if content.startswith('['):
                return content
                
    # 2. Fallback: Just grab everything between the first '[' and last ']'
    start_idx = text.find('[')
    end_idx = text.rfind(']')
    
    if start_idx != -1 and end_idx != -1 and end_idx > start_idx:
        potential_json = text[start_idx:end_idx+1]
        return potential_json
        
    return None

async def orchestrate(user_request: str):
    # --- NEW: Synthesis Hook & Auto-Wipe ---
    if user_request == "[SYSTEM] TASK_BATCH_COMPLETE":
        print("\nSupervisor synthesizing completed tasks...")
        
        # Grab the execution logs from the tasks that just finished
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("""
            SELECT t.title, e.agent_name, e.thought 
            FROM tasks t 
            JOIN execution_logs e ON t.id = e.task_id 
            WHERE t.status = 'Done'
        """)
        logs = cursor.fetchall()

        log_text = ""
        for title, agent, thought in logs:
            log_text += f"Task: {title} | Agent: {agent}\nLog: {thought}\n---\n"

        synthesis_prompt = f"""You are Odysseus, the master AI OS. Your agents have just completed a batch of tasks.
Read the execution logs below and present the FINAL RESULT to the user.

CRITICAL INSTRUCTION: Do NOT just say "the task is complete." You must actually show the user the work that was produced! 
- If the agents wrote a file, present the findings using native Markdown formatting (use # for headers, ** for bold, etc.).
- DO NOT wrap your entire response in a single ``` code block. Allow the Markdown to render naturally.
- Cut the fluff. Deliver the payload.

EXECUTION LOGS:
{log_text}"""

        summary = await ping_model(synthesis_prompt, "You are a helpful AI OS Supervisor.")
        if not summary: summary = "All tasks have been successfully completed."
        
        save_chat("assistant", summary)
        
        # WIPE THE KANBAN BOARD FOR THE NEXT COMMAND
        cursor.execute("DELETE FROM tasks")
        cursor.execute("DELETE FROM execution_logs")
        conn.commit()
        conn.close()
        
        return summary

    # --- Standard Routing (Existing Logic) ---
    save_chat("user", user_request)
    history = get_chat_history()
    prompt = f"Recent Chat History:{history}\n\nUSER COMMAND: {user_request}"
    
    print(f"Supervisor processing command: '{user_request}'...")
    raw_response = await ping_model(prompt, SUPERVISOR_PROMPT)
    
    if not raw_response or raw_response.strip() == "":
        return "Error: Local LLM returned an empty response."

    json_str = extract_task_json(raw_response)
    
    if json_str:
        try:
            tasks = json.loads(json_str)
            conn = sqlite3.connect(DB_PATH)
            cursor = conn.cursor()
            for task in tasks:
                cursor.execute(
                    "INSERT INTO tasks (title, description, status, assigned_agent) VALUES (?, ?, ?, ?)",
                    (task['title'], task['description'], 'Backlog', task['assigned_agent'])
                )
            conn.commit()
            conn.close()
            
            system_reply = f"[SYSTEM] Agentic Mode Triggered. Dispatched {len(tasks)} tasks to the Kanban board."
            save_chat("assistant", system_reply)
            print(f"\n{system_reply}")
            return system_reply
            
        except json.JSONDecodeError:
            print("\n[Watchdog] Found array brackets, but JSON was invalid. Falling back to chat.")
            pass 
            
    save_chat("assistant", raw_response)
    print("\n[Chat Mode Response]\n" + raw_response)
    return raw_response

if __name__ == "__main__":
    if len(sys.argv) > 1:
        goal = sys.argv[1]
        asyncio.run(orchestrate(goal))
    else:
        print("Please provide a command. Example: python supervisor.py 'hello'")