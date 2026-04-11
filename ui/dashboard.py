from textual.app import App, ComposeResult
from textual.screen import Screen
from textual.containers import Horizontal, VerticalScroll, Vertical
from textual.widgets import Header, Footer, Static, Label, Markdown, Input, RichLog
from textual.message import Message
from textual import work
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
        yield Markdown("Click a task card on the left to view its details here.", id="detail-content")

# --- SCREENS ---

class ChatScreen(Screen):
    """The default conversational interface."""
    def compose(self) -> ComposeResult:
        yield Header()
        yield RichLog(id="chat-log", wrap=True, highlight=True, markup=True)
        yield Input(placeholder="Talk to Odysseus or give an engineering command...", id="chat-input")
        yield Footer()

    def on_mount(self) -> None:
        log = self.query_one(RichLog)
        log.write("[bold green]=== ODYSSEUS OS ONLINE ===[/bold green]")
        log.write("[dim]System initialized. Awaiting commands.[/dim]\n")

    async def on_input_submitted(self, event: Input.Submitted) -> None:
        user_text = event.value
        if not user_text.strip(): return
        
        event.input.value = ""
        log = self.query_one(RichLog)
        
        log.write(f"[bold cyan]YOU:[/bold cyan] {user_text}")
        log.write("[dim italic]Odysseus is thinking...[/dim italic]")
        
        # Route to Supervisor
        reply = await orchestrate(user_text)
        log.write(f"[bold yellow]ODYSSEUS:[/bold yellow] {reply}\n")
        
        # Trigger Screen Switch if tasks were generated
        if "[SYSTEM] Agentic Mode Triggered" in reply:
            self.app.push_screen("kanban")

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
        yield Input(placeholder="Inject a hint or chat while agents work...", id="kanban-input")
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

        # --- NEW: Completion Detection Logic ---
        all_done = True
        has_tasks = False

        for task_id, title, status, agent in tasks:
            has_tasks = True
            if status != "Done":
                all_done = False
            if status in columns:
                columns[status].mount(TaskCard(task_id, title, agent))

        # If there are tasks and they are ALL in the Done column, trigger the hook
        if has_tasks and all_done:
            # Check a flag to ensure we don't trigger this 10 times a second
            if not hasattr(self, "is_synthesizing") or not self.is_synthesizing:
                self.is_synthesizing = True
                self.trigger_synthesis()

    @work
    async def trigger_synthesis(self) -> None:
        """Transitions back to Chat and asks the Supervisor for a summary."""
        # 1. Safely switch back to chat
        self.app.switch_screen("chat")
        chat_screen = self.app.get_screen("chat")
        chat_log = chat_screen.query_one(RichLog)
        
        # 2. Show a loading state
        chat_log.write("\n[dim italic]Tasks complete. Odysseus is synthesizing the results...[/dim italic]")
        
        # 3. Call the hidden system hook
        reply = await orchestrate("[SYSTEM] TASK_BATCH_COMPLETE")
        
        # 4. Display the final summary
        chat_log.write(f"[bold yellow]ODYSSEUS:[/bold yellow] {reply}\n")
        
        # 5. Reset the flag
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

    async def on_input_submitted(self, event: Input.Submitted) -> None:
        user_text = event.value
        if not user_text.strip(): return
        
        event.input.value = ""
        reply = await orchestrate(user_text)
        
        # If the user asks a normal question, switch back to chat mode to show the answer
        if "[SYSTEM] Agentic Mode Triggered" not in reply:
            self.app.switch_screen("chat")
            chat_screen = self.app.get_screen("chat")
            chat_log = chat_screen.query_one(RichLog)
            chat_log.write(f"[bold cyan]YOU:[/bold cyan] {user_text}")
            chat_log.write(f"[bold yellow]ODYSSEUS:[/bold yellow] {reply}\n")


# --- MAIN APP ---

class OdysseusDashboard(App):
    CSS = """
    Screen {
        layout: vertical;
    }
    #chat-log {
        height: 1fr;
        border: solid green;
        margin: 1;
        padding: 1;
        background: $surface;
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
        border-left: solid green;
        padding: 1 2;
        background: $surface;
    }
    #detail-header {
        text-style: bold;
        color: yellow;
        padding-bottom: 1;
        border-bottom: solid green;
        width: 100%;
    }
    KanbanColumn {
        width: 1fr;
        height: 1fr;
        border: solid green;
        margin: 1 1;
        padding: 1;
    }
    .column-header {
        text-align: center;
        text-style: bold;
        padding-bottom: 1;
    }
    TaskCard {
        border: panel cyan;
        margin-bottom: 1;
        padding: 1;
        background: $panel;
    }
    TaskCard:hover {
        background: $accent;
    }
    .card-title { text-style: bold; }
    .card-agent { color: yellow; }
    Input {
        dock: bottom;
        margin: 0 1 1 1;
    }
    """
    
    SCREENS = {"chat": ChatScreen, "kanban": KanbanScreen}
    BINDINGS = [("d", "toggle_dark", "Toggle dark mode"), ("q", "quit", "Quit")]

    def on_mount(self) -> None:
        # Start in Chat Mode
        self.push_screen("chat")

if __name__ == "__main__":
    app = OdysseusDashboard()
    app.run()