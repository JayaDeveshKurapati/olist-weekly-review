-- Staging: EXACTLY ONE review per order.
-- Olist has orders with several review rows; joining raw reviews to orders would
-- multiply those orders (double counting). We keep the most recently answered
-- review per order (dq05) and drop rows whose score is not an integer 1-5 (dq06).
DROP TABLE IF EXISTS stg_order_reviews;

CREATE TABLE stg_order_reviews AS
SELECT order_id,
       review_id,
       CAST(review_score AS INTEGER)                                AS review_score,
       CASE WHEN NULLIF(TRIM(review_comment_message), '') IS NULL
            THEN 0 ELSE 1 END                                       AS has_comment,
       DATETIME(NULLIF(TRIM(review_creation_date), ''))             AS created_ts,
       DATETIME(NULLIF(TRIM(review_answer_timestamp), ''))          AS answered_ts
FROM (
    SELECT *,
           ROW_NUMBER() OVER (
               PARTITION BY order_id
               ORDER BY DATETIME(NULLIF(TRIM(review_answer_timestamp), '')) DESC,
                        DATETIME(NULLIF(TRIM(review_creation_date), '')) DESC,
                        review_id DESC
           ) AS rn
    FROM raw_order_reviews
    WHERE NULLIF(TRIM(review_score), '') IS NOT NULL
      AND CAST(review_score AS INTEGER) BETWEEN 1 AND 5
)
WHERE rn = 1
  AND order_id IN (SELECT order_id FROM stg_orders);

CREATE UNIQUE INDEX ux_stg_reviews_order ON stg_order_reviews (order_id);
