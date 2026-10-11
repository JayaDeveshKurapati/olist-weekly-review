-- Staging: one row per (order_id, order_item_id).
--   * null / non-positive price or null / negative freight dropped (dq07)
--   * items pointing at an order we do not have are dropped (dq08)
DROP TABLE IF EXISTS stg_order_items;

CREATE TABLE stg_order_items AS
SELECT order_id,
       CAST(order_item_id AS INTEGER)  AS order_item_id,
       product_id,
       seller_id,
       DATETIME(NULLIF(TRIM(shipping_limit_date), '')) AS shipping_limit_ts,
       CAST(price AS REAL)             AS price,
       CAST(freight_value AS REAL)     AS freight_value
FROM (
    SELECT *,
           ROW_NUMBER() OVER (PARTITION BY order_id, order_item_id ORDER BY rowid) AS rn
    FROM raw_order_items
    WHERE NULLIF(TRIM(price), '') IS NOT NULL
      AND NULLIF(TRIM(freight_value), '') IS NOT NULL
      AND CAST(price AS REAL) > 0
      AND CAST(freight_value AS REAL) >= 0
)
WHERE rn = 1
  AND order_id IN (SELECT order_id FROM stg_orders);

CREATE INDEX ix_stg_items_order ON stg_order_items (order_id);
CREATE INDEX ix_stg_items_product ON stg_order_items (product_id);
