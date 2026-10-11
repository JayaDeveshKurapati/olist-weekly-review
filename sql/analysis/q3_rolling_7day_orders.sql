-- Q3. 7-day rolling average of daily order count.
-- "Order count" = all orders placed that day (any status).
-- Days with zero orders must appear as 0, otherwise ROWS BETWEEN 6 PRECEDING would
-- silently span more than 7 calendar days. A recursive CTE builds the calendar.
-- The first six days have no full 7-day window, so their average is left NULL.
WITH RECURSIVE bounds AS (
    SELECT MIN(purchase_date) AS d0, MAX(purchase_date) AS d1
    FROM mart_orders
    WHERE purchase_date IS NOT NULL
),
days(d) AS (
    SELECT d0 FROM bounds
    UNION ALL
    SELECT DATE(d, '+1 day') FROM days, bounds WHERE d < d1
),
daily AS (
    SELECT purchase_date AS d, COUNT(*) AS n_orders
    FROM mart_orders
    WHERE purchase_date IS NOT NULL
    GROUP BY purchase_date
),
filled AS (
    SELECT days.d AS order_date, COALESCE(daily.n_orders, 0) AS n_orders
    FROM days
    LEFT JOIN daily ON daily.d = days.d
),
rolled AS (
    SELECT order_date,
           n_orders,
           AVG(n_orders)  OVER w AS avg_7d,
           COUNT(*)       OVER w AS days_in_window
    FROM filled
    WINDOW w AS (ORDER BY order_date ROWS BETWEEN 6 PRECEDING AND CURRENT ROW)
)
SELECT order_date,
       n_orders                                                  AS orders,
       CASE WHEN days_in_window = 7 THEN ROUND(avg_7d, 2) END    AS rolling_7d_avg
FROM rolled
ORDER BY order_date;
