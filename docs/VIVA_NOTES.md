# Viva notes - be able to explain every one of these

Read each SQL file next to its notes. If you cannot explain a line, change it until you can.

## Pipeline
- **Why SQLite?** Zero setup, supports CTEs, window functions and transactional DDL. ~100k orders is small. The same SQL ports to Postgres with minor changes (`DATE(...,'start of month')`, `julianday`).
- **ELT order:** raw (exact copy, all TEXT) -> staging (typed, deduplicated, validated) -> marts (business grain). Raw is never edited, so any cleaning decision can be audited or reversed.
- **Idempotent how?** Each raw table: DROP/CREATE/INSERT in one transaction. Staging + marts: DROP/CREATE AS in one transaction. Same input -> same output; nothing is appended. Test: `test_idempotent_two_runs_identical`.
- **Why one transaction around staging + marts + DQ?** SQLite DDL is transactional. If a check fails, ROLLBACK leaves yesterday's good marts in place - bad data is never published. Test: `test_dq_alarm_stops_pipeline_and_keeps_previous_marts`.
- **Why validate all files up front?** A missing column found after loading 6 tables leaves a half-updated warehouse. Validation reports every problem at once and touches nothing.
- **Why split the SQL script into statements in Python?** `executescript()` silently commits the open transaction.

## Data-quality checks
- Each check has two queries: *found* (on raw) and *residual* (after cleaning). Alarm if found % > tolerance **or** residual > 0.
- Counting rule: duplicates count the *surplus* rows (3 copies = 2 failing rows).
- dq03 uses a 1.00 BRL tolerance because instalment interest and vouchers legitimately move payments away from price + freight. Flagged, not dropped.
- dq04: `NOT IN (subquery)` instead of `NOT EXISTS` because raw tables have no indexes; `NOT EXISTS` was ~10x slower on the test data.

## Part C queries
- **Q1** `LAG` over a *calendar* from a recursive CTE. Without it, a gap month (Nov 2016 has no sales) would make LAG compare December with October. Growth is NULL (not infinity) when the previous month is 0.
- **Q2** `DENSE_RANK() OVER (PARTITION BY state ORDER BY revenue DESC)` <= 3. DENSE_RANK keeps ties together; ROW_NUMBER would cut a tie arbitrarily. Revenue is summed at item grain so payments/reviews cannot inflate it.
- **Q3** `AVG(...) OVER (ORDER BY day ROWS BETWEEN 6 PRECEDING AND CURRENT ROW)` on a gap-free calendar. `ROWS` counts rows; on a calendar with missing days it would span more than 7 days. First 6 days = NULL (incomplete window).
- **Q4** The trap: `customer_id` is new per order, so grouping by it gives 0% repeat. `customer_unique_id` is the person. The query prints both so the difference is visible.
- **Q5** Delay = date(delivered) - date(estimated) in whole days. The estimate is a date at 00:00; comparing timestamps would call a 3 pm delivery on the promised day "0.6 days late". Shown by review score and by delay bucket.

## Metrics
- North star = satisfied orders (delivered, 4-5 stars) per week. Guardrails: GMV (is it just shrinking?), on-time rate (the lever), low-review rate (what "4-5 stars" hides), repeat rate (retention).
- Weeks are attributed by *purchase* date, so the newest weeks are incomplete - the report trims them.

## Memo
- It is a draft assembled from the query results. Check each number against the charts, then rewrite the wording and the recommendation in your own words - you must be able to defend it.
- State the limit honestly: late and unhappy are *associated*; the pilot with a control group is how to test causation. Be ready for "what else could explain it?" (product type, seller, price).

## Likely questions
1. What happens if two runs overlap? (SQLite locks; the DAG sets `max_active_runs=1`.)
2. Why not drop all payment-mismatch orders? (Not wrong enough; revenue is item-based.)
3. What would you change at 100x scale? (Warehouse engine, incremental loads by date partition, indexes on join keys, DQ as dbt/Great Expectations tests.)
4. Where could a join double count? (Items x payments x reviews - prevented by pre-aggregation; test `test_no_double_counting_of_items_revenue`.)
