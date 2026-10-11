-- check: dq07_invalid_item_price_or_freight
-- description: (own check) order items must have price > 0 and freight_value >= 0 (not blank)
-- handling: dropped (item row excluded from staging)
-- why: a zero/negative/blank price cannot be revenue. The item is excluded rather than repaired because the true price is unknown; the order stays, with its remaining items.
-- max_fail_pct: 1.0
-- @found
SELECT COALESCE(SUM(CASE WHEN NULLIF(TRIM(price), '') IS NULL
                           OR CAST(price AS REAL) <= 0
                           OR NULLIF(TRIM(freight_value), '') IS NULL
                           OR CAST(freight_value AS REAL) < 0
                         THEN 1 ELSE 0 END), 0) AS bad_rows,
       COUNT(*) AS total_rows
FROM raw_order_items;
-- @residual
SELECT COUNT(*) AS bad_rows
FROM stg_order_items
WHERE price IS NULL OR price <= 0 OR freight_value IS NULL OR freight_value < 0;
