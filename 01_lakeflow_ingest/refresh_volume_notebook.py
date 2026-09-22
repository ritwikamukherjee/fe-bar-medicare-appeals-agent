# Databricks notebook source
# MAGIC %md
# MAGIC # Refresh appeals-review volume data
# MAGIC
# MAGIC Run this notebook on a **cluster** to regenerate synthetic data in the volume:
# MAGIC - Writes to `/Volumes/hls_amer_catalog/appeals-review/raw_data/` (members, eligibility, providers, prior_authorizations, claims, appeals).
# MAGIC - Uses **drug_name** for Prescription Drug (no fake NDC); NDC can be joined from your external source later.
# MAGIC
# MAGIC **After this completes**, run your table pipeline (e.g. `create_tables.sql` or DLT) to refresh the Delta tables from the volume.

# COMMAND ----------

# MAGIC %pip install faker holidays -q

# COMMAND ----------

# MAGIC %run /Workspace/Users/raven.mukherjee@databricks.com/appeals-review/scripts/generate_healthcare_data
