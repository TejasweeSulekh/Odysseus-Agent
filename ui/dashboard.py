from textual.app import App, ComposeResult
from textual.screen import Screen
from textual.containers import Horizontal, VerticalScroll, Vertical
from textual.widgets import Header, Footer, Static, Label, Markdown, Input, RichLog, Button
from textual.message import Message
from textual import work
from textual.reactive import reactive
from rich.markdown import Markdown as RichMarkdown # NEW: Imports the Rich Markdown parser
import sqlite3
import os
import sys

# Ensure Python can find our core modules
sys.path.append(os.path.dirname(os.path.dirname(__file__)))
from core.telemetry import get_system_metrics
from core.supervisor import orchestrate

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'database', 'odysseus.db')

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
        yield Label(f"[{self.task_id}] {self.title}", classes="card-title")
        yield Label(f"Agent: {self.agent}", classes="card-agent")

    def on_click(self) -> None:
        self.post_message(self.Selected(self.task_id))

class KanbanColumn(VerticalScroll):
    def __init__(self, status_name: str):
        super().__init__()
        self.status_name = status_name
        self.add_class(f"column-{status_name.replace(' ', '').lower()}")

    def compose(self) -> ComposeResult:
        yield Label(f"--- {self.status_name.upper()} ---", classes="column-header")

class TaskDetailPanel(VerticalScroll):
    def compose(self) -> ComposeResult:
        yield Label("Odysseus Telemetry", id="telemetry-header")
        yield Label("CPU: --% | RAM: --GB", id="telemetry-data")
        yield Label("Task Details", id="detail-header")
        yield Markdown("*(Awaiting telemetry data...)*", id="detail-content")

class BlinkingCursor(Label):
    """A lightweight, CPU-safe thinking indicator."""
    cursor_visible = reactive(True)

    def on_mount(self) -> None:
        self.set_interval(0.5, self.toggle_cursor)

    def toggle_cursor(self) -> None:
        self.cursor_visible = not self.cursor_visible
        # Sleek, brutalist loading state
        self.update(f"[bold #ff00ff]Odysseus.sys.compute(){' █' if self.cursor_visible else '  '}[/bold #ff00ff]")

# --- SCREENS ---

class ChatScreen(Screen):
    """The default conversational interface."""
    
    is_agentic_mode = reactive(False)

    def compose(self) -> ComposeResult:
        yield Header()
        yield RichLog(id="chat-log", wrap=True, highlight=True, markup=True)
        
        with Horizontal(id="input-container"):
            yield Input(placeholder="Talk to Odysseus...", id="chat-input")
            yield Button("MODE: CHAT", id="mode-toggle", variant="primary")
            
        yield Footer()

    def on_mount(self) -> None:
        log = self.query_one(RichLog)
        log.write("[bold #00ff00]=== ODYSSEUS OS ONLINE ===[/bold #00ff00]")
        log.write("[dim]System initialized. Ready for input.[/dim]\n")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handles the Mode Toggle."""
        if event.button.id == "mode-toggle":
            self.is_agentic_mode = not self.is_agentic_mode
            if self.is_agentic_mode:
                event.button.label = "MODE: AGENTIC"
                event.button.variant = "warning"
                self.query_one(Input).placeholder = "Issue an engineering command..."
            else:
                event.button.label = "MODE: CHAT"
                event.button.variant = "primary"
                self.query_one(Input).placeholder = "Talk to Odysseus..."

    @work
    async def process_command(self, user_text: str) -> None:
        """Handles the async LLM call and UI updates without freezing the screen."""
        log = self.query_one(RichLog)
        chat_input = self.query_one(Input)
        
        # 1. Disable the input box so its cursor stops blinking
        chat_input.disabled = True
        
        # 2. Mount the pulsing cursor
        cursor = BlinkingCursor()
        self.mount(cursor)
        
        # Force the mode onto the user's text if Agentic is active
        command_payload = user_text
        if self.is_agentic_mode and not user_text.upper().startswith("BUILD") and not user_text.upper().startswith("WRITE"):
             command_payload = f"BUILD THIS: {user_text}"

        reply = await orchestrate(command_payload)
        
        # 3. Unmount the cursor once finished
        cursor.remove()
        
        # 4. Route logic & Render Markdown cleanly
        if "[SYSTEM] Agentic Mode Triggered" in reply:
            self.app.switch_screen("kanban")
        else:
            log.write(RichMarkdown(reply)) # Render as native Markdown!
            log.write("\n") # Add spacing after the output
            
        # 5. Re-enable the input box and refocus it
        chat_input.disabled = False
        chat_input.focus()

    async def on_input_submitted(self, event: Input.Submitted) -> None:
        user_text = event.value
        if not user_text.strip(): return
        
        event.input.value = ""
        log = self.query_one(RichLog)
        log.write(f"[bold #58a6ff]YOU:[/bold #58a6ff] {user_text}")
        
        # Fire the background worker
        self.process_command(user_text)

class KanbanScreen(Screen):
    """The Agentic Dashboard mode."""
    def compose(self) -> ComposeResult:
        yield Header()
        with Horizontal(id="board-container"):
            with Horizontal(id="main-view"):
                yield KanbanColumn("Backlog")
                yield KanbanColumn("In Progress")
                yield KanbanColumn("Review")
                yield KanbanColumn("Done")
            yield TaskDetailPanel(id="side-panel")
        yield Footer()

    def on_mount(self) -> None:
        self.load_tasks()
        self.set_interval(2.0, self.update_telemetry)
        self.set_interval(1.0, self.update_board)

    def update_board(self) -> None:
        for card in self.query(TaskCard):
            card.remove()
        self.load_tasks()

    def load_tasks(self) -> None:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("SELECT id, title, status, assigned_agent FROM tasks")
        tasks = cursor.fetchall()
        conn.close()

        columns = {
            "Backlog": self.query("KanbanColumn.column-backlog").first(),
            "In Progress": self.query("KanbanColumn.column-inprogress").first(),
            "Review": self.query("KanbanColumn.column-review").first(),
            "Done": self.query("KanbanColumn.column-done").first(),
        }

        all_done = True
        has_tasks = False

        for task_id, title, status, agent in tasks:
            has_tasks = True
            if status != "Done":
                all_done = False
            if status in columns:
                columns[status].mount(TaskCard(task_id, title, agent))

        if has_tasks and all_done:
            if not hasattr(self, "is_synthesizing") or not self.is_synthesizing:
                self.is_synthesizing = True
                self.trigger_synthesis()

    @work
    async def trigger_synthesis(self) -> None:
        """Pops the screen back to Chat and asks the Supervisor for a summary."""
        self.app.switch_screen("chat")
        chat_screen = self.app.get_screen("chat")
        chat_log = chat_screen.query_one(RichLog)
        
        chat_log.write("\n[dim italic]Tasks complete. Odysseus is synthesizing the results...[/dim italic]")
        
        reply = await orchestrate("[SYSTEM] TASK_BATCH_COMPLETE")
        
        # Render the final synthesized text as pure Markdown
        chat_log.write(RichMarkdown(reply))
        chat_log.write("\n")
        self.is_synthesizing = False

    def update_telemetry(self) -> None:
        metrics = get_system_metrics()
        telemetry_label = self.query_one("#telemetry-data", Label)
        telemetry_label.update(
            f"CPU: {metrics['cpu']}%\n"
            f"RAM: {metrics['ram_used']} / {metrics['ram_total']} GB ({metrics['ram_percent']}%)\n"
            f"Disk: {metrics['disk']}%"
        )

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
                    log_text += f"**[{log_agent}]**\n{thought}\n\n---\n"
            else:
                log_text = "*(Awaiting agent execution...)*"

            markdown_text = f"# {title}\n**Status:** {status} | **Agent:** {agent}\n***\n### Description\n{description}\n***\n### Execution Logs\n{log_text}"
            self.query_one("#detail-content", Markdown).update(markdown_text)


# --- MAIN APP ---

class OdysseusDashboard(App):
    CSS = """
    Screen {
        layout: vertical;
        background: #0d1117; 
    }
    #chat-log {
        height: 1fr;
        border: panel #00ff00; 
        margin: 1;
        padding: 1;
        background: #161b22;
    }
    
    #input-container {
        layout: horizontal;
        height: auto;
        dock: bottom;
        margin: 0 1 1 1;
    }
    #chat-input {
        width: 1fr;
        border: tall #00ff00;
    }
    #chat-input:disabled {
        opacity: 0.5; /* Dims the input bar while thinking */
    }
    #mode-toggle {
        width: auto;
        margin-left: 1;
        min-width: 18;
    }
    
    BlinkingCursor {
        dock: bottom;
        margin-left: 2;
        margin-bottom: 4; 
    }

    #board-container {
        height: 1fr;
        layout: horizontal;
    }
    #main-view {
        width: 70%;
        layout: horizontal;
    }
    #side-panel {
        width: 30%;
        border-left: vkey #00ff00;
        padding: 1 2;
        background: #161b22;
    }
    #detail-header {
        text-style: bold;
        color: #ff00ff; 
        padding-bottom: 1;
        border-bottom: solid #00ff00;
        width: 100%;
    }
    KanbanColumn {
        width: 1fr;
        height: 1fr;
        border: solid #30363d;
        margin: 1 1;
        padding: 1;
    }
    .column-header {
        text-align: center;
        text-style: bold;
        color: #58a6ff; 
        padding-bottom: 1;
    }
    
    TaskCard {
        border: panel #58a6ff;
        margin-bottom: 1;
        padding: 1;
        background: #21262d;
    }
    TaskCard:hover {
        background: #30363d;
        border: panel #00ff00;
    }
    .card-title { text-style: bold; }
    .card-agent { color: #f0883e; } 
    
    Markdown {
        margin: 1 0;
    }
    MarkdownH1, MarkdownH2, MarkdownH3 {
        color: #00ff00;
        text-style: bold;
    }
    MarkdownFence {
        border: solid #e3b341; 
        background: #0d1117;
        margin: 1 0;
    }
    """
    
    SCREENS = {"chat": ChatScreen, "kanban": KanbanScreen}
    BINDINGS = [("d", "toggle_dark", "Toggle dark mode"), ("q", "quit", "Quit")]

    def on_mount(self) -> None:
        self.push_screen("chat")

if __name__ == "__main__":
    app = OdysseusDashboard()
    app.run()