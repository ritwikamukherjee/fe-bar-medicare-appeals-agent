# Databricks notebook source
# MAGIC %pip install --quiet "psycopg[binary]"
# MAGIC dbutils.library.restartPython()

# COMMAND ----------
import json, psycopg
from databricks.sdk import WorkspaceClient
PROJECT_ID, BRANCH = "healthplan-appeals", "production"
w = WorkspaceClient(); user_email = w.current_user.me().user_name
ep = w.api_client.do("GET", f"/api/2.0/postgres/projects/{PROJECT_ID}/branches/{BRANCH}/endpoints")["endpoints"][0]
host = ep["status"]["hosts"]["host"]
token = w.api_client.do("POST", "/api/2.0/postgres/credentials", body={"endpoint": ep["name"]})["token"]
conn = psycopg.connect(host=host, dbname="databricks_postgres", user=user_email, password=token, sslmode="require", autocommit=True)
cur = conn.cursor()
cur.execute("""ALTER TABLE cases ADD COLUMN IF NOT EXISTS ts tsvector
    GENERATED ALWAYS AS (to_tsvector('english',
      coalesce(narrative,'') || ' ' || coalesce(denial_reason_code,'') || ' ' ||
      coalesce(cpt_hcpcs_code,'') || ' ' || coalesce(icd10_code,'') || ' ' ||
      coalesce(service_category,''))) STORED""")
cur.execute("CREATE INDEX IF NOT EXISTS cases_ts_gin ON cases USING gin(ts)")
cur.execute("ANALYZE cases")
cur.execute("GRANT SELECT ON cases TO PUBLIC")
# sanity: standard FTS keyword + a hybrid RRF using ts_rank_cd
cur.execute("SELECT plan_name, round(ts_rank_cd(ts, plainto_tsquery('english','wheelchair'))::numeric,4) r, left(narrative,60) FROM cases WHERE ts @@ plainto_tsquery('english','wheelchair') ORDER BY r DESC LIMIT 3")
report = {"fts_keyword_top": [list(x) for x in cur.fetchall()]}
cur.execute("SELECT count(*) FROM cases WHERE ts IS NOT NULL")
report["rows_with_ts"] = cur.fetchone()[0]
dbutils.notebook.exit(json.dumps(report, default=str))
