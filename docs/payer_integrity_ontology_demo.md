# Payer Integrity Ontology — Genie One Demo

**Workspace:** `fe-vm-hls-amer.cloud.databricks.com`
**Catalog / schema:** `hls_amer_catalog.appeals-review`
**Genie space:** [Payer Integrity Ontology — Genie One](https://fe-vm-hls-amer.cloud.databricks.com/genie/rooms/01f1975b29131726afea626d5ebabac3) (`space_id 01f1975b29131726afea626d5ebabac3`)
**Built:** 2026-08-13

---

## The story you're telling

> "We didn't just point Genie at some tables. We built a **semantic ontology** over the payer domain — entities, relationships, certified business metrics, synonyms, and business domains — and now a business user can ask a plain-English question and Genie reasons over that knowledge graph: it picks the certified metric, follows the right relationships between claims, providers, appeals, and members, and returns a grounded, traceable answer."

An "ontology" here = three stacked layers on top of the raw star schema:

| Layer | What it is | What we did |
|---|---|---|
| **1. Business semantics** (UC, GA) | Entities + declared PK/FK relationships + certified metric views + synonyms | 6 PKs, 14 RELY foreign keys, 8 certified metric views, 24 enriched column comments w/ synonyms |
| **2. Genie Ontology** (Preview) | Auto-built knowledge graph that grounds Genie answers by ranking authoritative "snippets" | Genie consumes the semantics + metric views + comments automatically |
| **3. Domains** (Preview) | Governed-tag business areas for Discover / Genie One browsing | 6 payer domains tagged onto 19 assets (via `payer_domain` tag — see "Governed Domains" note) |

---

## The entity–relationship graph (what Genie now navigates)

```
members ──< eligibility
   │
   ├──< claims >── providers ──< prior_authorizations
   │       │  │                        │
   │       │  └──< fraud_reference     │
   │       │                           │
   └──< appeals >──────────────────────┘   (appeal targets a claim OR a PA)
           │
   salesforce_cases (member / claim / provider)
```

All 14 foreign keys are declared `RELY` (zero orphan rows verified), so Genie and the optimizer trust them for join inference.

## The 6 business domains

| Domain | Core tables | Certified metric views |
|---|---|---|
| **Claims Operations** | `claims` | `claim_denials_metrics`, `pbi_claims_metrics` |
| **Appeals & Grievances** | `appeals` | `appeals_metrics`, `pbi_appeals_metrics` |
| **Prior Authorization & UM** | `prior_authorizations` | (feeds `glp1_utilization_metrics`) |
| **Pharmacy & GLP-1** | `cms_drug_spending` | `glp1_utilization_metrics` |
| **Provider Network Integrity** | `providers`, `fraud_reference` | `provider_risk_metrics`, `fraud_exposure_metrics` ⟵ *new* |
| **Member Eligibility & Cases** | `members`, `eligibility`, `salesforce_cases`, `state_eligibility_corroboration` | `eligibility_coverage_metrics` ⟵ *new* |

---

## Demo runbook — questions to ask, and the "ontology moment" each shows

Ask these in the Genie space in order. Each is chosen to make a specific ontology capability visible.

### Warm-up (single certified metric)
1. **"What is our appeal overturn rate by original denial reason, and which reasons are we losing most often?"**
   → Uses the certified `Overturn Rate` measure from `appeals_metrics`. Point out Genie chose the *governed* definition, not an ad-hoc `AVG()`.

2. **"What's the total billed vs paid amount for denied claims by service type?"**
   → `claim_denials_metrics`. Certified dollar measures.

### Relationship traversal (the star of the show)
3. **"Which providers have the highest denial rates and also appear in the fraud reference? Show specialty and fraud type."**
   → *Cross-domain.* Genie joins `provider_risk_metrics` (Denial Rate) to `claims → fraud_reference` via the declared FK graph. **This is the money demo** — it works today (validated).

4. **"Show members who had claims processed while their coverage was inactive."**
   → Uses the `was_member_active` flag / `eligibility` relationship. Payment-integrity narrative.

5. **"For each appeal, what was the original claim's denial category, and how often is each category overturned?"**
   → Traverses `appeals → claims` (FK), grounded by the `denial_category` comment.

### Pharmacy / GLP-1 economics (cross-domain)
6. **"For GLP-1 drugs, what are the prior-authorization approval rates by drug and specialty?"**
   → `glp1_utilization_metrics` (filtered to the GLP-1 drug list, joins PA→claims→providers).

7. **"How does GLP-1 prior-auth denial volume compare to CMS Part D spending for the same drugs?"**
   → Bridges `glp1_utilization_metrics` and `cms_drug_spending` (reference data).

### Provider integrity $ exposure
8. **"What is the total dollar exposure from flagged (suspected fraud) claims, broken down by fraud type?"**
   → `fraud_exposure_metrics` (new certified view; `Flagged Billed`/`Flagged Paid`).

9. **"Which specialties have the most suspected-fraud claims and the highest flagged dollars?"**
   → Same view, sliced by specialty.

### Appeals operations
10. **"How many appeals were filed by providers versus members, and what is each group's overturn rate?"**
    → `appeals_metrics` by `Appeal Source` — shows the synonym mapping (appellant / filed by).

11. **"What share of appeals had supporting documentation, and are documented appeals overturned more often?"**
    → `has_documentation` grounded by comment.

### Member / eligibility
12. **"How many active members do we have by plan type (line of business) and state?"**
    → `eligibility_coverage_metrics`. Say "LOB" or "line of business" out loud — the synonym resolves to `plan_type`.

13. **"How many open Provider Claim Inquiry (PCI) cases do we have by line of business?"**
    → `salesforce_cases` grounded by the `case_type` comment (PCI = Provider Claim Inquiry).

### Synonym / grounding flex (optional)
14. **"What's our claim rejection rate for Medicare Advantage members?"**
    → "rejection" → denial, "Medicare Advantage / MA" → `plan_type`. Shows business-language grounding.

---

## One-time UI setup (API can't set these — paste in the Genie space)

The public Genie API creates the space, tables, and sample questions (done). **General Instructions** and **trusted example SQL** are UI-only today. Open the space → **Settings / Instructions** and paste the block below.

### General Instructions (paste verbatim)

```
You are the Payer Integrity analyst for a US health plan. The data covers claims,
prior authorizations, appeals, members, providers, eligibility, Salesforce cases,
CMS Part D drug spend, and a fraud reference list.

ALWAYS prefer the certified metric views over raw tables when a question maps to a KPI:
- Appeals KPIs (counts, overturn rate) -> appeals_metrics
- Claim denial KPIs ($ and counts) -> claim_denials_metrics
- Provider risk (denial rate, billed-to-paid, inactive-member claims) -> provider_risk_metrics
- GLP-1 utilization (PA approval rate, spend) -> glp1_utilization_metrics
- Suspected-fraud dollar exposure -> fraud_exposure_metrics
- Member coverage counts -> eligibility_coverage_metrics
Query metric views with MEASURE(<measure name>).

Key relationships (declared foreign keys): claims/PAs belong to a member and a provider;
an appeal targets EITHER a claim OR a prior authorization (one of claim_id/prior_auth_id
is null); fraud_reference and salesforce_cases link by claim_id/provider_id/member_id.

Business definitions & synonyms:
- Overturn / reversed / won appeal / favorable outcome = is_overturned = true.
- Denial / rejection = a claim/PA that was not approved (claims.status='Denied', PA.is_approved=false).
- Denial category = the high-level bucket (Authorization, Coverage, Eligibility, Documentation,
  Coding, Duplicate, Benefit Limit, Step Therapy, Formulary).
- LOB / line of business / coverage type = plan_type (Commercial, Medicare Advantage (MA),
  Medicare Original, Medicaid, CHIP).
- Inactive-member claim = a claim where was_member_active = false (payment-integrity risk).
- Flagged / suspected fraud = a claim_id present in fraud_reference.
- GLP-1 drugs = Ozempic, Wegovy, Mounjaro, Zepbound, Rybelsus, Trulicity, Victoza, Saxenda, Byetta.
- PCI = Provider Claim Inquiry; CIR = Claim Information Request (salesforce_cases.case_type).

When a question spans domains (e.g., provider risk + fraud, appeals + original denial reason),
join through the declared keys rather than guessing.
```

### Trusted example SQL (add 2–3 in the "SQL examples" / "Instructions" section)

**Q: Providers with highest denial rates that also appear in the fraud reference**
```sql
WITH pdr AS (
  SELECT `Provider ID`, `Provider Name`, `Specialty`, MEASURE(`Denial Rate`) AS denial_rate
  FROM hls_amer_catalog.`appeals-review`.provider_risk_metrics GROUP BY ALL),
fp AS (
  SELECT DISTINCT c.provider_id, f.fraud_type
  FROM hls_amer_catalog.`appeals-review`.claims c
  JOIN hls_amer_catalog.`appeals-review`.fraud_reference f ON c.claim_id = f.claim_id)
SELECT pdr.`Provider Name`, pdr.`Specialty`, pdr.denial_rate, fp.fraud_type
FROM pdr JOIN fp ON pdr.`Provider ID` = fp.provider_id
ORDER BY pdr.denial_rate DESC;
```

**Q: Appeal overturn rate by original denial reason**
```sql
SELECT `Original Denial Reason`, MEASURE(`Appeal Count`) AS appeals,
       MEASURE(`Overturn Rate`) AS overturn_rate
FROM hls_amer_catalog.`appeals-review`.appeals_metrics
GROUP BY `Original Denial Reason` ORDER BY overturn_rate DESC;
```

**Q: Claims paid while member coverage was inactive**
```sql
SELECT c.claim_id, c.member_id, c.service_date, c.paid_amount, c.status
FROM hls_amer_catalog.`appeals-review`.claims c
WHERE c.was_member_active = false AND c.paid_amount > 0
ORDER BY c.paid_amount DESC;
```

---

## Follow-ups / optional upgrades

1. **Promote to governed Domains (needs account admin).** Domains in Discover key off the
   governed `domain` tag, whose allowed values are currently `[finance, sales, supply_chain,
   quality, hr, operations]`. We tagged assets with a custom `payer_domain` tag instead (no
   admin rights). To light up the formal Discover "Domain" cards, an account admin should add
   these values to the `domain` tag policy and we re-tag with `domain`:
   `claims_operations, appeals_grievances, prior_auth_um, pharmacy_glp1, provider_integrity, member_eligibility`.
   (Tag-policy update API: `PATCH /api/2.1/tag-policies`, or Terraform `databricks_tag_policy`.)

2. **Business Glossary Pages** (preview "coming soon") — when enabled, publish the definitions
   above as glossary Pages linked to each metric view so Genie cites canonical term definitions.

3. **Materialize the heavy metric views** (`provider_risk_metrics`, `glp1_utilization_metrics`)
   for interactive latency once the demo scales.

4. **Existing narrow spaces** (Prior Auth, Claims Ops, Provider 360, Payer CFO, State Regulatory)
   were left intact per your call. This unified space sits alongside them.
```
```

## What was changed in the workspace (for cleanup / audit)

- **Constraints:** 6 PRIMARY KEY + 14 FOREIGN KEY (RELY) on `appeals-review` tables.
- **New metric views:** `fraud_exposure_metrics`, `eligibility_coverage_metrics`.
- **Column comments:** 24 business columns enriched with definitions + synonyms.
- **Tags:** `payer_domain` on 19 assets, `subject_area='Payer Integrity'`, `certified='true'` on 8 metric views.
- **Genie space:** `Payer Integrity Ontology — Genie One` (`01f1975b29131726afea626d5ebabac3`).
- **Local config:** refreshed the stale `DEFAULT` profile token in `~/.databrickscfg` (it already pointed at this host) so the Databricks MCP tools could authenticate.
