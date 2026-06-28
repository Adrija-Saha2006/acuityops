# AcuityOps — Autonomous Vendor Compliance Agent

## Problem

Companies lose thousands of dollars each month because vendor SLA violations go undetected.
Manually auditing contract clauses against performance logs is slow, error-prone, and rarely
happens consistently. AcuityOps automates the entire pipeline — from contract parsing to
dispute drafting — while keeping a human in the loop before any formal action is taken.

## What it does

1. **Ingest** — Upload a vendor SLA (`.txt` or `.pdf`). An LLM extracts every enforceable
   numeric obligation (threshold, unit, penalty) as structured data.
2. **Audit** — Submit operational logs. The system compares each metric against its contract rule.
3. **Gather** — If a required metric is missing from the logs, the agent autonomously fetches
   it via a tool (mock vendor DB; swappable for a real API). It loops back to re-audit with
   the new data.
4. **Draft** — Violations are compiled into a formal dispute notice with breach details and
   estimated penalties.
5. **Approve** — Execution pauses. A manager reviews the draft and resumes with `approve` or
   `reject` via a separate HTTP call. Only then does the run complete.

## Architecture

```
        +----------+
START ->  | Auditor  | --(data complete?)--> [generate_dispute] -> [human_approval] -> END
        +----------+                                                      ^
             ^                                                            |
        no   |                                                   interrupt() pauses here
             |
   +------------------+
   |  Info-Gatherer   |  <- calls lookup_vendor_metric tool
   |  (tool call)     |
   +------------------+
```

**Why a cyclic graph and not a linear script?**

A script assumes you have all the data upfront. Real vendor audits don't — a contract may
require metrics your log export didn't include. The cycle lets the agent notice the gap,
fetch the missing data autonomously, and re-audit without human intervention. The
`MAX_GATHER_ATTEMPTS` cap guarantees the loop terminates even if a metric is permanently
unavailable.

The `interrupt()` is not a fake `input()` call. LangGraph checkpoints the entire graph state
to an in-memory store, so the run can be resumed from a completely separate HTTP request —
or, with a persistent checkpointer, from a different process hours later.

## How each part of the training maps to the build

| Week | Skill | Where it shows up |
|------|-------|-------------------|
| 1 — Python / Git | Pydantic models, defensive parsing, branch-per-feature workflow | `app/models.py`, `app/parsing.py`, git log |
| 2 — Prompting / APIs | `with_structured_output()`, few-shot + chain-of-thought extraction prompt | `app/extraction.py` |
| 3 — LangChain / LangGraph | Cyclic `StateGraph`, custom `@tool`, `interrupt()` guardrail | `app/graph.py`, `app/tools.py` |
| 4 — FastAPI | Async start / pause / resume across HTTP requests | `app/main.py` |

## Tech stack

| Layer | Library |
|-------|---------|
| Agent orchestration | LangGraph 1.x |
| LLM integration | LangChain 1.x + langchain-groq |
| LLM | Llama 3.3 70B via Groq (free tier) |
| API | FastAPI 0.115+ with async endpoints |
| Frontend | Vanilla HTML/CSS/JS served via FastAPI static files |
| Data validation | Pydantic v2 |
| PDF parsing | pypdf |

## Run it

```bash
# 1. Clone the repo
git clone https://github.com/YOUR-USERNAME/acuityops.git
cd acuityops

# 2. Create virtual environment and install dependencies
python -m venv .venv
.venv\Scripts\activate        # Windows
pip install -r requirements.txt

# 3. Add your API key to .env
# GROQ_API_KEY=gsk_...
# USE_MOCK_LLM=false

# 4. Start the server
uvicorn app.main:app --reload
```

Open **http://127.0.0.1:8000** in your browser. You will see the web UI.

## Demo walkthrough

**Step 1 — Upload Contract**
- Click the upload zone under Step 01
- Select `data/aws_ec2_sla.txt` (or any `.txt`/`.pdf` SLA)
- Click **Extract Rules** — the LLM reads the contract and returns structured rules

**Step 2 — Upload Vendor Logs**
- Upload any file from `data/logs_*.json`
- OR use the **Log Generator** (purple Helper panel) — enter the incident month and downtime hours, click Generate
- Click **Run Audit**

**Step 3 — Review & Approve**
- Violations appear as cards with breach details and penalty labels
- The drafted dispute letter is shown below
- Click **Approve & Send Dispute** to complete the run

## Sample data included

| SLA file | Log file | What it tests |
|----------|----------|--------------|
| `aws_ec2_sla.txt` | `sample_logs.json` | Jul 2024 Kinesis outage — 10% credit |
| `aws_ec2_sla.txt` | `logs_aws_dec2021_critical.json` | Dec 2021 critical outage — 30% credit |
| `aws_ec2_sla.txt` | `logs_aws_nov2020.json` | Nov 2020 Kinesis cascade — 10% credit |
| `aws_ec2_sla.txt` | `logs_cloudflare_jul2019.json` | 27-min Cloudflare outage |
| `ACME_Cloud_Services_SLA.txt` | `logs_acme_violations.json` | Dollar penalty violations |
| `ACME_Cloud_Services_SLA.txt` | `logs_acme_compliant.json` | Compliant month — no violations |

## Design decisions and trade-offs

**InMemorySaver vs persistent checkpointer** — `InMemorySaver` is fine for a demo and keeps
the setup to zero dependencies. For durability across server restarts I would swap in
`AsyncSqliteSaver` from `langgraph-checkpoint-sqlite` — one line change in `build_graph()`.

**Mock LLM extraction** — The Gemini integration is fully wired (`USE_MOCK_LLM=false`
activates it). The mock exists because the free-tier project quota on Google AI Studio can
be zero until billing is configured; it lets the rest of the system run and be evaluated
without an active API key.

**Mock vendor tool** — `lookup_vendor_metric` queries a hardcoded dict. In production this
would call a real vendor API or internal database. The tool interface (`@tool` decorator,
structured return) is production-ready; only the data source changes.

**Graph compiled once at startup** — `GRAPH = build_graph()` runs at module load, not inside
the request handler. If it were per-request, each request would get a fresh `InMemorySaver`
and `/approve` would never find the paused run.

## What I'd build next

- **Real vendor API integration** — replace the mock tool with authenticated HTTP calls to
  vendor portals or an internal metrics DB.
- **Persistent checkpointer** — swap `InMemorySaver` for `AsyncSqliteSaver` so paused runs
  survive server restarts.
- **Auth layer** — JWT on `/approve` so only authorised managers can resume runs.
- **Retry on tool failure** — wrap `lookup_vendor_metric` with exponential backoff before
  marking a metric as unverifiable.
