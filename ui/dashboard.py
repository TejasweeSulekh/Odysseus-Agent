from textual.app import App, ComposeResult
from textual.containers import Horizontal, VerticalScroll
from textual.widgets import Header, Footer, Static, Label, Markdown
from textual.message import Message
import sqlite3
import os
import sys
sys.path.append(os.path.dirname(os.path.dirname(__file__)))
from core.telemetry import get_system_metrics

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'database', 'odysseus.db')

class TaskCard(Static):
    """A widget to display a single task."""
    
    # Define a custom message to tell the App when this card is clicked
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
        """Fires when the user clicks this specific card."""
        self.post_message(self.Selected(self.task_id))

class KanbanColumn(VerticalScroll):
    """A column for a specific task status."""
    def __init__(self, status_name: str):
        super().__init__()
        self.status_name = status_name
        self.add_class(f"column-{status_name.replace(' ', '').lower()}")

    def compose(self) -> ComposeResult:
        yield Label(f"--- {self.status_name.upper()} ---", classes="column-header")

class TaskDetailPanel(VerticalScroll):
    """The side panel that shows execution logs AND Telemetry."""
    def compose(self) -> ComposeResult:
        yield Label("Odysseus Telemetry", id="telemetry-header")
        yield Label("CPU: --% | RAM: --GB", id="telemetry-data")
        yield Label("Task Details", id="detail-header")
        yield Markdown("Click a task card on the left to view its details here.", id="detail-content")
        
class OdysseusDashboard(App):
    """The main TUI application."""
    
    CSS = """
    Screen {
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
    """

    BINDINGS = [("d", "toggle_dark", "Toggle dark mode"), ("q", "quit", "Quit")]

    def compose(self) -> ComposeResult:
        yield Header()
        with Horizontal(id="main-view"):
            yield KanbanColumn("Backlog")
            yield KanbanColumn("In Progress")
            yield KanbanColumn("Review")
            yield KanbanColumn("Done")
        yield TaskDetailPanel(id="side-panel")
        yield Footer()

    def on_mount(self) -> None:
        self.load_tasks()
        # The telemetry timer we added earlier
        self.set_interval(2.0, self.update_telemetry)
        # --- The Board refresh timer ---
        self.set_interval(1.0, self.update_board)
        
    def update_board(self) -> None:
        """Wipes the board and redraws the cards to show live movement."""
        # 1. Remove all existing cards from the UI so they don't stack infinitely
        for card in self.query(TaskCard):
            card.remove()
        
        # 2. Fetch the fresh database state and redraw them
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

        for task_id, title, status, agent in tasks:
            if status in columns:
                columns[status].mount(TaskCard(task_id, title, agent))

    def update_telemetry(self) -> None:
        """Fetches new system metrics and updates the UI."""
        metrics = get_system_metrics()
        telemetry_label = self.query_one("#telemetry-data", Label)
        telemetry_label.update(
            f"CPU: {metrics['cpu']}%\n"
            f"RAM: {metrics['ram_used']} / {metrics['ram_total']} GB ({metrics['ram_percent']}%)\n"
            f"Disk: {metrics['disk']}%"
        )

    def on_task_card_selected(self, message: TaskCard.Selected) -> None:
        """Catches the custom click message from the TaskCard."""
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        # 1. Get Task Info
        cursor.execute("SELECT title, description, status, assigned_agent FROM tasks WHERE id = ?", (message.task_id,))
        task = cursor.fetchone()
        
        # 2. Get Execution Logs for this task
        cursor.execute("SELECT agent_name, thought FROM execution_logs WHERE task_id = ? ORDER BY timestamp ASC", (message.task_id,))
        logs = cursor.fetchall()
        
        conn.close()

        if task:
            title, description, status, agent = task
            
            # Format the logs
            log_text = ""
            if logs:
                for log_agent, thought in logs:
                    log_text += f"**[{log_agent}]**\n{thought}\n\n---\n"
            else:
                log_text = "*(Awaiting agent execution...)*"

            markdown_text = f"""
# {title}
**Status:** {status} | **Agent:** {agent}
***
### Description
{description}

***
### Execution Logs
{log_text}
            """
            
            detail_view = self.query_one("#detail-content", Markdown)
            detail_view.update(markdown_text)
            
    

if __name__ == "__main__":
    app = OdysseusDashboard()
    app.run()