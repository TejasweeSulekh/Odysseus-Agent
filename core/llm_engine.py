import asyncio
import httpx
import json
import sqlite3
import os

LOCAL_LLM_URL = "http://localhost:11434/api/chat"
MODEL_NAME = "gemma4:e2b"
DB_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'database', 'odysseus.db')

def log_metrics(eval_count: int, eval_duration_ns: int):
    """Calculates and logs tokens/sec to the SQLite database."""
    if not eval_count or not eval_duration_ns:
        return
        
    eval_duration_sec = eval_duration_ns / 1e9
    tokens_per_sec = eval_count / eval_duration_sec if eval_duration_sec > 0 else 0
    
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO session_metrics (endpoint, eval_count, eval_duration_sec, tokens_per_sec) VALUES (?, ?, ?, ?)",
            (LOCAL_LLM_URL, eval_count, round(eval_duration_sec, 2), round(tokens_per_sec, 2))
        )
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"[Telemetry Error] Could not log metrics: {e}")

async def ping_model(prompt: str, system_prompt: str = "You are a helpful assistant."):
    """Sends an asynchronous request to the local LLM and tracks telemetry."""
    headers = {"Content-Type": "application/json"}
    payload = {
        "model": MODEL_NAME,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": prompt}
        ],
        "stream": False,
        "options": {"temperature": 0.1, "num_predict": 2048, "num_ctx": 8192}
    }

    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(LOCAL_LLM_URL, headers=headers, json=payload, timeout=120.0)
            response.raise_for_status()
            data = response.json()
            
            # --- NEW: Extract Telemetry ---
            eval_count = data.get('eval_count', 0)
            eval_duration = data.get('eval_duration', 0)
            log_metrics(eval_count, eval_duration)
            
            reply = data.get('message', {}).get('content', '')
            return reply
            
        except httpx.ConnectError:
            print(f"Error: Could not connect to {LOCAL_LLM_URL}.")
        except Exception as e:
            print(f"An unexpected error occurred: {e}")
            return ""