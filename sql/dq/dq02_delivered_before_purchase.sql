-- check: dq02_delivered_before_purchase
-- description: order_delivered_customer_date must not be earlier than order_purchase_timestamp
-- handling: fixed + flagged (impossible delivery date set to NULL, delivered_before_purchase_flag = 1; the order itself is kept)
-- why: the purchase and the order are real, only the delivery timestamp is wrong. Dropping the order would understate revenue; keeping the bad date would create negative delivery times and corrupt the delay metrics.
-- max_fail_pct: 1.0
-- @found
SELECT COALESCE(SUM(CASE WHEN DATETIME(NULLIF(TRIM(order_delivered_customer_date), ''))
                           < DATETIME(NULLIF(TRIM(order_purchase_timestamp), ''))
                         THEN 1 ELSE 0 END), 0) AS bad_rows,
       COUNT(*) AS total_rows
FROM raw_orders;
-- @residual
SELECT COUNT(*) AS bad_rows
FROM stg_orders
WHERE delivered_customer_ts < purchase_ts;
