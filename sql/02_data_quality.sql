-- 02_data_quality.sql
-- Data quality checks at company x line-of-business level.
-- A company x LOB pair is included in the analysis only if it has a complete
-- 10x10 triangle (55 cells), positive earned premium in every accident year,
-- and no negative cumulative paid or incurred amounts.
-- Decreases in cumulative paid (e.g. salvage and subrogation) are reported
-- but do not exclude a pair.

CREATE OR REPLACE TABLE dq_pair_flags AS
WITH pair_stats AS (
    SELECT
        company,
        lob,
        COUNT(*)                                          AS n_cells,
        COUNT(*) FILTER (WHERE cum_paid < 0)              AS n_negative_paid,
        COUNT(*) FILTER (WHERE incurred < 0)              AS n_negative_incurred,
        COUNT(*) FILTER (WHERE earned_premium_net <= 0)   AS n_nonpositive_premium,
        SUM(earned_premium_net) FILTER (WHERE dev_lag = 1) AS premium_total
    FROM raw_claims
    GROUP BY company, lob
),
paid_changes AS (
    SELECT
        company,
        lob,
        cum_paid - LAG(cum_paid) OVER (
            PARTITION BY company, lob, accident_year
            ORDER BY dev_lag
        ) AS paid_change
    FROM raw_claims
),
paid_decreases AS (
    SELECT company, lob, COUNT(*) AS n_paid_decreases
    FROM paid_changes
    WHERE paid_change < 0
    GROUP BY company, lob
)
SELECT
    s.*,
    COALESCE(d.n_paid_decreases, 0) AS n_paid_decreases,
    s.n_cells < 55                  AS flag_incomplete_triangle,
    s.n_nonpositive_premium > 0     AS flag_nonpositive_premium,
    s.n_negative_paid > 0           AS flag_negative_paid,
    s.n_negative_incurred > 0       AS flag_negative_incurred,
    NOT (s.n_cells < 55
         OR s.n_nonpositive_premium > 0
         OR s.n_negative_paid > 0
         OR s.n_negative_incurred > 0) AS include_in_analysis
FROM pair_stats AS s
LEFT JOIN paid_decreases AS d USING (company, lob);

-- One row per check, for the README and the Power BI data quality page.
CREATE OR REPLACE TABLE dq_summary AS
SELECT 'Incomplete triangle (< 55 cells)' AS check_name,
       COUNT(*) FILTER (WHERE flag_incomplete_triangle) AS pairs_flagged,
       'Excluded' AS action
FROM dq_pair_flags
UNION ALL
SELECT 'Zero or negative earned premium',
       COUNT(*) FILTER (WHERE flag_nonpositive_premium), 'Excluded'
FROM dq_pair_flags
UNION ALL
SELECT 'Negative cumulative paid',
       COUNT(*) FILTER (WHERE flag_negative_paid), 'Excluded'
FROM dq_pair_flags
UNION ALL
SELECT 'Negative incurred',
       COUNT(*) FILTER (WHERE flag_negative_incurred), 'Excluded'
FROM dq_pair_flags
UNION ALL
SELECT 'Cumulative paid decreases between lags',
       COUNT(*) FILTER (WHERE n_paid_decreases > 0), 'Reported only'
FROM dq_pair_flags
UNION ALL
SELECT 'Included in analysis',
       COUNT(*) FILTER (WHERE include_in_analysis), '-'
FROM dq_pair_flags
UNION ALL
SELECT 'Total company x LOB pairs', COUNT(*), '-'
FROM dq_pair_flags;