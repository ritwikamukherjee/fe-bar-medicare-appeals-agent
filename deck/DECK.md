---
title: Medicare Appeals Triage Agent
subtitle: Cutting overturn-driven rework and speeding appeals triage for a managed-care payer
audience: Executive sponsor (VP Claims Ops) + Technical owner (Data/Platform lead)
---

# Medicare Appeals Triage Agent
### One governed answer per appeal - in seconds, not minutes

A payer-integrity build on Databricks for a Medicare Advantage / Medicaid health plan.
*(Synthetic data; real public code taxonomies.)*

---

## Slide 1 - The business problem

**Whose problem: the VP of Claims Operations.** Their scorecard is the appeal-overturn rate,
appeal cycle time against CMS clocks, and administrative cost per claim.

**Denied-claim appeals are expensive, slow, and repetitive.**

- Case workers hop across systems to triage one appeal: eligibility, denial reason,
  provider history, clinical evidence.
- Regulated **CMS turnaround clocks** are ticking the whole time.
- A large share of denials are **overturned on appeal** - the plan adjudicates and pays
  for the same claim twice, driving up cost per claim.

> VP of Claims Operations: administrative cost per claim, overturn rate, CMS compliance.
> CFO: the denied-dollar exposure and leakage roll into medical loss ratio (MLR).
> Chief Medical Officer: owns the "not medically necessary" overturns.

---

## Slide 2 - The stakes, quantified

On the book of business analyzed (executed live):

| Metric | Value |
|---|---|
| Total billed | **~$18.3M** |
| **Denied claims feeding appeals/rework** | **$3.14M** (5,284 claims) |
| Overturn rate on top-2 denial reasons | **~24-25%** (Prior-auth-not-obtained: 323 appeals; Not-medically-necessary: 287) |
| Pending claims exposure | $1.78M |

**One in four** denials on the highest-volume reasons is reversed later. That $3.14M and the
leakage behind it roll straight into the **CFO's medical loss ratio**; the overturn rate and
double-adjudication land on the **VP of Claims Operations'** scorecard. That is what we move.

---

## Slide 3 - The solution: one connected data journey

```
raw synthetic payer data
  → Lakeflow (ingest)
  → Unity Catalog (govern: 6 PK + 14 FK, 8 certified metric views, synonyms)
  → Lakebase (operational hybrid search over case narratives)
  → Gen AI Multi-Agent Supervisor  +  Genie agent (NL → certified SQL)
  → Databricks App (dashboard + chat)
```

**Every layer reads the same governed schema.** The dashboard, the Genie agent, and the
supervisor all speak one set of certified definitions - no drift, fully traceable.

---

## Slide 4 - What a case worker actually gets

- **Ask in plain English:** "overturn rate by denial reason?" → governed answer with the
  certified metric, in seconds (live Genie trace in the repo).
- **Triage one case:** a member/claim brief that pulls eligibility + claims + denials +
  appeals + prior auth into one dossier.
- **Find precedent fast:** Lakebase hybrid search over free-text case narratives when a
  member calls about a denial.
- **Prioritize risk:** one query surfaces providers with a high denial rate **and** a fraud
  flag (e.g. Endocrinology + "GLP-1 phantom claim").

---

## Slide 5 - Proof it runs (not a mockup)

Committed as text in the repo's `evidence/`:

- Governed tables populated: **33,500 claims / 2,305 appeals / 5,300 members**.
- **6 PK + 14 FK** constraints live (RELY) - the join graph the agent trusts.
- Certified-metric overturn rates by denial reason.
- Cross-domain provider-denial × fraud join.
- A **live Genie NL → `MEASURE()` SQL → grounded answer** trace.

---

## Slide 6 - Business outcomes (mapped to who owns them)

- **Admin cost per claim (VP Claims Ops):** triage minutes → seconds, faster appeal cycle time.
- **Overturn rate (VP Claims Ops):** cut the ~24-25% overturn reasons to stop paying twice.
- **Medical loss ratio (CFO):** cut improper-payment leakage and avoidable spend from the
  $3.14M denied-claim pool.
- **Medical-necessity defensibility (CMO):** clinical evidence attached to appeals.
- **Scales the team, not headcount:** analysts self-serve; reviewers start highest-yield.

*Every number on slide 2 maps to a metric a named executive is compensated on.*

---

## Slide 7 - For the technical stakeholder

- **Governance-first:** certified metric views + declared RELY keys → reproducible,
  optimizer- and Genie-trusted joins. No ad-hoc KPI drift.
- **Right engine per job:** analytics on the lakehouse; OLTP hybrid search on Lakebase.
- **Resilient Gen AI:** code-based supervisor isolates each MCP tool (try/except) so a flaky
  external server degrades gracefully instead of failing the endpoint.
- **Auth:** app runs dual-mode (service principal / on-behalf-of user); per-request Lakebase
  OAuth credential.

---

## Slide 8 - Roadmap

- **Overturn-likelihood model** (MLflow + Model Serving): score each open appeal, surface it
  in the dashboard, feed reviewer prioritization. The certified feature layer already exists.
- Restore Part D + PubMed MCP tools on the resilient supervisor.
- Materialize heavy metric views; publish a business glossary linked to the metrics.

---

## Slide 9 - The ask

Green-light a scoped pilot on one line of business:

1. Point Lakeflow at a de-identified extract.
2. Stand up the app for a triage pod.
3. Measure the VP's metrics over one quarter: administrative cost per claim, appeal cycle
   time, and overturn rate - with the MLR impact of cut leakage reported to the CFO.

**Low incremental cost - it reuses the governed lakehouse you already own.**
