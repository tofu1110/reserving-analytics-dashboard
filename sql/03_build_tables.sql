-- 03_build_tables.sql
-- Aggregate the included company x LOB pairs to industry level by line of business.

CREATE OR REPLACE TABLE fact_triangle AS
SELECT
    r.lob,
    r.accident_year,
    r.dev_lag,
    r.calendar_year,
    SUM(r.cum_paid)                AS cum_paid,
    SUM(r.incurred - r.bulk_ibnr)  AS reported_incurred,  -- case incurred, excl. bulk and IBNR
    COUNT(*)                       AS n_companies
FROM raw_claims AS r
JOIN dq_pair_flags AS f USING (company, lob)
WHERE f.include_in_analysis
GROUP BY ALL
ORDER BY r.lob, r.accident_year, r.dev_lag;

-- Earned premium is the same at every lag, so take it once per accident year.
CREATE OR REPLACE TABLE fact_premium AS
SELECT
    r.lob,
    r.accident_year,
    SUM(r.earned_premium_net) AS earned_premium_net
FROM raw_claims AS r
JOIN dq_pair_flags AS f USING (company, lob)
WHERE f.include_in_analysis
  AND r.dev_lag = 1
GROUP BY ALL
ORDER BY r.lob, r.accident_year;

CREATE OR REPLACE TABLE dim_accident_year AS
SELECT DISTINCT accident_year
FROM fact_triangle
ORDER BY accident_year;

-- Volume-weighted age-to-age factors on cumulative paid, using a window function.
-- Used later to reconcile against the chain ladder factors computed in Python.
CREATE OR REPLACE TABLE ata_paid_sql AS
WITH pairs AS (
    SELECT
        lob,
        accident_year,
        dev_lag,
        cum_paid,
        LEAD(cum_paid) OVER (
            PARTITION BY lob, accident_year
            ORDER BY dev_lag
        ) AS next_cum_paid
    FROM fact_triangle
)
SELECT
    lob,
    dev_lag                        AS from_lag,
    dev_lag + 1                    AS to_lag,
    SUM(next_cum_paid) / SUM(cum_paid) AS ata_factor
FROM pairs
WHERE next_cum_paid IS NOT NULL
GROUP BY lob, dev_lag
ORDER BY lob, dev_lag;