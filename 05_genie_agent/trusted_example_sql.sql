-- Trusted example SQL for the Genie space (steers Genie toward governed patterns).
-- Add these in the space's "SQL examples" / Instructions section.

-- Q: Providers with highest denial rates that also appear in the fraud reference
WITH pdr AS (
  SELECT `Provider ID`, `Provider Name`, `Specialty`, MEASURE(`Denial Rate`) AS denial_rate
  FROM hls_amer_catalog.`appeals-review`.provider_risk_metrics GROUP BY ALL),
fp AS (
  SELECT DISTINCT c.provider_id, f.fraud_type
  FROM hls_amer_catalog.`appeals-review`.claims c
  JOIN hls_amer_catalog.`appeals-review`.fraud_reference f ON c.claim_id = f.claim_id)
SELECT pdr.`Provider Name`, pdr.`Specialty`, pdr.denial_rate, fp.fraud_type
FROM pdr JOIN fp ON pdr.`Provider ID` = fp.provider_id
ORDER BY pdr.denial_rate DESC;

-- Q: Appeal overturn rate by original denial reason
SELECT `Original Denial Reason`, MEASURE(`Appeal Count`) AS appeals,
       MEASURE(`Overturn Rate`) AS overturn_rate
FROM hls_amer_catalog.`appeals-review`.appeals_metrics
GROUP BY `Original Denial Reason` ORDER BY overturn_rate DESC;

-- Q: Claims paid while member coverage was inactive (payment integrity)
SELECT c.claim_id, c.member_id, c.service_date, c.paid_amount, c.status
FROM hls_amer_catalog.`appeals-review`.claims c
WHERE c.was_member_active = false AND c.paid_amount > 0
ORDER BY c.paid_amount DESC;
