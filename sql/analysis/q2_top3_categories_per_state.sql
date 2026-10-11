-- Q2. Top 3 product categories per customer state by revenue.
-- Revenue = SUM(item price) of valid orders, summed at ITEM grain (mart_order_items),
-- so payments/reviews cannot inflate it.
-- DENSE_RANK (not ROW_NUMBER) so that categories tied on revenue share a rank;
-- a state can therefore return more than 3 rows only if there is an exact tie.
WITH category_revenue AS (
    SELECT customer_state,
           category_en,
           SUM(price)                AS revenue,
           COUNT(DISTINCT order_id)  AS orders
    FROM mart_order_items
    WHERE is_valid_order = 1
    GROUP BY customer_state, category_en
),
ranked AS (
    SELECT *,
           DENSE_RANK() OVER (PARTITION BY customer_state ORDER BY revenue DESC) AS rnk
    FROM category_revenue
)
SELECT customer_state,
       rnk                   AS rank_in_state,
       category_en           AS category,
       ROUND(revenue, 2)     AS revenue,
       orders
FROM ranked
WHERE rnk <= 3
ORDER BY customer_state, rnk, category_en;
