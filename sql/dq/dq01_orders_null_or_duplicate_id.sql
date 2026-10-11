-- check: dq01_orders_null_or_duplicate_id
-- description: order_id in orders must be present and unique (counts blank ids + surplus duplicate rows)
-- handling: dropped (blank ids removed; first row kept for each duplicated id)
-- why: order_id is the primary key of every downstream join; a duplicate would double-count revenue and a blank id cannot be linked to items, payments or reviews.
-- max_fail_pct: 1.0
-- @found
SELECT (SELECT COUNT(*) FROM raw_orders WHERE NULLIF(TRIM(order_id), '') IS NULL)
     + (SELECT COUNT(*) - COUNT(DISTINCT order_id) FROM raw_orders WHERE NULLIF(TRIM(order_id), '') IS NOT NULL)
       AS bad_rows,
       (SELECT COUNT(*) FROM raw_orders) AS total_rows;
-- @residual
SELECT (SELECT COUNT(*) FROM stg_orders WHERE order_id IS NULL OR TRIM(order_id) = '')
     + (SELECT COUNT(*) - COUNT(DISTINCT order_id) FROM stg_orders) AS bad_rows;
