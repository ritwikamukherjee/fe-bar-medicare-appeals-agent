# Deploying the Lakebase layer into `fe-vm-hls-amer`

The Lakebase operational-serving layer was consolidated into the same AWS workspace and
catalog as the rest of the build. Steps (all run 2026-09-22; validated output in
`../evidence/LAKEBASE_DEPLOYMENT.md`).

## 1. Lakebase Autoscale project
```
project: projects/healthplan-appeals  (Postgres 17)
branch:  production
endpoint: primary (READ_WRITE)
```

## 2. UC source tables (from the synthetic CSVs in ./data)
```
hls_amer_catalog.healthplan_appeals.cases   (800 rows)
hls_amer_catalog.healthplan_appeals.plans   (10 rows)
```
Loaded by uploading `data/cases.csv` and `data/plans.csv` to a UC volume
(`hls_amer_catalog.healthplan_appeals.raw`) and `CREATE TABLE ... AS SELECT * FROM read_files(...)`.

## 3. Seed Lakebase (serverless notebook job)
`setup/seed_lakebase_fe_vm.py` (a copy of `setup/seed_lakebase.py` repointed at
`hls_amer_catalog.healthplan_appeals.*` with a `GRANT SELECT ON cases TO PUBLIC`):
reads the joined cases, embeds narratives with `databricks-gte-large-en`, creates the
Postgres `cases` table with `vector(1024)`, inserts 800 rows, builds an HNSW index.

## 4. Lakebase Search objects (serverless notebook job)
`setup/validate_search.py` builds `search_tsv` + `cases_embedding_ann` (lakebase_ann) +
`cases_search_bm25` (lakebase_bm25) and validates vector, BM25, and hybrid. Requires
Lakebase Search (Beta) enabled on the project (one-time toggle in project settings).
`setup/fts_add_standard.py` adds a standard Postgres FTS index (tsvector + GIN) as a
portable fallback when Lakebase Search is not enabled.

## 5. App front-end
The `app-react/` app (env: `LAKEBASE_PROJECT=healthplan-appeals`, `LAKEBASE_BRANCH=production`,
`EMBEDDING_MODEL=databricks-gte-large-en`, `PGUSER=<app SP client id>`) connects as the app
service principal, mints a short-lived Lakebase OAuth credential per request, and runs the
vector / BM25 / hybrid queries in `app-react/lakebase.py`.

Note: `fe-vm-hls-amer` is currently at its 100-app limit, so the front-end is served from
the sibling workspace (`healthplan-search-compare`). The data + all three search modes run
in `fe-vm-hls-amer` (see evidence). To host the UI here too, free an app slot and
`databricks apps create healthplan-search-compare` + `sync` + `deploy` this folder.
