import psutil
import sqlite3
import os

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'database', 'odysseus.db')

def get_system_metrics():
    """Fetches real-time CPU and RAM usage."""
    cpu_usage = psutil.cpu_percent(interval=0.1)
    ram = psutil.virtual_memory()
    disk = psutil.disk_usage('/')

    return {
        "cpu": cpu_usage,
        "ram_percent": ram.percent,
        "ram_used": round(ram.used / (1024 ** 3), 1),
        "ram_total": round(ram.total / (1024 ** 3), 1),
        "disk": disk.percent
    }

def get_llm_metrics():
    """Fetches the most recent LLM inference metrics from the database."""
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        # Grab the single most recent inference log
        cursor.execute("SELECT tokens_per_sec, eval_count, eval_duration_sec FROM session_metrics ORDER BY timestamp DESC LIMIT 1")
        row = cursor.fetchone()
        conn.close()
        
        if row:
            return {
                "tps": round(row[0], 1) if row[0] else 0.0,
                "tokens": row[1] if row[1] else 0,
                "duration": round(row[2], 1) if row[2] else 0.0
            }
    except Exception as e:
        pass # Fail silently so we don't crash the UI thread
        
    return {"tps": 0.0, "tokens": 0, "duration": 0.0}

if __name__ == "__main__":
    # Test it out
    metrics = get_system_metrics()
    llm = get_llm_metrics()
    print(f"CPU: {metrics['cpu']}% | RAM: {metrics['ram_used']}GB")
    print(f"LLM: {llm['tps']} Tokens/sec | Last burst: {llm['tokens']} tokens")