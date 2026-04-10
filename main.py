import argparse
import subprocess
import sys

def launch_dashboard():
    """Starts the Textual Kanban UI."""
    print("Launching Odysseus Dashboard...")
    subprocess.run([sys.executable, "ui/dashboard.py"])

def launch_supervisor(goal):
    """Sends a goal to the background supervisor."""
    print(f"Dispatching goal to Supervisor: {goal}")
    subprocess.run([sys.executable, "core/supervisor.py", goal])

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Odysseus Agent OS CLI")
    
    # We can either pass a goal to run the backend, or pass nothing to open the UI
    parser.add_argument("--goal", "-g", type=str, help="The high-level goal to send to the Supervisor")
    
    args = parser.parse_args()

    if args.goal:
        launch_supervisor(args.goal)
    else:
        launch_dashboard()