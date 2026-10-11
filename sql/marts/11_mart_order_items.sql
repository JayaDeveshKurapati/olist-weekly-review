-- MART: one row per order item, enriched with category and the customer's state.
-- Used for revenue-by-category questions (price lives at item grain, so summing it
-- here cannot be inflated by payments or reviews).
DROP TABLE IF EXISTS mart_order_items;

CREATE TABLE mart_order_items AS
SELECT i.order_id,
       i.order_item_id,
       i.product_id,
       i.seller_id,
       COALESCE(p.category_en, 'unknown')  AS category_en,
       s.state                             AS seller_state,
       m.customer_state,
       m.order_status,
       m.is_valid_order,
       m.purchase_date,
       m.purchase_month,
       i.price,
       i.freight_value
FROM stg_order_items i
JOIN mart_orders m          ON m.order_id = i.order_id
LEFT JOIN stg_products p    ON p.product_id = i.product_id
LEFT JOIN stg_sellers  s    ON s.seller_id = i.seller_id;

CREATE INDEX ix_mart_items_state_cat ON mart_order_items (customer_state, category_en);
