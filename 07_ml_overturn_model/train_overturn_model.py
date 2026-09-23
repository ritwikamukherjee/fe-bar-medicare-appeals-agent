# Databricks notebook source
# MAGIC %md
# MAGIC # Appeal Overturn-Likelihood Model
# MAGIC Trains a classifier that predicts whether a denied-claim appeal will be OVERTURNED,
# MAGIC using the certified appeals feature layer. Logs to MLflow, registers to Unity Catalog,
# MAGIC and writes a scored table the reviewer queue can prioritize on. Serves via Model Serving
# MAGIC (endpoint created in a follow-up step). Synthetic data only.

# COMMAND ----------
# MAGIC %pip install --quiet scikit-learn
# MAGIC dbutils.library.restartPython()

# COMMAND ----------
import json, mlflow, pandas as pd
from sklearn.model_selection import train_test_split
from sklearn.compose import ColumnTransformer
from sklearn.preprocessing import OneHotEncoder
from sklearn.pipeline import Pipeline
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_auc_score, accuracy_score, classification_report
from mlflow.models.signature import infer_signature
from mlflow.tracking import MlflowClient

CATALOG, SCHEMA = "hls_amer_catalog", "appeals_ml"
MODEL_NAME = f"{CATALOG}.{SCHEMA}.appeal_overturn_model"
mlflow.set_registry_uri("databricks-uc")
mlflow.set_experiment("/Users/raven.mukherjee@databricks.com/fe-bar-overturn-model")

# COMMAND ----------
# Feature layer: appeal attributes + provider specialty; label = is_overturned
df = spark.sql("""
  SELECT a.appeal_id,
         a.appeal_type,
         a.appeal_source,
         a.original_denial_reason,
         CAST(a.has_documentation AS INT)      AS has_documentation,
         COALESCE(p.specialty, 'Unknown')      AS specialty,
         CAST(a.is_overturned AS INT)          AS is_overturned
  FROM hls_amer_catalog.`appeals-review`.appeals a
  LEFT JOIN hls_amer_catalog.`appeals-review`.providers p ON a.provider_id = p.provider_id
  WHERE a.is_overturned IS NOT NULL
""").toPandas()
print("rows:", len(df), "| overturn base rate:", round(df.is_overturned.mean(), 4))

CAT = ["appeal_type", "appeal_source", "original_denial_reason"]
NUM = ["has_documentation"]
X, y = df[CAT + NUM], df["is_overturned"]
Xtr, Xte, ytr, yte = train_test_split(X, y, test_size=0.25, random_state=42, stratify=y)

# COMMAND ----------
pre = ColumnTransformer([("cat", OneHotEncoder(handle_unknown="ignore"), CAT)], remainder="passthrough")
pipe = Pipeline([("pre", pre), ("clf", LogisticRegression(max_iter=2000))])

with mlflow.start_run(run_name="overturn-gbc") as run:
    pipe.fit(Xtr, ytr)
    proba = pipe.predict_proba(Xte)[:, 1]
    preds = (proba >= 0.5).astype(int)
    auc = roc_auc_score(yte, proba); acc = accuracy_score(yte, preds)
    mlflow.log_params({"model": "LogisticRegression", "n_features_cat": len(CAT)})
    mlflow.log_metrics({"auc": auc, "accuracy": acc})
    sig = infer_signature(Xte, proba)
    mlflow.sklearn.log_model(pipe, artifact_path="model", signature=sig,
                             input_example=Xte.head(3), registered_model_name=MODEL_NAME)
    run_id = run.info.run_id
print(f"AUC={auc:.3f}  ACC={acc:.3f}")
print(classification_report(yte, preds, digits=3))

# COMMAND ----------
# Promote latest version to alias 'champion'
c = MlflowClient()
ver = max(int(m.version) for m in c.search_model_versions(f"name='{MODEL_NAME}'"))
c.set_registered_model_alias(MODEL_NAME, "champion", ver)
print("registered", MODEL_NAME, "v"+str(ver), "-> alias champion")

# COMMAND ----------
# Score ALL appeals and persist a reviewer-prioritization table
full = df.copy()
full["overturn_probability"] = pipe.predict_proba(full[CAT + NUM])[:, 1]
scored = spark.createDataFrame(full[["appeal_id", "original_denial_reason", "specialty",
                                     "has_documentation", "is_overturned", "overturn_probability"]])
scored.write.mode("overwrite").saveAsTable(f"{CATALOG}.{SCHEMA}.appeal_overturn_scores")

# top-10 highest-overturn-probability open-risk appeals (evidence sample)
sample = (full.sort_values("overturn_probability", ascending=False)
              .head(10)[["appeal_id", "original_denial_reason", "specialty",
                         "overturn_probability"]].round(4).to_dict("records"))

dbutils.notebook.exit(json.dumps({
    "rows": len(df), "overturn_base_rate": round(float(df.is_overturned.mean()), 4),
    "auc": round(float(auc), 4), "accuracy": round(float(acc), 4),
    "model": MODEL_NAME, "version": ver,
    "scored_table": f"{CATALOG}.{SCHEMA}.appeal_overturn_scores",
    "top10_by_overturn_prob": sample,
}, indent=2, default=str))
