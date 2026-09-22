-- Governed view: reconcile internal coverage against the WA HCA state eligibility file.
-- Captured live from hls_amer_catalog.`appeals-review` (information_schema.views), 2026-09-22.
-- Labels each member concur_active / concur_inactive / discrepancy_* / missing_from_state
-- so the app's Eligibility Triage tab can flag internal-vs-state coverage mismatches.

CREATE OR REPLACE VIEW hls_amer_catalog.`appeals-review`.state_eligibility_corroboration AS
WITH latest_state AS (
  SELECT *, ROW_NUMBER() OVER (PARTITION BY state_member_id ORDER BY source_file_date DESC) AS rn
  FROM wa_hca_eligibility_raw
),
latest_internal AS (
  SELECT member_id,
         coverage_start AS int_coverage_start,
         coverage_end   AS int_coverage_end,
         is_active      AS int_is_active,
         plan_type      AS int_plan_type,
         ROW_NUMBER() OVER (PARTITION BY member_id ORDER BY coverage_start DESC) AS rn
  FROM hls_amer_catalog.`appeals-review`.eligibility
)
SELECT
  m.member_id,
  m.state_member_id,
  m.state,
  m.plan_type AS internal_plan_type,
  ls.eligibility_status AS state_status,
  ls.coverage_start AS state_coverage_start,
  ls.coverage_end   AS state_coverage_end,
  ls.plan_code      AS state_plan_code,
  ls.county         AS state_county,
  ls.source_file_date AS latest_state_file_date,
  lie.int_is_active AS internal_is_active,
  lie.int_coverage_start AS internal_coverage_start,
  lie.int_coverage_end   AS internal_coverage_end,
  CASE
    WHEN ls.state_member_id IS NULL THEN 'missing_from_state'
    WHEN lie.int_is_active = true  AND ls.eligibility_status = 'Active'     THEN 'concur_active'
    WHEN lie.int_is_active = false AND ls.eligibility_status = 'Terminated' THEN 'concur_inactive'
    WHEN lie.int_is_active = false AND ls.eligibility_status = 'Active'     THEN 'discrepancy_internal_inactive_state_active'
    WHEN lie.int_is_active = true  AND ls.eligibility_status = 'Terminated' THEN 'discrepancy_internal_active_state_inactive'
    ELSE 'unknown'
  END AS corroboration_status
FROM hls_amer_catalog.`appeals-review`.members m
LEFT JOIN latest_state ls   ON ls.rn = 1  AND m.state_member_id = ls.state_member_id
LEFT JOIN latest_internal lie ON lie.rn = 1 AND m.member_id = lie.member_id
WHERE m.state_member_id IS NOT NULL;
