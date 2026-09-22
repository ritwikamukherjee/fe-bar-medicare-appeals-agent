# Decisions & trade-offs

A short record of the engineering choices behind this build and why. The FE Bar rewards
this explicitly ("Why this approach and not another?").

## 1. Certified metric views vs. prompting the agent over raw tables
**Chose:** define 8 governed metric views (overturn rate, denial dollars, provider risk,
fraud exposure, GLP-1 utilization, eligibility coverage) with `MEASURE()` semantics.
**Why:** an agent that computes KPIs ad-hoc will drift - one question gets `AVG(is_overturned)`,
the next gets something subtly different. Certified metrics give one governed definition that
Genie and the dashboard both use. Evidence §6 shows Genie choosing `MEASURE(Overturn Rate)`
on its own. **Trade-off:** more up-front modeling; worth it for trust and reproducibility.

## 2. Declared PK/FK (RELY) graph vs. leaving joins to the model
**Chose:** declare 6 PK + 14 FK constraints as `RELY` (zero-orphan verified).
**Why:** Genie infers joins from the declared relationships instead of guessing, and the
optimizer can use them. Cross-domain questions (provider risk × fraud, appeal × original
denial) traverse real keys. **Trade-off:** you must keep the data clean enough to declare
RELY honestly; enforced at generation time.

## 3. Multi-Agent Supervisor vs. a single RAG chain
**Chose:** a supervisor that routes to Genie (aggregates/trends), Unity Catalog SQL functions
(per-member / per-claim briefs), and a ClinicalTrials.gov MCP (medical-necessity evidence).
**Why:** appeals triage spans two very different question shapes - population analytics and
single-record dossiers - plus external clinical evidence. One retrieval chain can't serve all
three well. **Trade-off:** orchestration complexity and per-request tool registration.

## 4. Agent Bricks MAS vs. a code-based supervisor
**Chose:** run the managed Agent Bricks MAS in production, but keep a **code-based supervisor**
(`04_genai_agent/agent.py`) as the resilient fallback.
**Why:** the managed MAS registers all tools per request and fails the *whole* request if any
one tool fails to register. Two external MCP servers (Medicare Part D behind Cloudflare bot
protection; a PubMed server) were intermittently failing and taking the endpoint down with
them. I removed the flaky MCPs and kept only the reliable ClinicalTrials one. The code-based
supervisor wraps each MCP `list_tools()` in try/except, so a bad server is *skipped*, not
fatal. **Trade-off:** managed simplicity and built-in tracing vs. graceful degradation and
control. Documented in `docs/FOLLOWUP.md`.

## 5. Lakebase (Postgres) for operational serving vs. serving search from the lakehouse
**Chose:** load case narratives into Lakebase managed Postgres, compute 1024-dim embeddings,
build a pgvector ANN index + a BM25 tsvector, and fuse them with reciprocal-rank fusion.
**Why:** member-services search is an OLTP-latency, per-request workload and needs *hybrid*
(semantic + keyword) retrieval because the narrative is free text but the codes (CARC, CPT,
ICD-10) are structured. Analytics stays on the lakehouse; operational lookup goes to Lakebase.
**Trade-off:** a second engine to operate; justified by latency and the hybrid requirement.

## 6. Gen AI to satisfy "make it intelligent" (no trained ML model)
**Chose:** satisfy the intelligence layer with Gen AI (the supervisor + Genie), not a trained
classifier. **Why:** the customer value here is governed natural-language triage and
routing, which Gen AI serves directly. An overturn-likelihood model is a strong *next* step
(scores in the dashboard, feeds reviewer prioritization) and the certified feature layer to
train it already exists - noted as future work rather than scope creep for this build.
