-- Staging: one row per (order_id, payment_sequential). Orphans dropped (dq08).
-- Zero-value 'not_defined' payments exist in Olist; they are kept (harmless).
DROP TABLE IF EXISTS stg_order_payments;

CREATE TABLE stg_order_payments AS
SELECT order_id,
       CAST(payment_sequential AS INTEGER)     AS payment_sequential,
       LOWER(TRIM(payment_type))               AS payment_type,
       CAST(payment_installments AS INTEGER)   AS payment_installments,
       CAST(payment_value AS REAL)             AS payment_value
FROM (
    SELECT *,
           ROW_NUMBER() OVER (PARTITION BY order_id, payment_sequential ORDER BY rowid) AS rn
    FROM raw_order_payments
    WHERE NULLIF(TRIM(payment_value), '') IS NOT NULL
      AND CAST(payment_value AS REAL) >= 0
)
WHERE rn = 1
  AND order_id IN (SELECT order_id FROM stg_orders);

CREATE INDEX ix_stg_pay_order ON stg_order_payments (order_id);
