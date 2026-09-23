# Execution Evidence, Lakebase layer live in `fe-vm-hls-amer`

The Lakebase operational-serving layer (layer 3) was deployed into the same AWS workspace
as the rest of the build so all six layers share one workspace and catalog. Captured
2026-09-22. Data is 100% synthetic.

## What was provisioned
- **Lakebase Autoscale project:** `projects/healthplan-appeals` (Postgres 17), branch
  `production`, endpoint `primary` (READ_WRITE, host `ep-lucky-mountain-d2hc68ic.database.us-east-1.cloud.databricks.com`)
- **UC source tables:** `hls_amer_catalog.healthplan_appeals.cases` (800 rows) and
  `hls_amer_catalog.healthplan_appeals.plans` (10 rows), loaded from the synthetic CSVs
- **Embedding model:** `databricks-gte-large-en` (1024-dim), READY in this workspace
- **Seed job:** `fe-bar-lakebase-seed` (serverless), result_state SUCCESS, 108s
- **Search-build job:** `fe-bar-lakebase-search-build` (serverless), result_state SUCCESS

## Seed result (pgvector)
800 cases inserted into Lakebase Postgres `cases` table with `vector(1024)` embeddings and
an HNSW index (`cases_embedding_hnsw`, cosine). `GRANT SELECT ON cases TO PUBLIC` so the
app service principal role can read it.

## Lakebase Search build + validation (all three modes OK)
Lakebase Search (Beta) enabled on the project. `validate_search` notebook output (verbatim):

```json
{
  "steps": [
    { "build_indexes": "OK",
      "sample": ["lakebase_text", "lakebase_vector", "plpgsql", "vector"] },
    { "bm25_query": "OK",
      "sample": [
        ["Keystone Care", "-1.629", "The surgeon says it should not be delayed further, but a lumbar decompression wa"],
        ["Sunbelt D-SNP", "-1.629", "They have been stable on it for over a year, but adalimumab was denied for lack "],
        ["BluePeak Health", "-1.629", "Our member is appealing because their maintenance biologic was denied for lack o"]
      ] },
    { "hybrid_query": "OK",
      "sample": [
        ["Sunbelt D-SNP", "0.02858", "Our member's request for a power wheelchair was denied as not medically necessar"],
        ["Liberty Advantage", "0.02845", "The member disputes that a power wheelchair was denied pending additional docume"],
        ["Evergreen Health Plan", "0.02808", "The member disputes that a power wheelchair was denied as a non-covered service."]
      ] }
  ]
}
```

Objects built: `search_tsv` (generated tsvector over narrative + CARC/CPT/ICD/service
columns), `cases_embedding_ann` (lakebase_ann vector index), `cases_search_bm25`
(lakebase_bm25 index). A standard Postgres FTS fallback (`ts` tsvector + GIN) was also
added for portability if Lakebase Search is not enabled (`fts_add_standard.py`).

## Meaning
- **Vector (semantic):** query "member needs a mobility device to get around their home
  safely" returns power-wheelchair cases that share almost no keywords, matching on meaning.
- **BM25 (keyword):** exact-token retrieval over the narrative + code columns.
- **Hybrid (RRF):** fuses both, reranking to the most relevant cases.

## Reproduce
Notebooks committed in `../03_lakebase_serving/setup/`:
`seed_lakebase_fe_vm.py` (seed + embeddings + HNSW), `validate_search.py` (Lakebase Search
objects + validation), `fts_add_standard.py` (standard FTS fallback). See
`../03_lakebase_serving/DEPLOY_FE_VM.md` for the full step list.
