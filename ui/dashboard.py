from textual.app import App, ComposeResult
from textual.containers import Horizontal, VerticalScroll
from textual.widgets import Header, Footer, Static, Label, Markdown
from textual.message import Message
import sqlite3
import os

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
    """The side panel that shows detailed execution logs."""
    def compose(self) -> ComposeResult:
        yield Label("Task Details", id="detail-header")
        yield Markdown("Click a task card on the left to view its execution logs and details here.", id="detail-content")

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

    def on_task_card_selected(self, message: TaskCard.Selected) -> None:
        """Catches the custom click message from the TaskCard."""
        # Query the database for the specific task details
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("SELECT title, description, status, assigned_agent FROM tasks WHERE id = ?", (message.task_id,))
        task = cursor.fetchone()
        conn.close()

        if task:
            title, description, status, agent = task
            # Format the output as Markdown
            markdown_text = f"""
# {title}
**Status:** {status} | **Agent:** {agent}
***
### Description
{description}

***
### Execution Logs
*(Awaiting agent routing...)*
            """
            
            # Update the side panel content
            detail_view = self.query_one("#detail-content", Markdown)
            detail_view.update(markdown_text)

if __name__ == "__main__":
    app = OdysseusDashboard()
    app.run()