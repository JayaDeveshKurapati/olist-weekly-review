-- check: dq08_orphan_child_rows
-- description: (own check) items, payments and reviews must reference an order that exists in orders
-- handling: dropped (orphan child rows excluded from staging)
-- why: an orphan row belongs to no order, so any join-based metric either loses it silently or, in a sum over the child table, counts revenue that no order owns.
-- max_fail_pct: 1.0
-- @found
SELECT (SELECT COUNT(*) FROM raw_order_items    WHERE order_id NOT IN (SELECT order_id FROM raw_orders))
     + (SELECT COUNT(*) FROM raw_order_payments WHERE order_id NOT IN (SELECT order_id FROM raw_orders))
     + (SELECT COUNT(*) FROM raw_order_reviews  WHERE order_id NOT IN (SELECT order_id FROM raw_orders))
       AS bad_rows,
       (SELECT COUNT(*) FROM raw_order_items) + (SELECT COUNT(*) FROM raw_order_payments)
     + (SELECT COUNT(*) FROM raw_order_reviews) AS total_rows;
-- @residual
SELECT (SELECT COUNT(*) FROM stg_order_items    WHERE order_id NOT IN (SELECT order_id FROM stg_orders))
     + (SELECT COUNT(*) FROM stg_order_payments WHERE order_id NOT IN (SELECT order_id FROM stg_orders))
     + (SELECT COUNT(*) FROM stg_order_reviews  WHERE order_id NOT IN (SELECT order_id FROM stg_orders))
       AS bad_rows;
