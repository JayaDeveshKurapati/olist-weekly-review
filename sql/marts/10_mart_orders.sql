-- MART: one row per order (grain = order_id). Analysis-ready.
--
-- Anti double-counting rule: items, payments and reviews are each pre-aggregated
-- to ONE row per order in a CTE *before* joining. Joining the three child tables
-- directly would multiply rows (an order with 3 items x 2 payments = 6 rows).
DROP TABLE IF EXISTS mart_orders;

CREATE TABLE mart_orders AS
WITH items AS (
    SELECT order_id,
           COUNT(*)                   AS n_items,
           COUNT(DISTINCT seller_id)  AS n_sellers,
           SUM(price)                 AS items_value,      -- merchandise value, excl. freight
           SUM(freight_value)         AS freight_value
    FROM stg_order_items
    GROUP BY order_id
),
pay AS (
    SELECT order_id,
           COUNT(*)                   AS n_payments,
           SUM(payment_value)         AS payment_total,
           MAX(payment_installments)  AS max_installments
    FROM stg_order_payments
    GROUP BY order_id
),
pay_main AS (   -- the payment method that covered the largest part of the order
    SELECT order_id, payment_type AS main_payment_type
    FROM (
        SELECT order_id, payment_type,
               ROW_NUMBER() OVER (PARTITION BY order_id
                                  ORDER BY payment_value DESC, payment_sequential) AS rn
        FROM stg_order_payments
    )
    WHERE rn = 1
),
base AS (
    SELECT o.order_id,
           o.customer_id,
           c.customer_unique_id,
           c.state                                   AS customer_state,
           c.city                                    AS customer_city,
           o.status                                  AS order_status,
           o.purchase_ts,
           DATE(o.purchase_ts)                       AS purchase_date,
           DATE(o.purchase_ts, 'start of month')     AS purchase_month,
           -- Monday of the purchase week ('weekday 0' = next Sunday, minus 6 days)
           DATE(o.purchase_ts, 'weekday 0', '-6 days') AS purchase_week,
           o.approved_ts,
           o.carrier_ts,
           o.delivered_customer_ts,
           o.estimated_ts,
           COALESCE(i.n_items, 0)                    AS n_items,
           COALESCE(i.n_sellers, 0)                  AS n_sellers,
           i.items_value,
           i.freight_value,
           COALESCE(p.n_payments, 0)                 AS n_payments,
           p.payment_total,
           p.max_installments,
           pm.main_payment_type,
           r.review_score,
           r.has_comment                             AS review_has_comment,
           CASE WHEN o.status NOT IN ('canceled', 'unavailable') THEN 1 ELSE 0 END
                                                     AS is_valid_order,
           o.delivered_before_purchase_flag
    FROM stg_orders o
    JOIN stg_customers c          ON c.customer_id = o.customer_id      -- 1:1
    LEFT JOIN items i             ON i.order_id = o.order_id            -- 1:1 (aggregated)
    LEFT JOIN pay p               ON p.order_id = o.order_id            -- 1:1 (aggregated)
    LEFT JOIN pay_main pm         ON pm.order_id = o.order_id           -- 1:1
    LEFT JOIN stg_order_reviews r ON r.order_id = o.order_id            -- 1:1 (deduplicated)
)
SELECT b.*,
       -- Delivery delay in WHOLE DAYS vs the promise. The estimate is a date
       -- (00:00:00) while the delivery has a time of day, so we compare dates:
       -- delivering at 15:00 on the promised date is on time, not 0.6 days late.
       CASE WHEN delivered_customer_ts IS NOT NULL AND estimated_ts IS NOT NULL
            THEN CAST(JULIANDAY(DATE(delivered_customer_ts)) - JULIANDAY(DATE(estimated_ts)) AS INTEGER)
       END                                                           AS delay_days,
       CASE WHEN delivered_customer_ts IS NOT NULL
            THEN ROUND(JULIANDAY(delivered_customer_ts) - JULIANDAY(purchase_ts), 2)
       END                                                           AS delivery_days,
       -- seller dispatch time and carrier transit time (negative = bad timestamp -> NULL)
       CASE WHEN carrier_ts IS NOT NULL AND JULIANDAY(carrier_ts) >= JULIANDAY(purchase_ts)
            THEN ROUND(JULIANDAY(carrier_ts) - JULIANDAY(purchase_ts), 2) END   AS dispatch_days,
       CASE WHEN carrier_ts IS NOT NULL AND delivered_customer_ts IS NOT NULL
                 AND JULIANDAY(delivered_customer_ts) >= JULIANDAY(carrier_ts)
            THEN ROUND(JULIANDAY(delivered_customer_ts) - JULIANDAY(carrier_ts), 2) END AS transit_days,
       -- dq03: payments should equal items + freight (tolerance 1.00 BRL)
       CASE WHEN n_items > 0
                 AND ABS(COALESCE(payment_total, 0) - (items_value + freight_value)) > 1.0
            THEN 1 ELSE 0 END                                        AS payment_mismatch_flag,
       -- dq09: status says delivered but there is no usable delivery date
       CASE WHEN order_status = 'delivered' AND delivered_customer_ts IS NULL
            THEN 1 ELSE 0 END                                        AS missing_delivery_date_flag
FROM base b;

CREATE UNIQUE INDEX ux_mart_orders ON mart_orders (order_id);
CREATE INDEX ix_mart_orders_unique_cust ON mart_orders (customer_unique_id);
CREATE INDEX ix_mart_orders_date ON mart_orders (purchase_date);
