-- check: dq06_review_score_out_of_range
-- description: (own check) review_score must be an integer from 1 to 5
-- handling: dropped (invalid review ignored; the order keeps a NULL review_score)
-- why: an out-of-range score would silently shift average review scores. We cannot guess the true score, so the review is treated as missing rather than invented.
-- max_fail_pct: 1.0
-- @found
SELECT COALESCE(SUM(CASE WHEN NULLIF(TRIM(review_score), '') IS NULL
                           OR CAST(review_score AS INTEGER) NOT BETWEEN 1 AND 5
                         THEN 1 ELSE 0 END), 0) AS bad_rows,
       COUNT(*) AS total_rows
FROM raw_order_reviews;
-- @residual
SELECT COUNT(*) AS bad_rows
FROM stg_order_reviews
WHERE review_score IS NULL OR review_score NOT BETWEEN 1 AND 5;
