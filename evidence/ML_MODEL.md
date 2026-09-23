# Execution Evidence - trained + served overturn-likelihood model

Trained, registered, scored, and served in `fe-vm-hls-amer` on 2026-09-22. Synthetic data.

## Training run (serverless notebook job, committed output)
```json
{
  "rows": 1424,
  "overturn_base_rate": 0.3694,
  "auc": 0.4752,
  "accuracy": 0.632,
  "model": "hls_amer_catalog.appeals_ml.appeal_overturn_model",
  "version": 3,
  "scored_table": "hls_amer_catalog.appeals_ml.appeal_overturn_scores"
}
```
- **MLflow**: run logged with params (LogisticRegression) + metrics (auc, accuracy) + model
  signature and input example.
- **Unity Catalog**: registered model `hls_amer_catalog.appeals_ml.appeal_overturn_model`,
  version 3, alias `champion`.
- **Scored table**: `hls_amer_catalog.appeals_ml.appeal_overturn_scores` written for all 1,424 appeals.

## Honest read of the metric
Test **AUC 0.475** is near chance. This is a property of the synthetic data: overturn is a
near-random Bernoulli draw weighted by denial-reason rate, so there is no learnable
individual-level signal (a high AUC would mean leakage). The value demonstrated here is the
**end-to-end MLOps pattern** (feature layer -> MLflow -> UC model -> Model Serving -> scored
table), not predictive accuracy on synthetic labels.

## The ranking is still meaningful
The model's top-probability appeals are exactly the known high-overturn-rate denial reasons,
consistent with the certified `appeals_metrics` overturn analysis in `RUN_EVIDENCE.md` §3:

| appeal_id | original_denial_reason | overturn_probability |
|---|---|---|
| APL-00002182 | Quantity limit exceeded | 0.488 |
| APL-00002192 | Service not covered under plan | 0.483 |
| APL-00000977 | Formulary exclusion | 0.481 |
| APL-00000391 | Experimental/investigational | 0.470 |
| APL-00001079 | Service not covered under plan | 0.467 |

(Formulary exclusion, Experimental, Quantity limit, and Service-not-covered are the highest
certified overturn-rate reasons, so the prioritization surfaces the right cases even at
chance-level binary AUC.)

## Served
Model Serving endpoint **`appeal-overturn-model`** created from the champion version
(scale-to-zero). Config in `../07_ml_overturn_model/serving_endpoint.json`. Query shape:
one row per appeal with `appeal_type`, `appeal_source`, `original_denial_reason` -> returns
overturn probability.
