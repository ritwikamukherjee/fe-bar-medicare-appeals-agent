# FE Bar - Submission narrative (paste into the form fields)

> These are drafted answers for the six narrative fields on the FE Bar submission form.
> Everything is anchored to real, executed output in [`evidence/RUN_EVIDENCE.md`](evidence/RUN_EVIDENCE.md).
>
> **Note on the "Customer name" field:** the FE Bar de-identifies submissions and bars
> customer-identifying content, so this is written for an **anonymized** payer rather than
> naming the real account. Use synthetic data only (this build does).

---

## Customer name
A national Medicaid / Medicare Advantage managed-care payer (anonymized; synthetic data used throughout).

## Industry / vertical
Healthcare - health insurance payer (government-sponsored managed care: Medicare Advantage, Medicaid, D-SNP).

## What is the business challenge you are solving? *
A health plan's claims-operations team is overwhelmed by denied-claim **appeals and
grievances**. To triage a single case, a worker pieces together answers from separate
systems - is the member eligible, why was the claim denied, has the provider been flagged,
what clinical evidence supports medical necessity - which is slow and inconsistent, and it
runs against regulated CMS turnaround clocks. Worse, a large share of denials are
**overturned on appeal**, so the plan pays to adjudicate the same claim twice and erodes
the member and provider experience. The team needs to (1) triage any appeal in seconds with
a governed, traceable answer, and (2) see *where* denials and overturns concentrate so they
can prevent avoidable rework and route payment-integrity risk to the front of the queue.

## How does your Databricks solution address this challenge? *
An **end-to-end data journey on Databricks**, integrated across six layers over one governed
schema (`hls_amer_catalog.`​`` `appeals-review` ``):

1. **Lakeflow** ingests synthetic payer data - members, providers, claims, prior
   authorizations, eligibility, appeals, Salesforce cases, and a fraud reference
   (33,500 claims, 2,305 appeals, 5,300 members, 17,168 prior auths; see evidence §1).
2. **Unity Catalog** governs it: a declared **6 primary-key + 14 foreign-key (RELY)** graph
   plus **8 certified metric views** (overturn rate, denial dollars, provider risk, fraud
   exposure, GLP-1 utilization, eligibility coverage) and enriched column comments/synonyms.
   This semantic ontology is what makes natural-language answers trustworthy (evidence §2-§4).
3. **Lakebase** (managed Postgres + pgvector) serves the free-text **case narratives** for
   sub-second **hybrid search** (vector + BM25 with reciprocal-rank fusion) so a member-services
   rep instantly finds similar prior cases when a member calls.
4. **Gen AI - a Multi-Agent Supervisor** routes each question to the right tool (a Genie
   space for aggregate/trend questions, Unity Catalog SQL functions for per-member and
   per-claim briefs, and a ClinicalTrials.gov MCP for medical-necessity evidence) and
   synthesizes one answer.
5. **A Genie agent** lets a business user ask in plain English; it grounds on the certified
   metrics and the declared relationships and returns governed SQL + a summary (evidence §6
   shows the live NL→SQL→answer trace using `MEASURE()` over the metric view).
6. **A Databricks App** (React + FastAPI) surfaces it: an operations dashboard driven by the
   same governed SQL, plus a chat panel that proxies to the agent.

The layers are connected, not siloed: every layer reads or writes the **same governed
schema**, so the dashboard, the Genie agent, and the supervisor all speak the same certified
definitions.

## What AI tools did you use, and what was your workflow? What decisions and trade-offs did you have to make?
**Tools.** I built with **Claude Code** (Isaac) driving the Databricks MCP server + CLI:
scaffolding the app, generating synthetic data, authoring the Unity Catalog constraints and
metric views, configuring the Genie space, and capturing execution evidence by running SQL,
the Genie Conversation API, and the app's endpoints live. On-platform AI: Databricks
Foundation Model serving, Agent Bricks Multi-Agent Supervisor, Genie, and MLflow (tracing /
LLM-as-judge scaffolding) for the agent.

**Key decisions & trade-offs (full detail in [`docs/DECISIONS_AND_TRADEOFFS.md`](docs/DECISIONS_AND_TRADEOFFS.md)):**
- **Certified metric views over raw-table prompting.** More up-front modeling work, but it
  makes Genie answers governed and reproducible (Genie picks `MEASURE(Overturn Rate)`, not an
  ad-hoc `AVG`). This is the difference between a demo and something ops can trust.
- **Multi-Agent Supervisor vs. a single RAG chain.** A supervisor that routes to Genie / SQL
  functions / MCP handles both aggregate ("overturn rate by denial reason") and row-level
  ("brief on member X") questions. Trade-off: orchestration complexity and per-request tool
  registration.
- **Agent Bricks MAS vs. a code-based supervisor.** The managed MAS fails a whole request if
  any one tool fails to register, which made it brittle against flaky external MCP servers.
  I kept only the reliable ClinicalTrials MCP live and preserved a **code-based supervisor**
  (`04_genai_agent/agent.py`) that wraps each MCP in try/except so a bad server degrades
  gracefully instead of taking the endpoint down. Trade-off: managed simplicity vs. resilience.
- **Lakebase for operational serving vs. serving from the lakehouse.** Case-narrative search
  needs OLTP-style latency and hybrid (vector + keyword) retrieval, so it belongs in Lakebase
  Postgres, while analytics stays on the lakehouse - one journey, right engine per job.

## What are the business outcomes and impact?
- **Faster triage.** One governed answer per appeal in seconds instead of a multi-system,
  multi-minute hunt - directly reducing per-case handling time against CMS turnaround clocks.
- **Less overturn-driven rework.** The overturn analysis (evidence §3) shows the two
  highest-volume denial reasons overturned ~24-25% of the time. Targeting those reasons cuts
  denials the plan would have paid to reverse anyway.
- **Improper-payment protection.** The cross-domain query (evidence §4) surfaces providers
  who pair a high denial rate with a fraud indicator - a prioritized payment-integrity work
  queue out of the box.
- **Quantified exposure.** ~$18.3M billed on the book, with **$3.14M concentrated in denied
  claims** feeding appeals/rework (evidence §5). The solution acts directly on that pool.
- **Scales the team, not the headcount.** Analysts self-serve governed answers in natural
  language; reps find precedent cases instantly; reviewers start with the highest-yield work.
