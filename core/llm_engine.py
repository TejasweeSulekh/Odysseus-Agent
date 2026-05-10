import asyncio
import httpx
import json
import sqlite3
import os
import time
from dotenv import load_dotenv
from google import genai
from google.genai import types

# Load environment variables
load_dotenv(os.path.join(os.path.dirname(os.path.dirname(__file__)), '.env'))

MODE = os.getenv("ODYSSEUS_MODE", "local").lower()
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")

LOCAL_LLM_URL = "http://localhost:11434/api/chat"
MODEL_NAME = "gemma4:e2b"
DB_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'database', 'odysseus.db')

def log_metrics(endpoint: str, eval_count: int, eval_duration_sec: float):
    """Calculates and logs tokens/sec to the SQLite database."""
    if not eval_count or not eval_duration_sec: return
    tokens_per_sec = eval_count / eval_duration_sec if eval_duration_sec > 0 else 0
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO session_metrics (endpoint, eval_count, eval_duration_sec, tokens_per_sec) VALUES (?, ?, ?, ?)",
            (endpoint, eval_count, round(eval_duration_sec, 2), round(tokens_per_sec, 2))
        )
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"[Telemetry Error] Could not log metrics: {e}")

async def ping_ollama(prompt: str, system_prompt: str):
    """The original Edge-Optimized local inference path."""
    headers = {"Content-Type": "application/json"}
    payload = {
        "model": MODEL_NAME,
        "messages": [{"role": "system", "content": system_prompt}, {"role": "user", "content": prompt}],
        "stream": False,
        "options": {"temperature": 0.1, "num_predict": 2048, "num_ctx": 8192}
    }
    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(LOCAL_LLM_URL, headers=headers, json=payload, timeout=120.0)
            response.raise_for_status()
            data = response.json()
            
            eval_count = data.get('eval_count', 0)
            eval_duration_sec = data.get('eval_duration', 0) / 1e9
            log_metrics(MODEL_NAME, eval_count, eval_duration_sec)
            
            return data.get('message', {}).get('content', '')
        except Exception as e:
            print(f"[Edge Engine Error] {e}")
            return ""

async def ping_gemini(prompt: str, system_prompt: str):
    """The Cloud-Tier frontier inference path."""
    if not GEMINI_API_KEY:
        return "Error: ODYSSEUS_MODE is 'cloud' but GEMINI_API_KEY is missing from .env"
        
    try:
        client = genai.Client(api_key=GEMINI_API_KEY)
        start_time = time.time()
        
        # Use the official async client for GenAI
        response = await client.aio.models.generate_content(
            model='gemini-2.5-flash',
            contents=prompt,
            config=types.GenerateContentConfig(
                system_instruction=system_prompt,
                temperature=0.1
            )
        )
        
        duration = time.time() - start_time
        # Extract token usage from Gemini's metadata
        eval_count = response.usage_metadata.candidates_token_count if response.usage_metadata else 0
        log_metrics("gemini-2.5-flash", eval_count, duration)
        
        return response.text
    except Exception as e:
        print(f"[Cloud Engine Error] {e}")
        return ""

async def ping_model(prompt: str, system_prompt: str = "You are a helpful assistant."):
    """Master Router: Decides which brain to use based on the environment."""
    if MODE == "cloud":
        return await ping_gemini(prompt, system_prompt)
    else:
        return await ping_ollama(prompt, system_prompt)