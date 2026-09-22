# Layer 1 — Lakeflow ingest

Generates and ingests the synthetic payer dataset into the governed schema
`hls_amer_catalog.`​`` `appeals-review` ``. This is the raw-data start of the journey.

## Contents
- [`generate_healthcare_data.py`](generate_healthcare_data.py) — synthetic data generator
  (members, providers, claims, prior_authorizations, eligibility, appeals, salesforce_cases,
  fraud_reference) using real public code taxonomies (CARC, CPT/HCPCS, ICD-10, plan types).
- [`create_tables.sql`](create_tables.sql) — table DDL for the star schema.
- [`refresh_volume_notebook.py`](refresh_volume_notebook.py) — refresh raw files in the UC Volume.

## Proof it ran
Row counts captured live in [`../evidence/RUN_EVIDENCE.md`](../evidence/RUN_EVIDENCE.md) §1:
33,500 claims · 17,168 prior auths · 6,366 eligibility · 5,300 members · 2,305 appeals ·
510 providers · 121 Salesforce cases.

## Connects to
**Down:** these tables are governed in `02_unity_catalog_governance/` (PK/FK + metric views),
then consumed by every layer above.
