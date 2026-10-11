-- Staging for the small dimension tables: products, sellers, geolocation.
DROP TABLE IF EXISTS stg_products;
CREATE TABLE stg_products AS
SELECT p.product_id,
       NULLIF(TRIM(p.product_category_name), '')                      AS category_pt,
       -- Fall back to the Portuguese name when a category has no translation
       -- (two categories in the real data), and to 'unknown' when it is blank.
       COALESCE(NULLIF(TRIM(t.product_category_name_english), ''),
                NULLIF(TRIM(p.product_category_name), ''),
                'unknown')                                            AS category_en
FROM (
    SELECT *, ROW_NUMBER() OVER (PARTITION BY product_id ORDER BY rowid) AS rn
    FROM raw_products WHERE NULLIF(TRIM(product_id), '') IS NOT NULL
) p
LEFT JOIN (
    SELECT product_category_name, MIN(product_category_name_english) AS product_category_name_english
    FROM raw_product_category_translation GROUP BY product_category_name
) t ON t.product_category_name = p.product_category_name
WHERE p.rn = 1;
CREATE UNIQUE INDEX ux_stg_products ON stg_products (product_id);

DROP TABLE IF EXISTS stg_sellers;
CREATE TABLE stg_sellers AS
SELECT seller_id,
       TRIM(seller_zip_code_prefix)  AS zip_prefix,
       LOWER(TRIM(seller_city))      AS city,
       UPPER(TRIM(seller_state))     AS state
FROM (
    SELECT *, ROW_NUMBER() OVER (PARTITION BY seller_id ORDER BY rowid) AS rn
    FROM raw_sellers WHERE NULLIF(TRIM(seller_id), '') IS NOT NULL
)
WHERE rn = 1;
CREATE UNIQUE INDEX ux_stg_sellers ON stg_sellers (seller_id);

-- Geolocation has many rows per zip prefix; collapse to one centroid per prefix.
DROP TABLE IF EXISTS stg_geolocation;
CREATE TABLE stg_geolocation AS
SELECT TRIM(geolocation_zip_code_prefix)        AS zip_prefix,
       AVG(CAST(geolocation_lat AS REAL))       AS lat,
       AVG(CAST(geolocation_lng AS REAL))       AS lng,
       COUNT(*)                                 AS n_points
FROM raw_geolocation
WHERE NULLIF(TRIM(geolocation_zip_code_prefix), '') IS NOT NULL
GROUP BY TRIM(geolocation_zip_code_prefix);
CREATE UNIQUE INDEX ux_stg_geo ON stg_geolocation (zip_prefix);
