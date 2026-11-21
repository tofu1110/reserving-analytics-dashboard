-- 01_load.sql
-- Load the raw long-format extract produced by src/export_data.py.

CREATE OR REPLACE TABLE raw_claims AS
SELECT *
FROM read_csv('data/raw/clrd_long.csv', header = true, auto_detect = true);