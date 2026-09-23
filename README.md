# Medicare Appeals Triage Agent - an end-to-end payer-integrity build

**Industry:** Healthcare payer (Medicare Advantage / Medicaid managed care)
**Metric owner (the buyer):** the **VP of Claims Operations**, whose scorecard is the
appeal-overturn rate, appeal cycle time against CMS clocks, and administrative cost per claim.
The denied-dollar exposure rolls up to the **CFO's medical loss ratio (MLR)**, and the
"not medically necessary" overturns sit on the **Chief Medical Officer's** clinical-policy scorecard.
**Customer problem:** This VP's claims-operations team is buried in denied-claim appeals and
grievances. Case workers hop between systems to answer one question - *is this member
eligible, why was the claim denied, has this provider been flagged, what does the evidence
say?* - while the plan pays twice for denials that get overturned on appeal, driving up the
VP's cost-per-claim and hurting the overturn rate they are measured on.

## The business outcome (read this first)

This build gives a case worker one place to triage an appeal and get a governed answer in
seconds instead of a multi-system, multi-minute hunt. On the synthetic book of business
used here (executed live, see [`evidence/RUN_EVIDENCE.md`](evidence/RUN_EVIDENCE.md)):

- **$3.14M** sits in **5,284 denied claims** that feed the appeals/rework pipeline (out of
  ~$18.3M billed). Appeals handling and avoidable denials act directly on that number.
- The two highest-volume denial reasons - *Prior authorization not obtained* (323 appeals)
  and *Not medically necessary* (287 appeals) - are **overturned ~24-25%** of the time.
  One in four of those denials is reversed later: rework the plan pays for twice.
- A single cross-domain query surfaces **providers who combine a high denial rate with a
  fraud indicator** (e.g. Endocrinology + "GLP-1 phantom claim") - the exact population a
  payment-integrity team should review first.

**Value framing.** For a plan handling tens of thousands of appeals a year, compressing
per-case triage from minutes to seconds and steering reviewers to the highest-yield denial
reasons and providers moves the exact metrics these executives are compensated on: the
**VP of Claims Operations'** administrative cost per claim and overturn rate, and the
**CFO's medical loss ratio** (via cut improper-payment leakage and avoidable medical spend) -
while improving the member and provider experience against regulated CMS turnaround clocks.

## The data journey - one connected pipeline, six Databricks layers

```
 raw synthetic payer data
        │  (Faker/PySpark generation)
        ▼
┌──────────────────────┐   01_lakeflow_ingest/
│ 1. LAKEFLOW           │   ingest members, providers, claims, prior_auths,
│    ingest             │   eligibility, appeals, salesforce_cases, fraud_reference
└─────────┬────────────┘
          ▼
┌──────────────────────┐   02_unity_catalog_governance/
│ 2. UNITY CATALOG      │   6 PK + 14 FK (RELY), 8 certified metric views,
│    govern             │   enriched column comments + synonyms, domain tags
└─────────┬────────────┘
          ├───────────────────────────────┐
          ▼                                ▼
┌──────────────────────┐        ┌──────────────────────┐
│ 3. LAKEBASE           │        │ 4. GEN AI (MAS)       │  04_genai_agent/
│    operational serving│        │    make it intelligent│  Multi-Agent Supervisor:
│  03_lakebase_serving/ │        │  Genie + UC functions │  routes to the right tool,
│  managed Postgres +   │        │  + ClinicalTrials MCP │  synthesizes one answer
│  pgvector hybrid      │        └──────────┬───────────┘
│  search over case     │                   ▼
│  narratives           │        ┌──────────────────────┐  05_genie_agent/
└─────────┬────────────┘        │ 5. GENIE AGENT        │  NL → certified-metric SQL
          │                     │    natural language   │  over the SAME governed schema
          │                     └──────────┬───────────┘
          └───────────────┬─────────────────┘
                          ▼
                ┌──────────────────────┐   06_databricks_app/
                │ 6. DATABRICKS APP     │   React + FastAPI: ops dashboard (SQL) +
                │    surface to business│   chat panel (proxies to the MAS agent)
                └──────────────────────┘
```

**Why this is one journey and not six demos:** every layer reads or writes **the one
governed schema** `hls_amer_catalog.`​`` `appeals-review` ``. Lakeflow lands the tables;
Unity Catalog governs them with the PK/FK graph and certified metric views; Lakebase serves
the case narratives operationally; the Gen AI supervisor and the Genie agent both answer
over the *same* certified metrics; the app calls the same SQL and proxies chat to the agent.
That shared, governed schema is the join between the layers.

## Repository map

| Path | Layer | What's here |
|---|---|---|
| [`01_lakeflow_ingest/`](01_lakeflow_ingest/) | Lakeflow | Synthetic data generator + table-creation pipeline |
| [`02_unity_catalog_governance/`](02_unity_catalog_governance/) | Unity Catalog | Constraints, certified metric views, comments/synonyms, tags |
| [`03_lakebase_serving/`](03_lakebase_serving/) | Lakebase | Managed Postgres + pgvector/BM25 hybrid search over case narratives, own app. Deployed live in `fe-vm-hls-amer` (project `healthplan-appeals`); see [`DEPLOY_FE_VM.md`](03_lakebase_serving/DEPLOY_FE_VM.md) |
| [`04_genai_agent/`](04_genai_agent/) | Gen AI | Code-based Multi-Agent Supervisor (Genie + UC functions + MCP) |
| [`05_genie_agent/`](05_genie_agent/) | Genie | Genie space config: general instructions, synonyms, trusted SQL |
| [`06_databricks_app/`](06_databricks_app/) | App | React + FastAPI Databricks App (dashboard + chat) |
| [`07_ml_overturn_model/`](07_ml_overturn_model/) | ML | Trained + served overturn-likelihood model (MLflow -> Unity Catalog -> Model Serving) feeding a reviewer-prioritization score |
| [`evidence/`](evidence/) | - | **Real run output committed as text** (query results, constraints, Genie trace, Lakebase search, ML metrics) |
| [`deck/`](deck/) | - | Business presentation (outcome-led) |
| [`docs/`](docs/) | - | Architecture, ontology runbook, decisions & trade-offs |

## Proof it runs

Live output captured 2026-09-22 against `fe-vm-hls-amer`:
- [`evidence/RUN_EVIDENCE.md`](evidence/RUN_EVIDENCE.md) - table row counts, the 6+14
  constraint listing, the certified-metric overturn-rate result, the cross-domain
  provider-fraud join, dollar exposure, and a live Genie NL to SQL to answer trace.
- [`evidence/LAKEBASE_DEPLOYMENT.md`](evidence/LAKEBASE_DEPLOYMENT.md) - the Lakebase layer
  provisioned and seeded in `fe-vm-hls-amer` (800 cases + embeddings), with vector, BM25,
  and hybrid search all validated OK.
- [`evidence/ML_MODEL.md`](evidence/ML_MODEL.md) - the overturn-likelihood model trained with
  MLflow, registered in Unity Catalog, scored across all appeals, and served on Model Serving
  (AUC reported honestly; the value is the end-to-end MLOps pattern and the prioritization).

## Data & compliance

100% synthetic data. The code systems referenced (CARC denial codes, CPT/HCPCS, ICD-10,
plan types, GLP-1 drug list) are real public taxonomies. No real customer data is included.
