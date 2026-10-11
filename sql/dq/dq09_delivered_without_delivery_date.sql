-- check: dq09_delivered_without_delivery_date
-- description: (own check) orders with status 'delivered' must carry a delivery date
-- handling: flagged (missing_delivery_date_flag = 1; delay and on-time metrics skip them automatically because delay_days is NULL)
-- why: the order and its revenue are real, but we cannot say whether it was late. Assuming 'on time' would flatter the on-time rate; dropping it would understate revenue. Excluding it from the delay denominator is the honest option.
-- max_fail_pct: 1.0
-- @found
SELECT COALESCE(SUM(CASE WHEN LOWER(TRIM(order_status)) = 'delivered'
                          AND NULLIF(TRIM(order_delivered_customer_date), '') IS NULL
                         THEN 1 ELSE 0 END), 0) AS bad_rows,
       COALESCE(SUM(CASE WHEN LOWER(TRIM(order_status)) = 'delivered' THEN 1 ELSE 0 END), 0) AS total_rows
FROM raw_orders;
-- @residual
SELECT COUNT(*) AS bad_rows
FROM mart_orders
WHERE order_status = 'delivered' AND delivered_customer_ts IS NULL AND missing_delivery_date_flag = 0;
