<div align="center">

# Job Search Agent

**Tell it what you want. It searches, reads, and brings back matching roles.**

A local job-discovery agent with a minimal chat UI. Preferences in, clarifying questions when needed, matching roles out.

<br />

[![Python](https://img.shields.io/badge/Python-3.10+-3776AB?style=for-the-badge&logo=python&logoColor=white)](https://github.com/Aakashi06/Job-Search-Agent)
[![FastAPI](https://img.shields.io/badge/FastAPI-009688?style=for-the-badge&logo=fastapi&logoColor=white)](https://github.com/Aakashi06/Job-Search-Agent)
[![Local model](https://img.shields.io/badge/model-SmolLM2--135M-111111?style=for-the-badge)](https://github.com/Aakashi06/Job-Search-Agent)
[![Runs locally](https://img.shields.io/badge/runs-locally-111111?style=for-the-badge)](https://github.com/Aakashi06/Job-Search-Agent)

<br />

[Source](https://github.com/Aakashi06/Job-Search-Agent) · [Author](https://github.com/Aakashi06)

</div>

---

## What it does

You describe the role in plain language. If a detail is missing, the UI asks a short multiple-choice question, with an Other option. The agent then calls its tools, and a tiny local model, `SmolLM2-135M-Instruct`, turns what they returned into job cards. Results land in a quiet chat UI, with thinking dots while it works.

```text
preferences  →  clarify  →  search tool  →  read tool  →  extract  →  chat results
```

After warmup, a search stays near 10 seconds. The model preloads in the background so the first real query is already warm.

<p>
  <img width="48%" alt="Job Search Agent chat" src="https://github.com/user-attachments/assets/668056e3-1617-4ec3-adda-212aa93547c8" />
</p>

<p>
   <img width="48%" alt="Job Search Agent results" src="https://github.com/user-attachments/assets/2e1571eb-4998-454f-9c0f-9d48ef53e017" />
</p>

---

## Tool calls

Each search runs two tools, then one model pass.

| Tool | What it does |
| --- | --- |
| **Web search** | DuckDuckGo text search from the brief plus role, location, and work mode. Returns the top hits. |
| **Page reader** | Fetches the top pages, strips them to text, and keeps a short excerpt for the model. |

`agent.py` calls them in order: search, then read, then extract. Status events stream to the UI over SSE while each step runs: Thinking, Searching, Reading, Matching, Refining.

The local model does the last step. It reads the tool output and returns matching jobs as JSON: title, company, location, skills, apply link, and why it fits.

---

## Features

- **Natural-language brief.** Type the role, stack, location, or constraints the way you would say them.
- **Guided clarify step.** Missing details become multiple-choice questions, with Other when none of the options fit.
- **Two built-in tools.** Search the web, then read the pages that came back.
- **One local pass.** `SmolLM2-135M-Instruct` extracts and ranks jobs from the tool output.
- **Minimal chat UI.** Themes, multi-select, and a thinking state while the tools run.
- **Streaming updates.** FastAPI pushes each phase over SSE.
- **Stays on your machine.** Search, fetch, and the model run locally. The model downloads once.

---

## How the work is split

| Piece | Owns |
| --- | --- |
| **Search tool** | DuckDuckGo hits for the brief |
| **Read tool** | Page fetch and clean text |
| **Local model** | Extract and rank jobs from that text |
| **Python** | Order the calls, dedupe, dates, formatting |
| **UI** | Preferences, clarifying questions, live status, results |

---

## Stack

| Layer | Choice |
| --- | --- |
| UI | `static/index.html` |
| Server | FastAPI, SSE, model preload (`app.py`) |
| Clarify | `clarify.py` |
| Tools + extract | `agent.py` |
| Results | `postprocess.py` |
| Model | `SmolLM2-135M-Instruct`, set in `config.py` |

---

## Project layout

```text
Job-Search-Agent/
├── app.py              # FastAPI server, SSE, model preload
├── agent.py            # search tool, read tool, one local model pass
├── clarify.py          # preference questions
├── postprocess.py      # filter, dedupe, JSON shape
├── config.py           # model id and speed limits
├── static/index.html   # chat UI
└── requirements.txt
```

---

## Run it

macOS, Python 3.10+. Apple Silicon is a great fit. Leave about 1 GB free for the model download.

```bash
git clone https://github.com/Aakashi06/Job-Search-Agent.git
cd Job-Search-Agent
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python app.py
```

Opens the system browser at [http://127.0.0.1:8000](http://127.0.0.1:8000).

---

## Author

Built by [Aakashi06](https://github.com/Aakashi06).
