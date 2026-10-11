# Olist Weekly Business Review - ELT pipeline, data quality, SQL analysis

A small, reproducible pipeline for the Brazilian E-Commerce (Olist) dataset:

1. **Load** nine CSVs into raw tables, **clean** them into staging tables, **build** analysis-ready marts (SQLite, plain SQL files).
2. **Check** the data with nine SQL data-quality checks; a failed check stops the pipeline.
3. **Answer** five business questions in SQL (CTEs + window functions) and build a 5-page PDF report.

The core pipeline uses only the Python standard library. The report and tests need `pandas`, `matplotlib`, `reportlab`, `pypdf`, `pytest`.

## Repository layout

```
pipeline/            run.py (entry point), ingest.py, quality.py, queries.py, db.py, config.py, errors.py
sql/staging/         01-06  cleaning: one clean table per source
sql/marts/           10 mart_orders (1 row/order) | 11 mart_order_items | 12 mart_weekly_metrics
sql/dq/              dq01 ... dq09  Part B data-quality checks (rule, handling, tolerance in the header)
sql/analysis/        q1 ... q5b  Part C queries, one file each; x1 + weekly_metrics support Part D
report/build_report.py   PDF report (charts, tables, VP memo draft)
dags/olist_daily_dag.py  Airflow DAG, @daily (bonus)
tools/make_synthetic_data.py   fake Olist-shaped data for tests / smoke runs (NOT real data)
tests/               pytest suite (14 tests)
docs/VIVA_NOTES.md   explanation of every query and design decision
```

## Run it (step by step)

```bash
# 1. environment (Python 3.10+)
python -m venv .venv
source .venv/bin/activate            # Windows: .venv\Scripts\activate
pip install -r requirements.txt

# 2. get the real data (needs a free Kaggle account)
#    https://www.kaggle.com/datasets/olistbr/brazilian-ecommerce
#    unzip the nine CSVs into data/raw/ (file names unchanged), or:
#    kaggle datasets download -d olistbr/brazilian-ecommerce -p data/raw --unzip

# 3. run the pipeline  (load -> staging -> marts -> DQ gate -> Part C queries)
python -m pipeline.run --raw-dir data/raw --db db/olist.db

# 4. build the PDF report  ->  outputs/report.pdf
python -m report.build_report

# 5. run the tests
pytest -q
```

Run step 3 as often as you like: raw tables are rebuilt atomically and staging/marts are rebuilt in one transaction, so repeated runs give identical tables.

**No Kaggle account yet?** Smoke-test everything on synthetic data:
`python tools/make_synthetic_data.py --out data/synthetic` then `python -m pipeline.run --raw-dir data/synthetic --db db/demo.db`.
Reports built from it carry a "SYNTHETIC DEMO DATA" banner.

Outputs: `db/olist.db` (all tables), `outputs/query_results/*.csv` (one per query), `outputs/charts/*.png`, `outputs/report.pdf`, `logs/pipeline.log`.

## What happens when something is wrong

| Situation | Behaviour | Exit code |
|---|---|---|
| A CSV is missing, empty, or lacks an expected column | All problems listed in one message, **before** the database is touched | 2 |
| A row has the wrong number of fields | Stops with file name and line number; that table's load is rolled back | 2 |
| A data-quality check fails | Alarm message lists the failed checks; staging/mart changes are **rolled back**, previous good tables stay | 3 |
| Anything else | Full traceback in `logs/pipeline.log` | 1 |

Every step logs START / DONE with timing; the run is recorded in the `etl_run_log` table and DQ results in `dq_results`.

### Data-quality checks (sql/dq/)

A check passes when (1) the share of failing raw rows is within its `max_fail_pct` tolerance and (2) **zero** bad rows remain after the handling. Tolerances live in each file's header. If the very first run on the real data alarms because a tolerance is too tight (most likely `dq03`), look at the logged failing percentage, decide whether it is a real problem, and adjust that one header value with a sentence of justification in your report.

| Check | Handling |
|---|---|
| dq01 null/duplicate `order_id` | dropped |
| dq02 delivered before purchased | fixed (date -> NULL) + flagged |
| dq03 payments != items + freight | flagged |
| dq04 order without customer | dropped |
| dq05 several reviews per order (own) | fixed (keep latest) |
| dq06 review score not 1-5 (own) | dropped |
| dq07 item price <= 0 / blank freight (own) | dropped |
| dq08 orphan items/payments/reviews (own) | dropped |
| dq09 'delivered' without delivery date (own) | flagged |

## Airflow (bonus)

`dags/olist_daily_dag.py` runs the same functions as four tasks (`validate_inputs >> load_raw >> transform_and_quality_gate >> analysis_queries`), scheduled `@daily`, `max_active_runs=1`. Input and data-quality failures raise `AirflowFailException` so they are not retried. To try it: `pip install apache-airflow`, set `OLIST_PROJECT_DIR`, `OLIST_RAW_DIR`, `OLIST_DB_PATH`, and point `dags_folder` at `dags/`. (The DAG is syntax-checked but was not executed inside an Airflow install when this repo was written.)

## Key modelling decisions

- **`customer_unique_id`, not `customer_id`**, identifies a person; `customer_id` is regenerated for every order (Q4).
- **No join fan-out:** items, payments and reviews are each aggregated to one row per order *before* joining.
- **Revenue** = item price of orders whose status is not canceled/unavailable (freight excluded).
- **Late** = delivery *date* after the estimated *date* (the estimate has no time of day).
