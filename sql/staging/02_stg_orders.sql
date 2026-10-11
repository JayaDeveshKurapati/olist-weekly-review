-- Staging: one clean row per order_id.
--   * rows with a null/blank order_id are dropped (dq01)
--   * duplicate order_id rows: first one kept (dq01)
--   * orders whose customer_id is unknown are dropped (dq04)
--   * a delivery timestamp earlier than the purchase is impossible: the value
--     is set to NULL and the row is flagged (dq02)
-- Timestamps are normalised to 'YYYY-MM-DD HH:MM:SS' text via datetime().
DROP TABLE IF EXISTS stg_orders;

CREATE TABLE stg_orders AS
WITH typed AS (
    SELECT order_id,
           customer_id,
           LOWER(TRIM(order_status))                                     AS status,
           DATETIME(NULLIF(TRIM(order_purchase_timestamp), ''))          AS purchase_ts,
           DATETIME(NULLIF(TRIM(order_approved_at), ''))                 AS approved_ts,
           DATETIME(NULLIF(TRIM(order_delivered_carrier_date), ''))      AS carrier_ts,
           DATETIME(NULLIF(TRIM(order_delivered_customer_date), ''))     AS delivered_raw_ts,
           DATETIME(NULLIF(TRIM(order_estimated_delivery_date), ''))     AS estimated_ts,
           ROW_NUMBER() OVER (PARTITION BY order_id ORDER BY rowid)      AS rn
    FROM raw_orders
    WHERE NULLIF(TRIM(order_id), '') IS NOT NULL
)
SELECT order_id,
       customer_id,
       status,
       purchase_ts,
       approved_ts,
       carrier_ts,
       CASE WHEN delivered_raw_ts < purchase_ts THEN NULL ELSE delivered_raw_ts END
                                                              AS delivered_customer_ts,
       estimated_ts,
       CASE WHEN delivered_raw_ts < purchase_ts THEN 1 ELSE 0 END
                                                              AS delivered_before_purchase_flag
FROM typed
WHERE rn = 1
  AND customer_id IN (SELECT customer_id FROM stg_customers);

CREATE UNIQUE INDEX ux_stg_orders ON stg_orders (order_id);
CREATE INDEX ix_stg_orders_customer ON stg_orders (customer_id);
