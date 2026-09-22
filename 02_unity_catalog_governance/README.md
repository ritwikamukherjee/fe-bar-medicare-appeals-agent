# Layer 2 — Unity Catalog governance

Governs the tables that Lakeflow lands (`01_lakeflow_ingest/`) and feeds every downstream
layer. This is the **semantic ontology**: relationships + certified metrics + business
language, all in Unity Catalog.

## What's declared here

**1. Primary/foreign keys (RELY).** 6 PK + 14 FK, declared `RELY` (zero orphan rows verified),
so Genie and the optimizer trust them for join inference. Confirmed live in
[`../evidence/RUN_EVIDENCE.md`](../evidence/RUN_EVIDENCE.md) §2. Graph:

```
members ──< eligibility
   ├──< claims >── providers ──< prior_authorizations
   │       └──< fraud_reference
   └──< appeals >── (targets a claim OR a prior_authorization)
   salesforce_cases ── (member / claim / provider)
```

**2. Certified metric views (8).** Queried with `MEASURE(...)`; preferred over raw tables for
all KPIs:

| Metric view | Key measures |
|---|---|
| `appeals_metrics` | Appeal Count, Overturned Count, Overturn Rate (by Original Denial Reason, Appeal Source) |
| `claim_denials_metrics` | Total Billed, Total Paid (by service type) |
| `provider_risk_metrics` | Denial Rate, Billed-to-Paid, inactive-member claims |
| `fraud_exposure_metrics` | Flagged Billed, Flagged Paid (by fraud type) |
| `glp1_utilization_metrics` | PA Approval Rate, spend (GLP-1 drug list) |
| `eligibility_coverage_metrics` | Active members by plan type / state |
| `pbi_appeals_metrics`, `pbi_claims_metrics` | Power BI-facing rollups |

**3. Enriched column comments + synonyms.** 24 business columns carry definitions and
synonyms so natural language resolves to the right column (e.g. "LOB" / "line of business" →
`plan_type`; "overturn" / "reversed" → `is_overturned = true`; "flagged / suspected fraud" →
`claim_id` in `fraud_reference`). Full list in [`../docs/payer_integrity_ontology_demo.md`](../docs/payer_integrity_ontology_demo.md).

**4. Domain tags.** 6 payer domains (Claims Operations, Appeals & Grievances, Prior Auth & UM,
Pharmacy & GLP-1, Provider Network Integrity, Member Eligibility & Cases) tagged across 19
assets; `certified='true'` on the 8 metric views.

**5. Governed reconciliation view.** `state_eligibility_corroboration` reconciles internal
coverage against the WA HCA state eligibility file and labels each member
`concur_active` / `concur_inactive` / `discrepancy_*` / `missing_from_state`. Real definition
in [`state_eligibility_corroboration.sql`](state_eligibility_corroboration.sql).

## Connects to
- **Up:** consumes the tables from `01_lakeflow_ingest/`.
- **Down:** the Genie agent (`05_genie_agent/`), the Gen AI supervisor (`04_genai_agent/`),
  and the app dashboard (`06_databricks_app/`) all read these certified metrics — the shared
  governed layer that keeps every answer consistent.
