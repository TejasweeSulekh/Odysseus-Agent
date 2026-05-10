from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import sys
import os

# Ensure absolute imports work
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.thick_tools import scrape_and_clean_web, export_to_pdf
from core.memory import query_memory, memorize_text

app = FastAPI(title="Odysseus MCP / Enterprise Tool Server")

# --- Security/Auth Simulation ---
API_KEY = "odysseus-fde-secret-key-123"

class ToolRequest(BaseModel):
    api_key: str
    args: dict

@app.post("/mcp/scrape")
async def mcp_scrape(req: ToolRequest):
    if req.api_key != API_KEY: raise HTTPException(status_code=401, detail="Unauthorized")
    url = req.args.get("url")
    if not url: raise HTTPException(status_code=400, detail="Missing URL")
    return {"result": scrape_and_clean_web(url)}

@app.post("/mcp/pdf")
async def mcp_pdf(req: ToolRequest):
    if req.api_key != API_KEY: raise HTTPException(status_code=401, detail="Unauthorized")
    filename = req.args.get("filename")
    content = req.args.get("content")
    if not filename or not content: raise HTTPException(status_code=400, detail="Missing args")
    return {"result": export_to_pdf(filename, content)}

@app.post("/mcp/query_memory")
async def mcp_memory(req: ToolRequest):
    if req.api_key != API_KEY: raise HTTPException(status_code=401, detail="Unauthorized")
    query = req.args.get("query")
    if not query: raise HTTPException(status_code=400, detail="Missing query")
    return {"result": query_memory(query)}

if __name__ == "__main__":
    import uvicorn
    print("🛡️ Starting Isolated Enterprise Tool Server on port 8000...")
    uvicorn.run(app, host="127.0.0.1", port=8000, log_level="warning")