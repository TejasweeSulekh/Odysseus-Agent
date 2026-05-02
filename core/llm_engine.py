import asyncio
import httpx
import json

# Switch to Ollama's native API instead of the OpenAI compat layer
LOCAL_LLM_URL = "http://localhost:11434/api/chat" 
MODEL_NAME = "gemma4:e2b"

async def ping_model(prompt: str, system_prompt: str = "You are a helpful assistant."):
    """Sends an asynchronous request to the local LLM."""
    
    headers = {"Content-Type": "application/json"}
    
    # Ollama native payload structure
    payload = {
        "model": MODEL_NAME,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": prompt}
        ],
        "stream": False,
        "options": {
            "temperature": 0.1,
            "num_predict": 2048, # Increased from 500 to let it finish its thoughts
            "num_ctx": 8192      # Expanded context window so history doesn't choke it
        }
    }

    print(f"Sending prompt to {MODEL_NAME} via Native API...")
    
    async with httpx.AsyncClient() as client:
        try:
            # Increased timeout just in case it needs to load weights from disk
            response = await client.post(LOCAL_LLM_URL, headers=headers, json=payload, timeout=120.0)
            response.raise_for_status()
            
            data = response.json()
            
            # The native API wraps the response differently
            reply = data.get('message', {}).get('content', '')
            
            print("\n--- Model Response ---")
            print(reply)
            print("----------------------\n")
            return reply
            
        except httpx.ConnectError:
            print(f"Error: Could not connect to the model at {LOCAL_LLM_URL}.")
            print("Make sure your local inference server (Ollama) is running.")
        except httpx.HTTPStatusError as e:
            print(f"HTTP Error: {e.response.status_code} - {e.response.text}")
        except Exception as e:
            print(f"An unexpected error occurred: {e}")

if __name__ == "__main__":
    # Test the connection directly
    test_prompt = "Respond with a single sentence: Are your systems online and ready for deployment?"
    asyncio.run(ping_model(test_prompt, "You are the Odysseus Agent OS."))