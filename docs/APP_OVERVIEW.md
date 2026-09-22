# Medicare Appeals Chat — App Overview

A **Databricks App** for a Molina Healthcare claims-operations team, built to triage
incoming Medicare/Medicaid **claim-denial and appeals** cases. It pairs a live
operations dashboard with an AI supervisor agent that answers case-worker questions
over Molina's internal claims data.

- **Live URL:** https://medicare-appeals-chat-1602460480284688.aws.databricksapps.com/
- **Workspace:** `fe-vm-hls-amer` (profile `hls_amer`)
- **Stack:** React (Vite) frontend + FastAPI backend, deployed as a Databricks App.

## What a user sees — two tabs

Both tabs share a left-side **dashboard** (from `/api/summary`) and a right-side
**AI chat panel** (from `/api/chat`). Each tab just frames a different slice of the data
and offers different sample prompts.

1. **Eligibility Triage** — KPI tiles (open cases, eligibility denials, state
   discrepancies, WA Medicaid members), the incoming Salesforce case queue
   (prioritized), and a state-eligibility corroboration / discrepancy table (internal
   coverage vs. WA HCA state files). Sample prompts triage a specific case or member.
2. **Claims Trends & Inventory** — denial trends over time, denial-category breakdown,
   and open cases by state × line-of-business. Sample prompts explore provider disputes
   and denial trends.

## How it works

- **`GET /api/summary`** runs ~8 parallel SQL queries against
  `hls_amer_catalog.`appeals-review`` (tables: `members`, `claims`, `eligibility`,
  `appeals`, `prior_authorizations`, `salesforce_cases`, `state_eligibility_corroboration`,
  `wa_hca_eligibility_raw`) and returns the dashboard data (cached).
- **`POST /api/chat`** proxies the conversation to a **Multi-Agent Supervisor (MAS)**
  serving endpoint (`mas-acd1e8ba-endpoint`, Agent Bricks tile
  `medicare-appeals-supervisor`). The supervisor routes each question to the right tool
  and synthesizes one answer. It auto-approves MCP tool calls and streams intermediate
  steps (tool calls + reasoning) back to the UI.

### Supervisor tools (current, all verified working)

| Tool | Type | Purpose |
|---|---|---|
| `appeals_data_worker` | Genie space | Aggregate/population questions: counts, trends, top denials, distributions |
| `member_appeal_brief` | UC function | Full per-member brief: demographics, eligibility, claims, denials, appeals, prior auth |
| `claim_investigation_summary` | UC function | Full per-claim dossier: claim, member, provider, prior auth, appeal history, peer comparison |
| `conn_clinicaltrials` | External MCP | ClinicalTrials.gov evidence for medical-necessity appeals |

The two UC functions are SQL functions in the `appeals-review` schema that read the
underlying data tables directly.

## Current known constraints

- The MAS **fails a whole request if any one tool fails to register** (registration runs
  per request, concurrently, fail-fast). This makes it sensitive to unreliable external
  MCP servers.
- Two external MCP servers were **removed** for reliability:
  - **`raven_medicare_mcp`** (Medicare Part D, `mcp-partd.medseal.app`) — a third-party
    server behind **Cloudflare Bot Management** that intermittently 403s Databricks'
    egress. Not fixable from our side; the connection object is kept for easy re-add if
    the server's protection is relaxed.
  - **`conn_aichemy_pubmed`** (PubMed, glama.ai) — intermittently fails to register.
  - Running multiple flaky external MCPs at once compounded the failures; **one** external
    MCP (ClinicalTrials) alone is reliable, so it was kept.
- To restore all clinical-evidence MCP tools reliably, switch the app from the Agent
  Bricks MAS to the **code-based supervisor** in `supervisor/agent.py` (it wraps each MCP
  `list_tools()` in try/except, so a flaky server is skipped rather than fatal) and add
  the two UC functions to it.

## Repo layout

- `app.py`, `app.yaml` — FastAPI entrypoint + Databricks App config (env: `MAS_ENDPOINT_NAME`,
  `WAREHOUSE_ID`, `CATALOG`, `SCHEMA`).
- `server/config.py` — dual-mode auth (App service principal vs. local CLI profile).
- `server/routes/chat.py` — MAS proxy + MCP auto-approval loop.
- `server/routes/summary.py` — dashboard SQL queries.
- `frontend/` — React SPA (two tabs, chat panel, markdown rendering).
- `supervisor/` — an alternative code-based ResponsesAgent supervisor (`agent.py`) and its
  deploy script (`deploy.py`); not what the live app currently points at.
