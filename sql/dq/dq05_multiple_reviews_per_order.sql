-- check: dq05_multiple_reviews_per_order
-- description: (own check) an order should have at most one review row; counts surplus review rows
-- handling: fixed (keep the most recently answered review per order)
-- why: a LEFT JOIN from orders to raw reviews would duplicate those orders and inflate order counts and revenue. The latest answer is the customer's final opinion of the order.
-- max_fail_pct: 5.0
-- @found
SELECT COUNT(*) - COUNT(DISTINCT order_id) AS bad_rows, COUNT(*) AS total_rows
FROM raw_order_reviews
WHERE NULLIF(TRIM(order_id), '') IS NOT NULL;
-- @residual
SELECT COUNT(*) - COUNT(DISTINCT order_id) AS bad_rows FROM stg_order_reviews;
