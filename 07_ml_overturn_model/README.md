# Layer 7 - Trained + served ML model (appeal overturn-likelihood)

Pairs the grounded Gen AI answers with a **trained-model risk score**: for each appeal it
predicts the probability the denial will be overturned, so reviewers work the highest-yield
cases first. Trained with **MLflow**, registered in **Unity Catalog**, and **served** on
Model Serving. Uses the same certified appeals feature layer as the rest of the build.

## Pipeline
- **Train** ([`train_overturn_model.py`](train_overturn_model.py), serverless notebook job):
  reads `hls_amer_catalog.`​`` `appeals-review` ``.appeals joined to providers, one-hot encodes
  `appeal_type` / `appeal_source` / `original_denial_reason` (+ `has_documentation`), trains a
  scikit-learn classifier, logs params/metrics/signature to MLflow.
- **Register**: Unity Catalog model `hls_amer_catalog.appeals_ml.appeal_overturn_model`,
  alias `champion`.
- **Score**: writes `hls_amer_catalog.appeals_ml.appeal_overturn_scores` (per-appeal
  `overturn_probability`) - the reviewer-prioritization table.
- **Serve**: Model Serving endpoint `appeal-overturn-model` ([`serving_endpoint.json`](serving_endpoint.json)),
  scale-to-zero.

## Honest results (and why they are what they are)
On this **synthetic** data, overturn is a near-random draw weighted by denial-reason rate,
so there is little individual-level signal to learn: test **AUC is ~0.48** (near chance) and
no estimator beats it - a high AUC here would indicate leakage, not skill. See
[`../evidence/ML_MODEL.md`](../evidence/ML_MODEL.md) for the committed metrics.

What still works and matters:
- The **ranking is sensible**: the model's highest-probability appeals are exactly the known
  high-overturn reasons (Formulary exclusion, Experimental/investigational, Service not
  covered, Quantity limit exceeded), matching the certified overturn-rate analysis.
- The **value is the productionization pattern**: certified feature layer -> MLflow tracking
  -> Unity Catalog registered model -> Model Serving -> a scored table feeding the queue,
  governed and reproducible end to end.

**What would lift accuracy on real data:** provider-level appeal history, free-text reviewer
notes / clinical documentation embeddings, prior-auth and eligibility timing, and a temporal
(seasonal / open-enrollment) signal. The feature layer and serving path are already in place
to add them.

## Connects to
- **Up:** trains on the governed appeals tables (`02_unity_catalog_governance/`).
- **Down:** the `appeal_overturn_scores` table prioritizes the reviewer queue the app
  (`06_databricks_app/`) surfaces, and complements the Genie/agent answers with a risk score.
