# Layer 5 — Genie agent (natural language over the governed schema)

Lets a business user ask in plain English and get a governed, traceable answer. Genie grounds
on the certified metric views + declared relationships from `02_unity_catalog_governance/`.

- **Genie space:** *Payer Integrity Ontology — Genie One* (`space_id 01f1975b29131726afea626d5ebabac3`)
- **Live proof:** [`../evidence/RUN_EVIDENCE.md`](../evidence/RUN_EVIDENCE.md) §6 — a real
  NL question returning `MEASURE()`-based SQL over `appeals_metrics` plus a grounded summary.

## Configuration

- [`general_instructions.txt`](general_instructions.txt) — the space's General Instructions:
  which metric view to prefer per question type, the key relationships, and the business
  synonym dictionary (overturn/reversed, LOB→plan_type, flagged fraud, GLP-1 drug list, PCI/CIR).
- [`trusted_example_sql.sql`](trusted_example_sql.sql) — trusted example queries that steer
  Genie toward governed patterns (overturn rate by denial reason; providers with high denial
  rate that appear in the fraud reference; claims paid while a member was inactive).
- Full runbook (entity graph, 14-question demo script, setup): [`../docs/payer_integrity_ontology_demo.md`](../docs/payer_integrity_ontology_demo.md).

## Connects to
- **Up:** reads the certified metrics + PK/FK graph in `02_unity_catalog_governance/`.
- **Sideways:** the Gen AI supervisor (`04_genai_agent/`) calls this space as its
  `appeals_data_worker` tool for aggregate/trend questions.
- **Down:** the app (`06_databricks_app/`) exposes it in the chat panel.
