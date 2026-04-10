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

    # Insert our default agents if they don't exist
    cursor.execute("INSERT OR IGNORE INTO agents (name, role, system_prompt) VALUES ('Supervisor', 'Orchestrator', 'You are the Supervisor. Break user requests into sub-tasks.')")
    cursor.execute("INSERT OR IGNORE INTO agents (name, role, system_prompt) VALUES ('Coder', 'Executor', 'You write Python code to solve tasks.')")
    cursor.execute("INSERT OR IGNORE INTO agents (name, role, system_prompt) VALUES ('Reviewer', 'QA', 'You review code for errors and logic flaws.')")

    conn.commit()
    conn.close()
    print(f"Database initialized successfully at {DB_PATH}")

if __name__ == "__main__":
    initialize_db()