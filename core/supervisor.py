import asyncio
import json
import sqlite3
import os
import re
import sys

# --- Add project root to sys.path before core imports ---
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.llm_engine import ping_model
from core.tools import process_tool_call

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'database', 'odysseus.db')

FAST_PATH_PROMPT = """You are Odysseus, a fast and helpful AI OS assistant.
You have access to tools. 

If you DO NOT need a tool, output your final answer directly in plain text/markdown.
If you DO need a tool, output STRICTLY a JSON block and nothing else.

AVAILABLE TOOLS:
- search_web(query)
- list_directory(path)
- read_file(filename)
- scrape_and_clean_web(url)
- export_to_pdf(filename, content)

To use a tool, use this exact format:
```json
{
    "tool": "list_directory",
    "args": {"path": "."}
}
"""

SUPERVISOR_PROMPT = """You are Odysseus, the master AI OS Supervisor.
Your ONLY job is to classify the user's intent and output a STRICT JSON object.

You have TWO modes of operation:
1. "chat" (Fast-Path): For general questions, brainstorming, or simple requests.
2. "orchestrate" (Slow-Path): IF AND ONLY IF the user explicitly asks you to BUILD, WRITE CODE, CREATE A FILE, or EXECUTE A SCRIPT.

CRITICAL INSTRUCTION:
You MUST output ONLY valid JSON. No markdown formatting, no conversational filler, no backticks.
Your output must exactly match one of these two schemas:

SCHEMA 1 (Chat):
{
    "intent": "chat",
    "payload": "Your helpful response to the user's question."
}

SCHEMA 2 (Orchestrate):
{
    "intent": "orchestrate",
    "payload": [
        {
            "title": "Task Name",
            "description": "Detailed instructions on what to do.",
            "assigned_agent": "Coder"
        }
    ]
}
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


async def fast_react_loop(user_command: str, history: str) -> str:
    """Executes an in-memory Reason+Act loop."""
    context = f"Recent History:\n{history}\n\nUSER COMMAND: {user_command}\n"
    max_steps = 3
    
    for step in range(max_steps):
        print(f"  [Fast-Path] Loop {step+1}/{max_steps} - Thinking...")
        response = await ping_model(context, FAST_PATH_PROMPT)
        
        # Check if the model outputted a markdown JSON block (tool call)
        if "```json" in response:
            try:
                # Extract and parse the JSON
                json_text = response.split("```json")[1].split("```")[0].strip()
                tool_data = json.loads(json_text)
                
                tool_name = tool_data.get("tool")
                tool_args = tool_data.get("args", {})
                
                print(f"  [Fast-Path] Action Triggered: {tool_name}({tool_args})")
                observation = process_tool_call(tool_name, tool_args)
                
                # Append the execution result to the context and let it loop again
                context += f"\nAgent: {response}\nObservation: {observation}\n"
                
            except Exception as e:
                # Healing: If the JSON is broken, feed the error back to the model
                print(f"  [Fast-Path] Syntax Error: {e}")
                context += f"\nAgent: {response}\nSystem Error: Invalid JSON syntax ({str(e)}). Fix it and try again.\n"
        else:
            # No JSON found, assume it is the final synthesized answer
            return response
            
    return "Error: Fast-Path ReAct loop timed out before reaching a final answer."

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

    # --- Deterministic JSON Routing ---
    try:
        # Clean potential markdown backticks just in case the model hallucinates them
        clean_response = raw_response.replace("```json", "").replace("```", "").strip()
        parsed_data = json.loads(clean_response)
        
        intent = parsed_data.get("intent", "chat")
        payload = parsed_data.get("payload", "I could not process that request.")

        if intent == "orchestrate" and isinstance(payload, list):
            # SLOW-PATH: Push to Kanban
            conn = sqlite3.connect(DB_PATH)
            cursor = conn.cursor()
            for task in payload:
                cursor.execute(
                    "INSERT INTO tasks (title, description, status, assigned_agent) VALUES (?, ?, ?, ?)",
                    (task.get('title', 'Untitled'), task.get('description', ''), 'Backlog', task.get('assigned_agent', 'Coder'))
                )
            conn.commit()
            conn.close()
            
            system_reply = f"[SYSTEM] Agentic Mode Triggered. Dispatched {len(payload)} tasks to the Kanban board."
            save_chat("assistant", system_reply)
            print(f"\n{system_reply}")
            return system_reply
            
        else:
            # FAST-PATH: Direct Chat via ReAct Loop
            # Instead of just returning the static payload, we unleash the ReAct loop
            print(f"\n[Fast-Path] Routing to ReAct Engine...")
            
            # We pass the original user_request so the loop knows what to solve
            final_answer = await fast_react_loop(user_request, history)
            
            save_chat("assistant", final_answer)
            print("\n[Fast-Path Chat Response]\n" + final_answer)
            return final_answer

    except json.JSONDecodeError:
        # Fallback if the 4B model completely fails the schema
        print("\n[Watchdog] Supervisor failed to output valid JSON. Falling back to raw text.")
        save_chat("assistant", raw_response)
        return raw_response

if __name__ == "__main__":
    if len(sys.argv) > 1:
        goal = sys.argv[1]
        asyncio.run(orchestrate(goal))
    else:
        print("Please provide a command. Example: python supervisor.py 'hello'")