-- Extra (supports the VP memo). Where is lateness concentrated, and is it the seller
-- (slow dispatch to the carrier) or the carrier (slow transit)?
-- States with fewer than 50 delivered orders are left out (too noisy).
SELECT customer_state,
       COUNT(*)                                                   AS delivered_orders,
       ROUND(100.0 * AVG(delay_days > 0), 1)                      AS late_rate_pct,
       ROUND(AVG(CASE WHEN delay_days > 0 THEN delay_days END), 1) AS avg_days_late_when_late,
       ROUND(AVG(CASE WHEN delay_days > 0 THEN dispatch_days END), 1) AS dispatch_days_when_late,
       ROUND(AVG(CASE WHEN delay_days > 0 THEN transit_days END), 1)  AS transit_days_when_late,
       ROUND(AVG(CASE WHEN delay_days <= 0 THEN dispatch_days END), 1) AS dispatch_days_on_time,
       ROUND(AVG(CASE WHEN delay_days <= 0 THEN transit_days END), 1)  AS transit_days_on_time,
       ROUND(AVG(review_score), 2)                                AS avg_review_score
FROM mart_orders
WHERE order_status = 'delivered' AND delay_days IS NOT NULL
GROUP BY customer_state
HAVING COUNT(*) >= 50
ORDER BY late_rate_pct DESC;
