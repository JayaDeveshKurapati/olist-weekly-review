-- Q5 (companion). The same relationship from the other direction: group orders by
-- how late they arrived and look at the review score. The numeric prefix keeps the
-- buckets in order.
WITH base AS (
    SELECT review_score,
           CASE WHEN delay_days <= -8 THEN '1: 8+ days early'
                WHEN delay_days <= -1 THEN '2: 1-7 days early'
                WHEN delay_days = 0   THEN '3: on estimated date'
                WHEN delay_days <= 3  THEN '4: 1-3 days late'
                WHEN delay_days <= 7  THEN '5: 4-7 days late'
                ELSE                       '6: 8+ days late'
           END AS delay_bucket
    FROM mart_orders
    WHERE order_status = 'delivered'
      AND delay_days IS NOT NULL
      AND review_score IS NOT NULL
)
SELECT delay_bucket,
       COUNT(*)                                      AS orders,
       ROUND(AVG(review_score), 2)                   AS avg_review_score,
       ROUND(100.0 * AVG(review_score <= 2), 1)      AS pct_low_reviews_1_2,
       ROUND(100.0 * AVG(review_score = 5), 1)       AS pct_five_star
FROM base
GROUP BY delay_bucket
ORDER BY delay_bucket;
