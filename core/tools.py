import os
import subprocess
import json
import warnings
from core.memory import query_memory
from core.thick_tools import scrape_and_clean_web, export_to_pdf

# Suppress the noisy renaming warning from the duckduckgo backend
warnings.filterwarnings("ignore", category=RuntimeWarning, module="duckduckgo_search")

from ddgs import DDGS

# Ensure the workspace exists and lock tools to this directory
WORKSPACE_DIR = os.path.abspath(os.path.join(os.path.dirname(os.path.dirname(__file__)), 'workspace'))
os.makedirs(WORKSPACE_DIR, exist_ok=True)

def write_file(filename: str, content: str) -> str:
    """Writes content to a file inside the workspace."""
    safe_path = os.path.join(WORKSPACE_DIR, os.path.basename(filename))
    try:
        with open(safe_path, 'w', encoding='utf-8') as f:
            f.write(content)
        return f"SUCCESS: File '{filename}' written successfully."
    except Exception as e:
        return f"ERROR writing file: {str(e)}"

def read_file(filename: str) -> str:
    """Reads the contents of a file from the workspace."""
    safe_path = os.path.join(WORKSPACE_DIR, os.path.basename(filename))
    if not os.path.exists(safe_path):
        return f"ERROR: File '{filename}' does not exist."
    try:
        with open(safe_path, 'r', encoding='utf-8') as f:
            return f.read()
    except Exception as e:
        return f"ERROR reading file: {str(e)}"

def execute_bash(command: str) -> str:
    """Executes a bash command in the workspace directory."""
    try:
        # Timeout added to prevent infinite loops from the LLM
        result = subprocess.run(
            command,
            shell=True,
            cwd=WORKSPACE_DIR,
            capture_output=True,
            text=True,
            timeout=15 
        )
        output = ""
        if result.stdout:
            output += f"STDOUT:\n{result.stdout}\n"
        if result.stderr:
            output += f"STDERR:\n{result.stderr}\n"
        
        if result.returncode == 0:
            return f"SUCCESS:\n{output}" if output else "SUCCESS: Command ran with no output."
        else:
            return f"FAILED (Exit code {result.returncode}):\n{output}"
            
    except subprocess.TimeoutExpired:
        return "ERROR: Command timed out after 15 seconds."
    except Exception as e:
        return f"ERROR executing command: {str(e)}"

def search_web(query: str) -> str:
    """Searches the web for up-to-date information and documentation."""
    if DDGS is None:
        return "ERROR: ddgs library not installed. Run: python -m pip install ddgs"
    
    try:
        # Use backend="lite" to bypass DuckDuckGo's aggressive anti-bot JavaScript challenges
        results = DDGS().text(query, max_results=3, backend="lite")
        
        # If it returns a generator, convert it to a list
        if not isinstance(results, list):
            results = list(results)
            
        if not results:
            return f"No results found for query: {query}. The search engine might be temporarily blocking the request."
            
        formatted_results = "--- WEB SEARCH RESULTS ---\n"
        for i, r in enumerate(results):
            # Safe extraction just in case the new ddgs package changes its dictionary keys
            title = r.get('title', 'No Title')
            body = r.get('body', r.get('snippet', 'No snippet'))
            href = r.get('href', r.get('link', 'No link'))
            formatted_results += f"{i+1}. {title}\nSnippet: {body}\nURL: {href}\n\n"
        
        return formatted_results
        
    except Exception as e:
        return f"ERROR searching the web: {str(e)}"

def process_tool_call(tool_name: str, tool_args: dict) -> str:
    """Router function to execute the requested tool."""
    if tool_name == "write_file":
        return write_file(tool_args.get("filename", ""), tool_args.get("content", ""))
    elif tool_name == "read_file":
        return read_file(tool_args.get("filename", ""))
    elif tool_name == "execute_bash":
        return execute_bash(tool_args.get("command", ""))
    elif tool_name == "list_directory":
        return list_directory(tool_args.get("path", "."))
    elif tool_name == "search_web":
        return search_web(tool_args.get("query", ""))
    # --- NEW THICK TOOLS ---
    elif tool_name == "scrape_and_clean_web":
        return scrape_and_clean_web(tool_args.get("url", ""))
    elif tool_name == "export_to_pdf":
        return export_to_pdf(tool_args.get("filename", ""), tool_args.get("content", ""))
    elif tool_name == "query_memory":
        return query_memory(tool_args.get("query", ""))
    else:
        return f"ERROR: Unknown tool '{tool_name}'."
    
def list_directory(path: str = ".") -> str:
    """Returns a tree-like map of the workspace directory."""
    # Ensure the path is strictly within the workspace to prevent directory traversal attacks
    target_dir = os.path.abspath(os.path.join(WORKSPACE_DIR, path))
    if not target_dir.startswith(WORKSPACE_DIR):
        return "ERROR: Access denied. You can only list directories within the workspace."
    
    if not os.path.exists(target_dir):
        return f"ERROR: Directory '{path}' does not exist."
        
    try:
        # Use tree if available in the WSL environment, otherwise fallback to ls -R
        result = subprocess.run(["tree", target_dir], capture_output=True, text=True)
        if result.returncode == 0:
            return result.stdout
            
        # Fallback if `tree` isn't installed
        result = subprocess.run(["ls", "-R", target_dir], capture_output=True, text=True)
        return result.stdout if result.returncode == 0 else "ERROR: Could not list directory."
        
    except Exception as e:
        return f"ERROR listing directory: {str(e)}"