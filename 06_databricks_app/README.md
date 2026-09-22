# Layer 6 - Databricks App (surface to the business)

The business-facing surface: a React (Vite) + FastAPI app deployed as a Databricks App. Two
tabs, each pairing a governed dashboard with an AI chat panel.

- **Eligibility Triage** - open cases, eligibility denials, the internal-vs-state coverage
  discrepancy table (from `state_eligibility_corroboration`), and a prioritized Salesforce
  case queue. Sample prompts triage a specific case or member.
- **Claims Trends & Inventory** - denial trends over time, denial-category breakdown, open
  cases by state × line-of-business. Sample prompts explore provider disputes and trends.

## How it works
- `GET /api/summary` runs the governed SQL (row counts, KPIs, trends) - the *same* certified
  layer the Genie agent uses.
- `POST /api/chat` proxies the conversation to the Multi-Agent Supervisor (`04_genai_agent/`),
  auto-approves tool calls, and streams intermediate steps back to the UI.

## Contents
- `app.py`, `app.yaml` - FastAPI entrypoint + Databricks App config (env: `MAS_ENDPOINT_NAME`,
  `WAREHOUSE_ID`, `CATALOG`, `SCHEMA`).
- `server/` - dual-mode auth (App service principal vs. local profile), chat + summary routes.
- `frontend/` - React SPA (two tabs, chat panel, markdown rendering). `node_modules`/`dist`
  are gitignored; run `npm install && npm run build` to rebuild.

Full architecture: [`../docs/APP_OVERVIEW.md`](../docs/APP_OVERVIEW.md).

## Connects to
- **Up:** reads governed SQL (`02_`) and proxies chat to the Gen AI supervisor (`04_`), which
  in turn uses the Genie agent (`05_`). It is the top of the same one journey.
