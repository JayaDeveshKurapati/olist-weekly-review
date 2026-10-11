-- check: dq03_payment_vs_items_plus_freight
-- description: for orders with items, sum(payment_value) should equal sum(price + freight_value) within 1.00 BRL
-- handling: flagged (payment_mismatch_flag = 1 in mart_orders; rows kept)
-- why: legitimate causes exist (instalment interest, vouchers), so these orders are not wrong enough to drop. Revenue is defined from item prices, not payments, so the mismatch does not distort revenue; the flag lets analysts exclude them if they need cash-based numbers.
-- max_fail_pct: 10.0
-- @found
WITH i AS (
    SELECT order_id, SUM(CAST(price AS REAL) + CAST(freight_value AS REAL)) AS v
    FROM raw_order_items GROUP BY order_id
),
p AS (
    SELECT order_id, SUM(CAST(payment_value AS REAL)) AS v
    FROM raw_order_payments GROUP BY order_id
)
SELECT COALESCE(SUM(CASE WHEN ABS(COALESCE(p.v, 0) - i.v) > 1.0 THEN 1 ELSE 0 END), 0) AS bad_rows,
       COUNT(*) AS total_rows
FROM i LEFT JOIN p ON p.order_id = i.order_id;
-- @residual
SELECT COUNT(*) AS bad_rows
FROM mart_orders
WHERE n_items > 0
  AND ABS(COALESCE(payment_total, 0) - (items_value + freight_value)) > 1.0
  AND payment_mismatch_flag = 0;
