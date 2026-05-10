from textual.app import App, ComposeResult
from textual.screen import Screen
from textual.containers import Horizontal, VerticalScroll, Vertical, Container
from textual.widgets import Header, Footer, Static, Label, Markdown, Input, RichLog, Button
from textual.message import Message
from textual import work
from textual.reactive import reactive
from rich.markdown import Markdown as RichMarkdown
import sqlite3
import os
import sys

# Ensure Python can find our core modules
sys.path.append(os.path.dirname(os.path.dirname(__file__)))
from core.telemetry import get_system_metrics
from core.supervisor import orchestrate

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'database', 'odysseus.db')

# --- ASSETS ---
ODYSSEUS_ASCII = """
[#5eead4] ██████╗ ██████╗ ██╗   ██╗███████╗███████╗███████╗██╗   ██╗███████╗[/]
[#2dd4bf]██╔═══██╗██╔══██╗╚██╗ ██╔╝██╔════╝██╔════╝██╔════╝██║   ██║██╔════╝[/]
[#14b8a6]██║   ██║██║  ██║ ╚████╔╝ ███████╗███████╗█████╗  ██║   ██║███████╗[/]
[#0d9488]██║   ██║██║  ██║  ╚██╔╝  ╚════██║╚════██║██╔══╝  ██║   ██║╚════██║[/]
[#0f766e]╚██████╔╝██████╔╝   ██║   ███████║███████║███████╗╚██████╔╝███████║[/]
[#115e59] ╚═════╝ ╚═════╝    ╚═╝   ╚══════╝╚══════╝╚══════╝ ╚═════╝ ╚══════╝[/]
"""

# --- WIDGETS ---

class TaskCard(Static):
    class Selected(Message):
        def __init__(self, task_id: int):
            self.task_id = task_id
            super().__init__()

    def __init__(self, task_id: int, title: str, agent: str):
        super().__init__()
        self.task_id = task_id
        self.title = title
        self.agent = agent

    def compose(self) -> ComposeResult:
        yield Label(f"ID-{self.task_id}: {self.title}", classes="card-title")
        yield Label(f"↳ {self.agent}", classes="card-agent")

    def on_click(self) -> None:
        self.post_message(self.Selected(self.task_id))

class KanbanColumn(VerticalScroll):
    def __init__(self, status_name: str):
        super().__init__()
        self.status_name = status_name
        self.add_class(f"column-{status_name.replace(' ', '').lower()}")

    def compose(self) -> ComposeResult:
        yield Label(f"--- {self.status_name.upper()} ---", classes="column-header")

class BlinkingCursor(Label):
    cursor_state = reactive(True)

    def on_mount(self) -> None:
        self.set_interval(0.5, self.toggle_cursor)

    def toggle_cursor(self) -> None:
        self.cursor_state = not self.cursor_state
        if self.cursor_state:
            self.update("[bold #2dd4bf]COMPUTING ▊[/bold #2dd4bf]")
        else:
            self.update("[bold #0d9488]COMPUTING ▌[/bold #0d9488]")

# --- SCREENS ---

class ChatScreen(Screen):
    is_agentic_mode = reactive(False)

    def compose(self) -> ComposeResult:
        yield Header()
        yield RichLog(id="chat-log", wrap=True, highlight=True, markup=True)
        with Horizontal(id="input-container"):
            yield Input(placeholder="COMMAND / PROMPT", id="chat-input")
            yield Button("CHAT MODE", id="mode-toggle")
        yield Footer()

    def on_mount(self) -> None:
        log = self.query_one(RichLog)
        log.write(ODYSSEUS_ASCII)
        log.write("\n[bold #2dd4bf]Odysseus[/bold #2dd4bf]")
        log.write("[dim]System initialized. Ready for input.[/dim]")
        log.write("[dim]─[/dim]" * 40)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "mode-toggle":
            self.is_agentic_mode = not self.is_agentic_mode
            if self.is_agentic_mode:
                event.button.label = "AGENTIC"
                event.button.add_class("agentic-active")
            else:
                event.button.label = "CHAT MODE"
                event.button.remove_class("agentic-active")

    @work
    async def process_command(self, user_text: str) -> None:
        log = self.query_one(RichLog)
        chat_input = self.query_one(Input)
        chat_input.disabled = True
        
        cursor = BlinkingCursor()
        self.mount(cursor)
        
        command_payload = user_text
        if self.is_agentic_mode and not any(k in user_text.upper() for k in ["BUILD", "WRITE", "CREATE"]):
             command_payload = f"BUILD THIS: {user_text}"

        reply = await orchestrate(command_payload)
        cursor.remove()
        
        if "[SYSTEM] Agentic Mode Triggered" in reply:
            self.app.switch_screen("kanban")
        else:
            log.write("\n[bold #2dd4bf]Odysseus[/bold #2dd4bf]")
            log.write(RichMarkdown(reply))
            log.write("[dim]─[/dim]" * 40)
            
        chat_input.disabled = False
        chat_input.focus()

    async def on_input_submitted(self, event: Input.Submitted) -> None:
        user_text = event.value
        if not user_text.strip(): return
        event.input.value = ""
        log = self.query_one(RichLog)

        log.write(f"\n[bold #94a3b8]User[/bold #94a3b8]")
        log.write(f"{user_text}")
        
        self.process_command(user_text)

class KanbanScreen(Screen):
    def compose(self) -> ComposeResult:
        yield Header()
        with Horizontal(id="board-container"):
            with Horizontal(id="main-view"):
                yield KanbanColumn("Backlog")
                yield KanbanColumn("In Progress")
                yield KanbanColumn("Review")
                yield KanbanColumn("Done")
            # FIXED: Changed back to VerticalScroll so the panel can scroll vertically
            with VerticalScroll(id="side-panel"):
                yield Label("SYSTEM TELEMETRY", classes="panel-header")
                yield Label("CPU --% | RAM --GB", id="telemetry-data")
                # --- NEW: LLM Telemetry UI ---
                yield Label("LLM PERFORMANCE", classes="panel-header")
                yield Label("-- T/s | -- Tokens", id="llm-telemetry-data")
                
                yield Label("LOGS", classes="panel-header")
                yield Markdown("Select a task to view execution details.", id="detail-content")
        yield Footer()

    def on_mount(self) -> None:
        self.set_interval(2.0, self.update_telemetry)
        self.set_interval(1.0, self.update_board)

    def update_board(self) -> None:
        for card in self.query(TaskCard): card.remove()
        conn = sqlite3.connect(DB_PATH); cursor = conn.cursor()
        cursor.execute("SELECT id, title, status, assigned_agent FROM tasks")
        tasks = cursor.fetchall(); conn.close()

        columns = {
            "Backlog": self.query(".column-backlog").first(),
            "In Progress": self.query(".column-inprogress").first(),
            "Review": self.query(".column-review").first(),
            "Done": self.query(".column-done").first(),
        }

        all_done = True; has_tasks = False
        for tid, title, status, agent in tasks:
            has_tasks = True
            if status != "Done": all_done = False
            if status in columns: columns[status].mount(TaskCard(tid, title, agent))

        if has_tasks and all_done and not getattr(self, "is_synthesizing", False):
            self.is_synthesizing = True
            self.trigger_synthesis()

    @work
    async def trigger_synthesis(self) -> None:
        self.app.switch_screen("chat")
        reply = await orchestrate("[SYSTEM] TASK_BATCH_COMPLETE")
        log = self.app.get_screen("chat").query_one(RichLog)
        
        log.write("\n[bold #2dd4bf]Odysseus[/bold #2dd4bf] [dim]• Synthesis Complete[/dim]")
        log.write(RichMarkdown(reply))
        log.write("[dim]─[/dim]" * 40)
        
        self.is_synthesizing = False

    def update_telemetry(self) -> None:
        # Import our new function here as well
        from core.telemetry import get_llm_metrics
        
        # Update Hardware
        m = get_system_metrics()
        self.query_one("#telemetry-data", Label).update(f"CPU: {m['cpu']}% | RAM: {m['ram_used']}GB / {m['ram_total']}GB")
        
        # Update LLM Performance
        l = get_llm_metrics()
        self.query_one("#llm-telemetry-data", Label).update(f"Speed: {l['tps']} T/s | Last burst: {l['tokens']} tok ({l['duration']}s)")

    def on_task_card_selected(self, message: TaskCard.Selected) -> None:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("SELECT title, description, status, assigned_agent FROM tasks WHERE id = ?", (message.task_id,))
        task = cursor.fetchone()
        cursor.execute("SELECT agent_name, thought FROM execution_logs WHERE task_id = ? ORDER BY timestamp ASC", (message.task_id,))
        logs = cursor.fetchall()
        conn.close()

        if task:
            title, description, status, agent = task
            log_text = ""
            if logs:
                for log_agent, thought in logs:
                    clean_thought = thought.replace("```json", "").replace("```", "").strip()
                    log_text += f"**{log_agent} Execution:**\n```text\n{clean_thought}\n```\n\n"
            else:
                log_text = "*(Awaiting agent execution...)*"

            markdown_text = f"# {title}\n**Status:** {status} | **Agent:** {agent}\n***\n## Description\n{description}\n***\n## Logs\n{log_text}"
            self.query_one("#detail-content", Markdown).update(markdown_text)


# --- THE HERMES SKIN (CSS) ---

class OdysseusDashboard(App):
    CSS = """
    /* DARK MODE - EARL GREY & TURQUOISE */
    Screen { background: #1a1b1e; color: #e2e8f0; }
    
    Header { background: #1a1b1e; color: #2dd4bf; border-bottom: hkey #2dd4bf; }
    Footer { background: #1a1b1e; color: #94a3b8; }

    #chat-log {
        height: 1fr;
        border: none;
        background: #1a1b1e;
        padding: 1 6; 
    }
    
    #input-container {
        height: auto;
        dock: bottom;
        padding: 1 2;
        background: #1a1b1e;
        border-top: vkey #334155;
    }
    Input {
        width: 1fr;
        background: #1a1b1e;
        border: solid #334155;
        color: #f8fafc;
    }
    Input:focus { border: double #2dd4bf; }
    Input:disabled { opacity: 0.5; }

    Button {
        background: #1a1b1e;
        color: #94a3b8;
        border: solid #334155;
        margin-left: 1;
        text-style: bold;
    }
    Button.agentic-active { color: #2dd4bf; border: double #2dd4bf; }

    /* KANBAN UI */
    TaskCard {
        background: #25262b;
        border-left: solid #2dd4bf;
        margin-bottom: 1;
        padding: 1;
    }
    .card-title { text-style: bold; color: #f8fafc; }
    .card-agent { color: #2dd4bf; text-style: dim; }
    
    KanbanColumn { background: #1a1b1e; border: none; margin: 0 1; }
    .column-header { color: #94a3b8; text-style: bold; padding: 1; border-bottom: solid #334155; }
    
    #side-panel { background: #1a1b1e; border-left: vkey #334155; width: 30%; }
    .panel-header { color: #2dd4bf; text-style: bold; margin-top: 1; padding: 0 1; }
    #detail-content { overflow-x: auto; }

    /* DARK MODE MARKDOWN */
    Markdown { color: #e2e8f0; }
    MarkdownH1, MarkdownH2, MarkdownH3 { color: #2dd4bf; text-style: bold; margin-top: 1; }
    MarkdownBullet { color: #2dd4bf; }
    MarkdownFence { border: solid #334155; background: #25262b; margin: 1 0; overflow-x: auto; }
    MarkdownCode { color: #2dd4bf; background: #25262b; }

    /* ========================================= */
    /* LIGHT MODE FIXES - CLAUDE PAPER & TEAL    */
    /* ========================================= */
    
    /* Base Backgrounds (Claude's Warm Paper #F5F4F0) */
    App.-light-mode Screen { background: #F5F4F0; color: #2D3142; }
    App.-light-mode Header { background: #F5F4F0; color: #0F766E; border-bottom: hkey #0F766E; }
    App.-light-mode Footer { background: #F5F4F0; color: #646E83; }
    App.-light-mode #chat-log { background: #F5F4F0; }
    App.-light-mode RichLog { background: #F5F4F0; color: #2D3142; }
    App.-light-mode KanbanColumn { background: #F5F4F0; }
    App.-light-mode #side-panel { background: #F5F4F0; border-left: vkey #E5E4E0; }
    App.-light-mode #input-container { background: #F5F4F0; border-top: vkey #E5E4E0; }
    
    /* Elevated Backgrounds (Pure White for Contrast) */
    App.-light-mode Input { background: #FFFFFF; border: solid #E5E4E0; color: #2D3142; }
    App.-light-mode Input:focus { border: double #0F766E; }
    App.-light-mode Button { background: #FFFFFF; color: #2D3142; border: solid #E5E4E0; }
    App.-light-mode Button.agentic-active { color: #0F766E; border: double #0F766E; background: #E6F4F1; }
    App.-light-mode TaskCard { background: #FFFFFF; border: solid #E5E4E0; border-left: solid #0F766E; }
    
    /* Text & Headers */
    App.-light-mode .panel-header { color: #0F766E; }
    App.-light-mode .column-header { color: #646E83; border-bottom: solid #E5E4E0; }
    App.-light-mode .card-title { color: #2D3142; }
    App.-light-mode .card-agent { color: #0F766E; }
    
    /* Light Mode Markdown */
    App.-light-mode Markdown { color: #2D3142; }
    App.-light-mode MarkdownH1, App.-light-mode MarkdownH2, App.-light-mode MarkdownH3 { color: #0F766E; }
    App.-light-mode MarkdownBullet { color: #0F766E; }
    App.-light-mode MarkdownFence { border: solid #E5E4E0; background: #FFFFFF; color: #2D3142; overflow-x: auto; }
    App.-light-mode MarkdownCode { color: #0F766E; background: #FFFFFF; }
    """
    
    SCREENS = {
        "chat": ChatScreen, 
        "kanban": KanbanScreen
    }
    BINDINGS = [("d", "toggle_dark", "Toggle light/dark"), ("q", "quit", "Quit")]

    def on_mount(self) -> None:
        self.push_screen("chat")

if __name__ == "__main__":
    app = OdysseusDashboard()
    app.run()