-- Simple pipeline to create tables from raw parquet data
-- Reads from /Volumes/hls_amer_catalog/appeals-review/raw_data/ and creates tables

-- Members table
CREATE OR REPLACE TABLE members AS
SELECT *
FROM read_files(
  '/Volumes/hls_amer_catalog/appeals-review/raw_data/members',
  format => 'parquet'
);

-- Eligibility table
CREATE OR REPLACE TABLE eligibility AS
SELECT *
FROM read_files(
  '/Volumes/hls_amer_catalog/appeals-review/raw_data/eligibility',
  format => 'parquet'
);

-- Providers table
CREATE OR REPLACE TABLE providers AS
SELECT *
FROM read_files(
  '/Volumes/hls_amer_catalog/appeals-review/raw_data/providers',
  format => 'parquet'
);

-- Prior Authorizations table
CREATE OR REPLACE TABLE prior_authorizations AS
SELECT *
FROM read_files(
  '/Volumes/hls_amer_catalog/appeals-review/raw_data/prior_authorizations',
  format => 'parquet'
);

-- Claims table
CREATE OR REPLACE TABLE claims AS
SELECT *
FROM read_files(
  '/Volumes/hls_amer_catalog/appeals-review/raw_data/claims',
  format => 'parquet'
);

-- Appeals table
CREATE OR REPLACE TABLE appeals AS
SELECT *
FROM read_files(
  '/Volumes/hls_amer_catalog/appeals-review/raw_data/appeals',
  format => 'parquet'
);
