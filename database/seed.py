import sqlite3
import os

DB_PATH = os.path.join(os.path.dirname(__file__), 'odysseus.db')

def seed_tasks():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Insert some dummy tasks in different states
    tasks = [
        ("Write CPU monitor script", "Create a python script to log CPU temps using psutil.", "Backlog", "Supervisor"),
        ("Parse log file", "Extract error codes from server.log", "In Progress", "Coder"),
        ("Optimize sorting algorithm", "Make the data pipeline faster", "Review", "Reviewer"),
        ("Setup directory structure", "Create core and db folders", "Done", "Coder")
    ]
    
    cursor.executemany("INSERT INTO tasks (title, description, status, assigned_agent) VALUES (?, ?, ?, ?)", tasks)
    conn.commit()
    conn.close()
    print("Database seeded with dummy tasks!")

if __name__ == "__main__":
    seed_tasks()