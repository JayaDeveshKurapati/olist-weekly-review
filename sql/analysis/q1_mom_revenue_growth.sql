-- Q1. Month-over-month revenue and growth %.
-- Revenue = SUM(item price, excl. freight) of valid orders (not canceled/unavailable),
--           attributed to the month of purchase.
-- A recursive calendar fills months with no sales with 0, so LAG() always compares
-- with the *calendar* previous month (Olist has a gap in late 2016, and a plain
-- LAG over only the months that have sales would compare Dec 2016 with Oct 2016).
-- Growth is NULL when the previous month is 0 (undefined, not infinite).
WITH RECURSIVE bounds AS (
    SELECT DATE(MIN(purchase_date), 'start of month') AS first_m,
           DATE(MAX(purchase_date), 'start of month') AS last_m
    FROM mart_orders
    WHERE is_valid_order = 1
),
months(m) AS (
    SELECT first_m FROM bounds
    UNION ALL
    SELECT DATE(m, '+1 month') FROM months, bounds WHERE m < last_m
),
monthly AS (
    SELECT purchase_month AS m, SUM(items_value) AS revenue
    FROM mart_orders
    WHERE is_valid_order = 1
    GROUP BY purchase_month
),
filled AS (
    SELECT months.m, COALESCE(monthly.revenue, 0) AS revenue
    FROM months
    LEFT JOIN monthly ON monthly.m = months.m
),
with_prev AS (
    SELECT m, revenue, LAG(revenue) OVER (ORDER BY m) AS prev_revenue
    FROM filled
)
SELECT STRFTIME('%Y-%m', m)                                             AS month,
       ROUND(revenue, 2)                                                AS revenue,
       ROUND(prev_revenue, 2)                                           AS prev_month_revenue,
       ROUND(100.0 * (revenue - prev_revenue) / NULLIF(prev_revenue, 0), 1) AS mom_growth_pct
FROM with_prev
ORDER BY m;
