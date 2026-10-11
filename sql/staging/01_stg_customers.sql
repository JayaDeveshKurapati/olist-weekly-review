-- Staging: one clean row per customer_id.
-- NOTE: customer_id is generated per ORDER in Olist. customer_unique_id is the
-- real person, so repeat-purchase logic must use customer_unique_id.
DROP TABLE IF EXISTS stg_customers;

CREATE TABLE stg_customers AS
SELECT customer_id,
       customer_unique_id,
       TRIM(customer_zip_code_prefix)      AS zip_prefix,
       LOWER(TRIM(customer_city))          AS city,
       UPPER(TRIM(customer_state))         AS state
FROM (
    SELECT *, ROW_NUMBER() OVER (PARTITION BY customer_id ORDER BY rowid) AS rn
    FROM raw_customers
    WHERE NULLIF(TRIM(customer_id), '') IS NOT NULL
      AND NULLIF(TRIM(customer_unique_id), '') IS NOT NULL
)
WHERE rn = 1;

CREATE UNIQUE INDEX ux_stg_customers ON stg_customers (customer_id);
CREATE INDEX ix_stg_customers_unique ON stg_customers (customer_unique_id);
