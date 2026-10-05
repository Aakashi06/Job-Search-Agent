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

You describe the role in plain language. If a detail is missing, the UI asks a short multiple-choice question, with an Other option. Python searches the web and reads a few pages. A tiny local model, `SmolLM2-135M-Instruct`, extracts the matching jobs in one pass. Results land in a quiet chat UI, with thinking dots while it works.

```text
preferences  →  clarify  →  search and read  →  extract  →  chat results
```

After warmup, a search stays near 10 seconds. The model preloads in the background so the first real query is already warm.

<p align="center">
  <img width="48%" alt="Job Search Agent chat" src="https://github.com/user-attachments/assets/668056e3-1617-4ec3-adda-212aa93547c8" />
  <img width="48%" alt="Job Search Agent results" src="https://github.com/user-attachments/assets/2e1571eb-4998-454f-9c0f-9d48ef53e017" />
</p>

<p align="center">
  <sub>Chat · results</sub>
</p>

---

## Features

- **Natural-language brief.** Type the role, stack, location, or constraints the way you would say them.
- **Guided clarify step.** Missing details become multiple-choice questions, with Other when none of the options fit.
- **Live web search.** Python finds pages and reads a few of them before the model runs.
- **One local pass.** `SmolLM2-135M-Instruct` extracts and ranks jobs from the fetched text.
- **Minimal chat UI.** Themes, multi-select, and a thinking state while the search runs.
- **Streaming updates.** FastAPI serves the UI and pushes progress over SSE.
- **Stays on your machine.** Search, fetch, and the model run locally. The model downloads once.

---

## How the work is split

| Piece | Owns |
| --- | --- |
| **Python** | Web search, page fetch, dates, dedupe, formatting |
| **Local model** | Extract and rank jobs from the fetched text |
| **UI** | Preferences, clarifying questions, results |

---

## Stack

| Layer | Choice |
| --- | --- |
| UI | `static/index.html` |
| Server | FastAPI, SSE, model preload (`app.py`) |
| Clarify | `clarify.py` |
| Search | `agent.py` |
| Results | `postprocess.py` |
| Model | `SmolLM2-135M-Instruct`, set in `config.py` |

---

## Project layout

```text
Job-Search-Agent/
├── app.py              # FastAPI server, SSE, model preload
├── agent.py            # search + one local model pass
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
