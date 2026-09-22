# Layer 4 — Gen AI: Multi-Agent Supervisor

Makes the data intelligent. A supervisor agent routes each question to the right tool and
synthesizes one answer. This directory holds the **code-based** supervisor (the resilient
variant); the production app can point at either this or the managed Agent Bricks MAS.

## Tools the supervisor routes to
| Tool | Type | Purpose |
|---|---|---|
| `appeals_data_worker` | Genie space (`05_genie_agent/`) | Aggregate/population questions: counts, trends, overturn rates |
| `member_appeal_brief` | Unity Catalog SQL function | Full per-member brief: eligibility, claims, denials, appeals, prior auth |
| `claim_investigation_summary` | Unity Catalog SQL function | Full per-claim dossier + peer comparison |
| `conn_clinicaltrials` | External MCP | ClinicalTrials.gov evidence for medical-necessity appeals |

## Contents
- [`agent.py`](agent.py) — code-based ResponsesAgent supervisor. Wraps each MCP
  `list_tools()` in try/except so a flaky external server degrades gracefully instead of
  failing the whole request.
- [`deploy.py`](deploy.py) — deploy to a Model Serving endpoint.

## Design decision
Managed Agent Bricks MAS vs. this code-based supervisor: see
[`../docs/DECISIONS_AND_TRADEOFFS.md`](../docs/DECISIONS_AND_TRADEOFFS.md) §4. Short version:
the managed MAS fails a request if any one tool fails to register, which is brittle against
unreliable external MCP servers; the code-based version isolates each tool.

## Connects to
- **Up:** calls the Genie agent (`05_genie_agent/`) and UC SQL functions over the governed
  schema (`02_unity_catalog_governance/`).
- **Down:** the app (`06_databricks_app/`) proxies its chat panel to this agent's endpoint.
