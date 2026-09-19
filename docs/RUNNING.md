# Running the application

Every command below was run against a fresh clone of this repository on macOS
before being written down.

---

## What you need

| | Why |
|---|---|
| **Python 3.11+** | the agent and API |
| **[uv](https://docs.astral.sh/uv/)** | dependency install (`brew install uv`) |
| **Node 20+** | building the supervision UI |
| **A local model server** | *optional* — Ollama or llama.cpp. The agent runs without one, it simply asks more questions |

---

## First run

```bash
git clone https://github.com/Rakeshreddysr2401/HR_Automation_Agents.git
cd HR_Automation_Agents

# 1. Python environment
uv venv --python 3.11
VIRTUAL_ENV="$PWD/.venv" uv pip install -e ".[dev]"

# 2. Build the UI (served by the API, so there is only ever one server)
cd web && npm install && npm run build && cd ..

# 3. Start
.venv/bin/uvicorn app.main:app --port 8000
```

Open **http://localhost:8000** and press *Run the sample migration*.

> **`VIRTUAL_ENV=` is not decoration.** `uv` installs into whatever virtual
> environment the shell already has active, which — if you have another project's
> venv activated — is not this one. Setting it explicitly pins the install to this
> repository. Alternatively `source .venv/bin/activate` first and drop the prefix.

### What you should see

The agent reads both sample exports and stops with **ten questions** out of 35
source columns and 52 people. That ratio is the point of the project: everything
else it settled on its own.

The questions are one contested column mapping, one date column with no way to tell
day-first from month-first, one unrecognised department value, a suspected rehire, a
suspected duplicate, and five records that will not load.

---

## Day-to-day

```bash
.venv/bin/uvicorn app.main:app --reload --port 8000
```

`--reload` restarts the API when Python changes. It does **not** rebuild the UI.

### Working on the UI

Run two servers so the frontend hot-reloads:

```bash
.venv/bin/uvicorn app.main:app --port 8000    # terminal 1
cd web && npm run dev                          # terminal 2 → http://localhost:5173
```

Vite proxies `/api` and `/mock-target` to port 8000, so the UI behaves identically.
When you are finished, `npm run build` so the single-server path serves the changes.

### Regenerating the sample data

```bash
.venv/bin/python scripts/make_sample_data.py
```

Rewrites the three files in `data/`. Every defect in them is deliberate and
exercises one specific branch of the escalation policy, so changing this script
changes which questions the agent asks.

### Starting from a clean slate

```bash
rm -f migration.db checkpoints.db
```

`migration.db` holds runs, escalations, records and the audit trail;
`checkpoints.db` holds the graph state that lets an interrupted run resume. Deleting
both resets everything — **including the agent's learned column mappings**.

---

## Pointing it at your own models

Chat and embeddings are configured **separately**, because they usually live on
different machines: a llama.cpp host serving a chat model has no embedding model
loaded. Copy `.env.example` to `.env` and edit.

### Ollama on this machine (the default)

```bash
OLLAMA_HOST=0.0.0.0 ollama serve
ollama pull nomic-embed-text
ollama pull gemma4
```

No `.env` needed — those are the defaults.

### llama.cpp on another machine

llama.cpp speaks the OpenAI-compatible API, so the provider is `openai` and the base
URL ends in `/v1`:

```bash
REASONING_PROVIDER=openai
REASONING_BASE_URL=http://singireddys-mac-mini.local:8080/v1
REASONING_MODEL=gemma-4-12B-it-Q4_K_M

# embeddings stay on local Ollama
EMBEDDING_PROVIDER=ollama
EMBEDDING_BASE_URL=http://localhost:11434
EMBEDDING_MODEL=nomic-embed-text
```

Check what the app can actually reach:

```bash
curl -s localhost:8000/api/health | python3 -m json.tool
```

The UI shows the same thing as two badges in the header.

### Running with no models at all

```bash
LLM_ENABLED=false
```

The agent falls back to lexical matching for column mapping. It still completes the
whole migration; it simply escalates more, because scores spread less and fewer
mappings clear the confidence bar. **Failing toward asking is the correct direction**,
and the header says so when it happens.

---

## Using the API directly

The UI is a client of a plain HTTP API — useful for scripting a demo.

```bash
# start a run over the bundled samples
RID=$(curl -s -X POST localhost:8000/api/runs \
  -H 'Content-Type: application/json' -d '{"use_sample":true}' \
  | python3 -c "import sys,json;print(json.load(sys.stdin)['run_id'])")

# watch it work (server-sent events)
curl -N localhost:8000/api/runs/$RID/events

# answer questions, then reopen the stream to resume
curl -X POST localhost:8000/api/runs/$RID/decisions \
  -H 'Content-Type: application/json' \
  -d '{"decisions":{"contest:legacy_hris_export.csv:work_email":"Official Email"}}'

curl -s localhost:8000/api/runs/$RID/audit | python3 -m json.tool
```

Interactive docs at **http://localhost:8000/docs**.

The mock target system is mounted in the same app, so you can inspect what was
actually loaded:

```bash
curl -s localhost:8000/mock-target/v1/employees | python3 -m json.tool
curl -X POST localhost:8000/mock-target/v1/_reset      # empty it
```

---

## When something goes wrong

**The page loads but says the UI is not built.**
`cd web && npm install && npm run build`. The API serves `web/dist`, which is not
committed.

**`ModuleNotFoundError` even though the install succeeded.**
It went into a different virtual environment. Reinstall with
`VIRTUAL_ENV="$PWD/.venv" uv pip install -e ".[dev]"`.

**Port 8000 is taken.**
`--port 8001`. If you are running the UI dev server too, update the proxy targets in
`web/vite.config.ts` to match.

**The header says no model is reachable.**
Expected if nothing is running locally — the agent still works. To fix it, check
`curl localhost:11434/api/tags` for Ollama, or `curl <base-url>/models` for
llama.cpp, and confirm `.env` points at the right host.

**A run seems stuck.**
Look at the terminal. The analyse pass is a few seconds with warm embeddings, longer
on the first run while every target field is embedded. `GET /api/runs/{id}/summary`
shows the current state.

**The agent asks far more than ten questions.**
Almost always means no embedding model is reachable, so mapping is running on column
names alone. Check the header badges.
