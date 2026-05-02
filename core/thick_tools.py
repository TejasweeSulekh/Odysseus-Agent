import os
import requests
from bs4 import BeautifulSoup
from weasyprint import HTML, CSS
import markdown

WORKSPACE_DIR = os.path.abspath(os.path.join(os.path.dirname(os.path.dirname(__file__)), 'workspace'))

def scrape_and_clean_web(url: str) -> str:
    """Fetches a webpage and extracts ONLY the readable text to save LLM context."""
    try:
        headers = {"User-Agent": "Odysseus-AgentOS/1.0"}
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        
        soup = BeautifulSoup(response.content, "html.parser")
        
        # Strip out non-content elements
        for element in soup(["script", "style", "nav", "footer", "header", "aside"]):
            element.extract()
            
        # Extract text and collapse whitespace
        text = soup.get_text(separator=' ', strip=True)
        
        # Hard cap at 4000 characters to prevent Context Window Poisoning
        if len(text) > 4000:
            return text[:4000] + "\n...[TRUNCATED FOR CONTEXT WINDOW]..."
        return text
    except Exception as e:
        return f"ERROR scraping web: {str(e)}"

def export_to_pdf(filename: str, content: str) -> str:
    """Converts Markdown content to a styled PDF using a hardcoded template."""
    safe_path = os.path.join(WORKSPACE_DIR, os.path.basename(filename))
    
    # Hardcoded Enterprise CSS Template
    css = CSS(string='''
        @page { margin: 2cm; size: A4; }
        body { font-family: "Helvetica Neue", Helvetica, Arial, sans-serif; color: #333; line-height: 1.6; }
        h1, h2, h3 { color: #0f766e; border-bottom: 1px solid #e2e8f0; padding-bottom: 5px; }
        code { background: #f1f5f9; padding: 2px 4px; border-radius: 4px; font-family: monospace; }
        pre { background: #1e293b; color: #f8fafc; padding: 10px; border-radius: 6px; overflow-x: auto; }
        pre code { background: transparent; color: inherit; }
    ''')
    
    try:
        # Convert Markdown to HTML, then to PDF
        html_body = markdown.markdown(content, extensions=['fenced_code', 'tables'])
        full_html = f"<html><body>{html_body}</body></html>"
        
        HTML(string=full_html).write_pdf(safe_path, stylesheets=[css])
        return f"SUCCESS: PDF exported successfully to '{filename}'."
    except Exception as e:
        return f"ERROR exporting PDF: {str(e)}"