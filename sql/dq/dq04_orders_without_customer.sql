-- check: dq04_orders_without_customer
-- description: every order's customer_id must exist in the customers table
-- handling: dropped (the order and, by cascade, its items/payments/reviews are excluded from staging)
-- why: without a customer we cannot assign a state or a customer_unique_id, so the order cannot be used in any state-level or repeat-purchase metric, and nothing can be recovered from other tables.
-- max_fail_pct: 1.0
-- @found
SELECT COUNT(*) AS bad_rows, (SELECT COUNT(*) FROM raw_orders) AS total_rows
FROM raw_orders o
WHERE o.customer_id NOT IN (SELECT customer_id FROM raw_customers);   -- IN-subquery: SQLite indexes it, NOT EXISTS on unindexed raw tables is quadratic
-- @residual
SELECT COUNT(*) AS bad_rows
FROM stg_orders o
WHERE o.customer_id NOT IN (SELECT customer_id FROM stg_customers);
