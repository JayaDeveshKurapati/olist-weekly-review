-- Q4. Repeat-purchase rate.
-- TRAP: in Olist, customer_id is generated fresh for EVERY order, so counting
-- orders per customer_id can never exceed 1. The real person is customer_unique_id.
-- Repeat customer = a customer_unique_id with 2+ distinct valid orders.
-- Both versions are shown so the difference is visible.
WITH per_person AS (
    SELECT customer_unique_id AS cust, COUNT(DISTINCT order_id) AS n_orders
    FROM mart_orders
    WHERE is_valid_order = 1
    GROUP BY customer_unique_id
),
per_customer_id AS (
    SELECT customer_id AS cust, COUNT(DISTINCT order_id) AS n_orders
    FROM mart_orders
    WHERE is_valid_order = 1
    GROUP BY customer_id
)
SELECT 'customer_unique_id (correct)' AS identifier,
       COUNT(*)                                                    AS customers,
       SUM(CASE WHEN n_orders >= 2 THEN 1 ELSE 0 END)              AS repeat_customers,
       ROUND(100.0 * SUM(CASE WHEN n_orders >= 2 THEN 1 ELSE 0 END) / COUNT(*), 2) AS repeat_rate_pct,
       ROUND(AVG(n_orders), 3)                                     AS avg_orders_per_customer
FROM per_person
UNION ALL
SELECT 'customer_id (naive, wrong)',
       COUNT(*),
       SUM(CASE WHEN n_orders >= 2 THEN 1 ELSE 0 END),
       ROUND(100.0 * SUM(CASE WHEN n_orders >= 2 THEN 1 ELSE 0 END) / COUNT(*), 2),
       ROUND(AVG(n_orders), 3)
FROM per_customer_id;
