# Follow-up / Deferred Work

Status as of 2026-07-13. The app is **live and working** (see `APP_OVERVIEW.md`). These
items were intentionally deferred — nothing here is blocking.

## 1. Restore the remaining external MCP tools (Part D + PubMed)

**Currently out of the supervisor:** `raven_medicare_mcp` (Medicare Part D) and
`conn_aichemy_pubmed` (PubMed). Both UC connection objects are still intact — no rebuild
needed, just re-wiring.

**Why they're out:** the Agent Bricks MAS registers all tools per request and fails the
*whole* request if any one tool fails to register. These external MCP servers are
unreliable:
- **Part D** (`mcp-partd.medseal.app`) sits behind **Cloudflare bot-protection** that
  intermittently returns a 403 challenge to Databricks' egress. Not fixable from our side
  (it's a third-party server). Only fixes: the server owner relaxes Cloudflare, or we drop
  it.
- **PubMed** (glama.ai) intermittently fails to register too.
- Running several flaky MCPs at once compounds the failures. **One** external MCP
  (ClinicalTrials, currently live) is reliable.

**Durable fix (the real to-do):** switch the app from the Agent Bricks MAS to the
**code-based supervisor** already in `supervisor/agent.py`. It wraps each MCP
`list_tools()` in try/except, so a flaky server is *skipped*, not fatal — Part D/PubMed
would degrade gracefully instead of taking the whole endpoint down.
- Add the two UC-function tools (`member_appeal_brief`, `claim_investigation_summary`) to
  that agent — it currently only has Genie + the 3 MCPs.
- Deploy via `supervisor/deploy.py`, then point `MAS_ENDPOINT_NAME` in `app.yaml` at the
  new endpoint and redeploy the app.

## 2. Environment / auth housekeeping

- The `hls_amer` OAuth token expires frequently (lapsed mid-session). Re-login:
  `databricks auth login -p hls_amer --host https://fe-vm-hls-amer.cloud.databricks.com`
- The **Databricks MCP server** (the `mcp__databricks__*` tools) is stuck on a stale
  `DEFAULT`-profile PAT and returns "Invalid access token". Repoint it at the `hls_amer`
  OAuth profile in the MCP config so those tools work again. (All work this session was
  done via the `databricks` CLI as a workaround.)

## Current live supervisor tools (for reference)
`appeals_data_worker` (Genie) · `member_appeal_brief` (UC func) ·
`claim_investigation_summary` (UC func) · `conn_clinicaltrials` (MCP).
