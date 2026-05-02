import sqlite3
import os

DB_PATH = os.path.join(os.path.dirname(__file__), 'odysseus.db')

def initialize_db():
    """Creates the SQLite tables if they do not exist."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # 1. TASKS TABLE (The Kanban Board)
    # Tracks the state of the work. Textual will read this to render the board.
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS tasks (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        title TEXT NOT NULL,
        description TEXT,
        status TEXT DEFAULT 'Backlog', -- States: Backlog, In Progress, Review, Done
        assigned_agent TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    ''')

    # 2. AGENTS TABLE (The Roster)
    # Defines the roles and system prompts for your workers.
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS agents (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT UNIQUE NOT NULL,
        role TEXT NOT NULL,
        system_prompt TEXT NOT NULL
    )
    ''')

    # 3. EXECUTION LOGS (The Hundred Eyes / Telemetry)
    # Stores the step-by-step thoughts and tool calls for the Watchdog and the UI side-panel.
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS execution_logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        task_id INTEGER,
        agent_name TEXT,
        thought TEXT,
        tool_name TEXT,
        tool_args TEXT, -- Stored as JSON string
        observation TEXT,
        timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY(task_id) REFERENCES tasks(id)
    )
    ''')
    
    # 4. CHAT MESSAGES (The UI Conversation)
    # Stores the back-and-forth chat between the user and the Supervisor.
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS chat_messages (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        role TEXT NOT NULL, -- 'user' or 'assistant'
        content TEXT NOT NULL,
        timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    ''')

    # Insert our default agents if they don't exist
    cursor.execute("INSERT OR IGNORE INTO agents (name, role, system_prompt) VALUES ('Supervisor', 'Orchestrator', 'You are the Supervisor. Break user requests into sub-tasks.')")
    
    coder_prompt = """You are the Coder. You interact with the system strictly by using tools.
You MUST output a valid JSON block to call a tool. Never output raw python blocks outside of the JSON args.

CRITICAL INSTRUCTIONS REGARDING INTERNET ACCESS:
You DO HAVE live internet access. You are equipped with the `search_web` tool.
NEVER say "I cannot perform live web searches" or "I am an AI." If you do not know something, or if the user asks for recent documentation, you MUST use the `search_web` tool to find the answer. Do not rely on your internal training data for recent libraries.

Available tools:
1. write_file(filename, content)
2. read_file(filename)
3. execute_bash(command)
4. list_directory(path)
5. search_web(query)
6. scrape_and_clean_web(url)
7. export_to_pdf(filename, content)

Example of searching the web:
```json
{
    "tool": "search_web",
    "args": {
        "query": "FastAPI background tasks documentation"
    }
}"""

    cursor.execute("INSERT OR IGNORE INTO agents (name, role, system_prompt) VALUES ('Coder', 'Executor', ?)", (coder_prompt,))
    
    reviewer_prompt = """You are the Lead QA Reviewer. Your job is to enforce Self-Reflection in the agentic loop.
You do NOT write code. You evaluate the execution logs of the Coder against the original task description.

CRITICAL INSTRUCTIONS:
1. Read the Task Description and the Coder's execution logs.
2. If the Coder's work completely satisfies the task, you must output exactly: [APPROVE]
3. If the Coder's work is incomplete, broken, or hallucinated, you must output a structured critique and end with: [REJECT]

If rejecting, use this exact format to guide the Coder's next attempt:
CRITIQUE: <Explain exactly what is missing or broken>
SUGGESTED NEXT TOOL: <Name the tool the Coder should use next, e.g., read_file or execute_bash>
VERDICT: [REJECT]
"""
    cursor.execute("INSERT OR IGNORE INTO agents (name, role, system_prompt) VALUES ('Reviewer', 'QA', ?)", (reviewer_prompt,))
    
    # Force update the Reviewer prompt in case the DB already exists
    cursor.execute("UPDATE agents SET system_prompt = ? WHERE name = 'Reviewer'", (reviewer_prompt,))
    
    # Force update the Coder prompt in case the DB already exists
    cursor.execute("UPDATE agents SET system_prompt = ? WHERE name = 'Coder'", (coder_prompt,))

    conn.commit()
    conn.close()
    print(f"Database initialized successfully at {DB_PATH}")

if __name__ == "__main__":
    initialize_db()