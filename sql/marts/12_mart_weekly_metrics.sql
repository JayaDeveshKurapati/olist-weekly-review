-- MART: one row per purchase week (Monday start) - the table behind the weekly
-- business review. See report metric definitions for the exact formulas.
--   NORTH STAR   satisfied_orders      = delivered orders rated 4 or 5 stars
--   supporting   gmv, on_time_rate_pct, low_review_rate_pct
-- Weeks are attributed by PURCHASE date, so the newest weeks are incomplete
-- (orders not yet delivered / reviewed) - treat the last 1-2 weeks with care.
DROP TABLE IF EXISTS mart_weekly_metrics;

CREATE TABLE mart_weekly_metrics AS
SELECT purchase_week                                                      AS week_start,
       COUNT(*)                                                           AS orders_placed,
       SUM(is_valid_order)                                                AS valid_orders,
       ROUND(SUM(CASE WHEN is_valid_order = 1 THEN COALESCE(items_value, 0) END), 2) AS gmv,
       SUM(CASE WHEN order_status = 'delivered' AND delay_days IS NOT NULL THEN 1 ELSE 0 END)
                                                                          AS delivered_orders,
       SUM(CASE WHEN order_status = 'delivered' AND review_score >= 4 THEN 1 ELSE 0 END)
                                                                          AS satisfied_orders,
       SUM(CASE WHEN order_status = 'delivered' AND review_score IS NOT NULL THEN 1 ELSE 0 END)
                                                                          AS reviewed_delivered_orders,
       ROUND(100.0 * SUM(CASE WHEN order_status = 'delivered' AND delay_days <= 0 THEN 1 ELSE 0 END)
             / NULLIF(SUM(CASE WHEN order_status = 'delivered' AND delay_days IS NOT NULL THEN 1 ELSE 0 END), 0), 2)
                                                                          AS on_time_rate_pct,
       ROUND(100.0 * SUM(CASE WHEN order_status = 'delivered' AND review_score <= 2 THEN 1 ELSE 0 END)
             / NULLIF(SUM(CASE WHEN order_status = 'delivered' AND review_score IS NOT NULL THEN 1 ELSE 0 END), 0), 2)
                                                                          AS low_review_rate_pct,
       ROUND(AVG(CASE WHEN order_status = 'delivered' THEN review_score END), 3) AS avg_review_score
FROM mart_orders
WHERE purchase_week IS NOT NULL
GROUP BY purchase_week;

CREATE UNIQUE INDEX ux_mart_weekly ON mart_weekly_metrics (week_start);
