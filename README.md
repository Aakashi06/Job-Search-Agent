# Job Search Agent

Minimal local AI job-discovery agent with an interactive **web UI**.

Uses a tiny free local model (`SmolLM2-135M-Instruct`) plus Python web search/fetch for ~10s responses.
<img width="1919" height="1001" alt="image" src="https://github.com/user-attachments/assets/668056e3-1617-4ec3-adda-212aa93547c8" />
<img width="1905" height="966" alt="image" src="https://github.com/user-attachments/assets/2e1571eb-4998-454f-9c0f-9d48ef53e017" />




## What it does

1. You type natural-language job preferences in the browser
2. If details are missing, the UI asks multiple-choice questions (with Other)
3. Python searches the web and reads a few pages
4. The local model extracts matching jobs in one short pass
5. Results appear in a minimal chat UI with thinking dots

## Requirements

- macOS (Apple Silicon recommended)
- Python 3.10+
- ~1 GB free disk for the 360M model (downloaded once)

## Setup

```bash
cd "Job Search Agent"
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Run the web UI

```bash
source .venv/bin/activate
python app.py
```

Opens your **system browser** at [http://127.0.0.1:8000](http://127.0.0.1:8000).

The 135M model preloads in the background so searches stay near ~10s after warmup.

## Project layout

| File | Role |
|------|------|
| `app.py` | FastAPI server + SSE + model preload |
| `static/index.html` | Chat UI (themes, multi-select, Other) |
| `clarify.py` | Preference questions |
| `agent.py` | Fast search + one local LLM pass |
| `postprocess.py` | Filter / dedupe / JSON shape |
| `config.py` | Model id and speed limits |

## Design notes

- **Python:** web search, page fetch, dates, dedupe, formatting
- **LLM (local, free):** extract / rank jobs from fetched text
- No paid APIs, LangChain, LangGraph, RAG, or vector DB
