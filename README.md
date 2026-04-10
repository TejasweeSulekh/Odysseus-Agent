# Odysseus-Agent 👁️

**Intelligence in plain sight. Observable local intelligence.**

Odysseus is a localized, hardware-accelerated Agent Operating System. It eschews the "black box" chatbot interface in favor of a multi-threaded Kanban dashboard. You act as the orchestrator; the agents do the work. 

## Features
* **Clear-Box Autonomy:** See every thought, tool call, and execution trace in real-time.
* **Decoupled Architecture:** The UI, state machine (SQLite), and Agent Engine run independently.
* **Edge-Optimized:** Designed to run local, quantized models (like Gemma 4) with highly compressed KV caches.

## Quick Start
1. Ensure `ollama serve` is running in the background.
2. Load the model: `ollama run gemma4`
3. Activate the environment: `source .venv/bin/activate`
4. Launch the CTO Dashboard: `python ui/dashboard.py`