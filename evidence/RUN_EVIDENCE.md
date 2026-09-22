# Execution Evidence — real run output (readable as text)

> The FE Bar Build domain requires **evidence the build actually ran, committed as
> text** (query results, run logs, agent output) — not screenshots. Everything below
> was executed live against the governed schema and captured verbatim.

- **Workspace:** `fe-vm-hls-amer.cloud.databricks.com` (AWS)
- **Catalog / schema:** `hls_amer_catalog.` + `` `appeals-review` `` (schema name has a hyphen, so it is backticked)
- **Captured:** 2026-09-22
- **Data:** 100% synthetic. Code systems referenced (CARC denial codes, CPT/HCPCS, ICD-10, plan types, GLP-1 drug list) are real public taxonomies. No real customer data.

---

## 1. Lakeflow output — governed tables are populated

```sql
SELECT 'claims' AS tbl, COUNT(*) AS rows FROM hls_amer_catalog.`appeals-review`.claims
UNION ALL SELECT 'appeals', COUNT(*) FROM hls_amer_catalog.`appeals-review`.appeals
UNION ALL SELECT 'members', COUNT(*) FROM hls_amer_catalog.`appeals-review`.members
UNION ALL SELECT 'providers', COUNT(*) FROM hls_amer_catalog.`appeals-review`.providers
UNION ALL SELECT 'prior_authorizations', COUNT(*) FROM hls_amer_catalog.`appeals-review`.prior_authorizations
UNION ALL SELECT 'eligibility', COUNT(*) FROM hls_amer_catalog.`appeals-review`.eligibility
UNION ALL SELECT 'salesforce_cases', COUNT(*) FROM hls_amer_catalog.`appeals-review`.salesforce_cases
ORDER BY tbl;
```

| table | rows |
|---|---|
| appeals | 2,305 |
| claims | 33,500 |
| eligibility | 6,366 |
| members | 5,300 |
| prior_authorizations | 17,168 |
| providers | 510 |
| salesforce_cases | 121 |

---

## 2. Unity Catalog governance — declared PK/FK constraints (RELY) are live

```sql
SELECT tc.table_name, tc.constraint_type, tc.constraint_name
FROM hls_amer_catalog.information_schema.table_constraints tc
WHERE tc.table_schema = 'appeals-review'
ORDER BY tc.table_name, tc.constraint_type;
```

Returned **6 PRIMARY KEY + 14 FOREIGN KEY** constraints:

| table | type | constraint |
|---|---|---|
| appeals | PRIMARY KEY | appeals_pk |
| appeals | FOREIGN KEY | appeals_member_fk, appeals_provider_fk, appeals_claim_fk, appeals_pa_fk |
| claims | PRIMARY KEY | claims_pk |
| claims | FOREIGN KEY | claims_member_fk, claims_provider_fk, claims_pa_fk |
| eligibility | PRIMARY KEY | eligibility_pk |
| eligibility | FOREIGN KEY | eligibility_member_fk |
| fraud_reference | FOREIGN KEY | fraud_claim_fk |
| members | PRIMARY KEY | members_pk |
| prior_authorizations | PRIMARY KEY | prior_authorizations_pk |
| prior_authorizations | FOREIGN KEY | pa_member_fk, pa_provider_fk |
| providers | PRIMARY KEY | providers_pk |
| salesforce_cases | FOREIGN KEY | sfcase_member_fk, sfcase_claim_fk, sfcase_provider_fk |

These are declared `RELY` (zero orphan rows verified), so both the optimizer and Genie
trust them for join inference. This is the backbone of the semantic ontology.

---

## 3. Certified metric view — appeal overturn rate by original denial reason

```sql
SELECT `Original Denial Reason`,
       MEASURE(`Appeal Count`) AS appeals,
       ROUND(MEASURE(`Overturn Rate`), 3) AS overturn_rate
FROM hls_amer_catalog.`appeals-review`.appeals_metrics
GROUP BY `Original Denial Reason`
ORDER BY overturn_rate DESC;
```

Top rows (of 21):

| Original Denial Reason | appeals | overturn_rate |
|---|---|---|
| Formulary exclusion | 13 | 0.462 |
| Experimental/investigational | 26 | 0.346 |
| Quantity limit exceeded | 3 | 0.333 |
| Step therapy requirement not met | 50 | 0.280 |
| Service not covered under plan | 265 | 0.272 |
| Not medically necessary | 287 | 0.251 |
| Member not active at time of service | 120 | 0.250 |
| Prior authorization not obtained | 323 | 0.238 |
| Exceeds benefit limit | 127 | 0.213 |
| Coding error | 98 | 0.204 |
| Provider not in network | 44 | 0.136 |

**Business read:** the two highest-volume denial reasons — *Prior authorization not
obtained* (323 appeals) and *Not medically necessary* (287 appeals) — are overturned
~24–25% of the time. Roughly one in four denials on those grounds is reversed on appeal,
which is rework the plan is paying for twice.

---

## 4. Cross-domain query — high-denial providers that also appear in the fraud reference

This is the "ontology moment": Genie/SQL joins the certified `provider_risk_metrics`
(Denial Rate) to `claims → fraud_reference` through the declared FK graph.

```sql
WITH pdr AS (
  SELECT `Provider ID`, `Provider Name`, `Specialty`, MEASURE(`Denial Rate`) AS denial_rate
  FROM hls_amer_catalog.`appeals-review`.provider_risk_metrics GROUP BY ALL),
fp AS (
  SELECT DISTINCT c.provider_id, f.fraud_type
  FROM hls_amer_catalog.`appeals-review`.claims c
  JOIN hls_amer_catalog.`appeals-review`.fraud_reference f ON c.claim_id = f.claim_id)
SELECT pdr.`Provider Name`, pdr.`Specialty`, ROUND(pdr.denial_rate,3) AS denial_rate, fp.fraud_type
FROM pdr JOIN fp ON pdr.`Provider ID` = fp.provider_id
ORDER BY pdr.denial_rate DESC
LIMIT 15;
```

Top rows:

| Provider Name | Specialty | denial_rate | fraud_type |
|---|---|---|---|
| Dr. Laura Hawkins MD | | 0.339 | Kickback indicator |
| Long Ltd | | 0.333 | Phantom services |
| Gonzalez Inc | | 0.300 | Procedure upcoding |
| Dr. Richard Lynch | Pathology | 0.298 | Duplicate billing |
| Dr. David Kim | Endocrinology | 0.278 | Diagnosis upcoding for coverage |
| Dr. David Kim | Endocrinology | 0.278 | GLP-1 phantom claim |
| Dr. David Kim | Endocrinology | 0.278 | Telehealth prescription mill |
| Dr. Elizabeth Kirk | Primary Care | 0.277 | Procedure upcoding |
| Dr. Elizabeth Kirk | Primary Care | 0.277 | GLP-1 phantom claim |
| Dr. Dalton Bradshaw | Primary Care | 0.271 | Diagnosis upcoding for coverage |

**Business read:** these providers combine an elevated denial rate with one or more
fraud indicators — the exact population a payment-integrity team should route to review
first. Endocrinology + "GLP-1 phantom claim" / "compounded semaglutide billing" reflects
the current GLP-1 utilization pressure.

---

## 5. Dollar exposure by claim status — quantified value anchor

```sql
SELECT status, COUNT(*) AS claims,
       ROUND(SUM(billed_amount)) AS total_billed,
       ROUND(SUM(paid_amount)) AS total_paid
FROM hls_amer_catalog.`appeals-review`.claims
GROUP BY status ORDER BY total_billed DESC;
```

| status | claims | total_billed | total_paid |
|---|---|---|---|
| Paid | 23,117 | $12,496,745 | $9,247,058 |
| Denied | 5,284 | $3,135,891 | (none) |
| Pending | 3,372 | $1,778,298 | (none) |
| Partially Paid | 1,727 | $912,131 | $329,532 |

**Business read:** ~$18.3M billed across the book; **$3.14M sits in denied claims** that
feed the appeals/rework pipeline, plus $1.78M pending. Cutting appeal-handling time and
preventing avoidable denials acts directly on that $3.14M.

---

## 6. Genie agent — live natural-language → certified SQL → grounded answer

Genie space: **Payer Integrity Ontology — Genie One** (`01f1975b29131726afea626d5ebabac3`).
Question asked via the Genie Conversation API:

> *"What is our appeal overturn rate by original denial reason, and which reasons are we
> losing most often?"*

**SQL Genie generated (unedited)** — note it selected the governed metric view and
`MEASURE()`, not an ad-hoc `AVG()`:

```sql
SELECT `Original Denial Reason`,
  MEASURE(`Appeal Count`) AS `appeal_count`,
  MEASURE(`Overturned Count`) AS `overturned_count`,
  MEASURE(`Appeal Count`) - MEASURE(`Overturned Count`) AS `lost_count`,
  try_divide(100.0 * MEASURE(`Overturned Count`), NULLIF(MEASURE(`Appeal Count`), 0)) AS `overturn_rate`
FROM `hls_amer_catalog`.`appeals-review`.`appeals_metrics`
WHERE `Original Denial Reason` IS NOT NULL
GROUP BY ALL
ORDER BY `lost_count` DESC, `appeal_count` DESC, `Original Denial Reason` ASC;
```

**Genie's natural-language answer (unedited):**

> Across the **21 denial reasons** shown, the reasons you are losing most often are led by
> **Prior authorization not obtained** with **246** lost appeals and a **23.8%** overturn
> rate, followed by **Not medically necessary** with **215** losses and a **25.1%**
> overturn rate, and **Service not covered under plan** with **193** losses and a **27.2%**
> overturn rate. ... Among these high-loss reasons, overturn rates are mostly in the
> **18%–27%** range, while the lowest overturn rate overall is **Provider not in network**
> at **13.6%**.

`status: COMPLETED`, `row_count: 21`, `conversation_id: 01f1b6deb80d1d45b5872802e551fec8`.

This is the whole point of the ontology: a business user asks in plain English and Genie
reasons over the certified metric layer + declared relationships to return a governed,
traceable answer.

---

## How the layers connect (why this is one journey, not six silos)

1. **Lakeflow** generates + ingests the synthetic payer data into the tables counted in §1.
2. **Unity Catalog** governs those exact tables with the PK/FK graph in §2 and the certified
   metric views queried in §3–§4.
3. **Lakebase** serves the case narratives operationally for sub-second member-services
   search (see `03_lakebase_serving/` evidence).
4. **Gen AI (MAS)** and the **Genie agent** in §6 answer over the *same* governed metrics.
5. The **Databricks App** calls the same SQL (dashboard) and proxies chat to the agent.

Every layer reads or writes the one governed schema — that shared schema is the join.
