import asyncio
import httpx
import json

# Default Ollama port is 11434. If using llama.cpp directly, it is usually 8080.
# We use the OpenAI compatible /v1/chat/completions endpoint.
LOCAL_LLM_URL = "http://localhost:11434/v1/chat/completions" 
MODEL_NAME = "gemma4" # Change this to exactly what your local model is named

async def ping_model(prompt: str, system_prompt: str = "You are a helpful assistant."):
    """Sends an asynchronous request to the local LLM."""
    
    headers = {"Content-Type": "application/json"}
    payload = {
        "model": MODEL_NAME,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": prompt}
        ],
        "temperature": 0.1, # Keep it low for deterministic agent actions
        "max_tokens": 150
    }

    print(f"Sending prompt to {MODEL_NAME}...")
    
    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(LOCAL_LLM_URL, headers=headers, json=payload, timeout=60.0)
            response.raise_for_status()
            
            data = response.json()
            reply = data['choices'][0]['message']['content']
            print("\n--- Model Response ---")
            print(reply)
            print("----------------------\n")
            return reply
            
        except httpx.ConnectError:
            print(f"Error: Could not connect to the model at {LOCAL_LLM_URL}.")
            print("Make sure your local inference server (Ollama/llama.cpp) is running.")
        except Exception as e:
            print(f"An unexpected error occurred: {e}")

if __name__ == "__main__":
    # Test the connection
    test_prompt = "Respond with a single sentence: Are your systems online and ready for deployment?"
    asyncio.run(ping_model(test_prompt, "You are the Odysseus Agent OS."))