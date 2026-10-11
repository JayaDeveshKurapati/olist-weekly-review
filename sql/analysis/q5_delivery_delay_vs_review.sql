-- Q5. Average delivery delay vs the estimated date, and how it relates to review score.
-- delay_days = delivery date - estimated date, in whole days (positive = late).
-- Population: delivered orders that have BOTH a usable delivery date and a review.
-- One row per review score plus an ALL row. Read it top to bottom: as the score
-- falls, the average delay rises and the share of late orders explodes.
WITH base AS (
    SELECT review_score, delay_days, delivery_days
    FROM mart_orders
    WHERE order_status = 'delivered'
      AND delay_days IS NOT NULL
      AND review_score IS NOT NULL
),
per_score AS (
    SELECT CAST(review_score AS TEXT)                AS review_score,
           COUNT(*)                                  AS orders,
           ROUND(AVG(delay_days), 2)                 AS avg_delay_days,
           ROUND(100.0 * AVG(delay_days > 0), 1)     AS pct_late,
           ROUND(AVG(delivery_days), 2)              AS avg_delivery_days
    FROM base
    GROUP BY review_score
),
overall AS (
    SELECT 'ALL', COUNT(*), ROUND(AVG(delay_days), 2),
           ROUND(100.0 * AVG(delay_days > 0), 1), ROUND(AVG(delivery_days), 2)
    FROM base
)
SELECT *
FROM (SELECT * FROM per_score UNION ALL SELECT * FROM overall)
ORDER BY CASE WHEN review_score = 'ALL' THEN 1 ELSE 0 END, review_score;
